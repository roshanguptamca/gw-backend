"""
ScannerOrchestrator — resolves which engines to run for a scan, runs each in
order while updating progress/status, aggregates + deduplicates findings,
and performs simple cross-engine correlation.
"""

from __future__ import annotations

import logging
from pathlib import Path

from django.utils import timezone

from ..discovery.engine import ApplicationDiscoveryEngine
from ..runtime.manager import RuntimeEnvironmentManager
from .api import ApiScanner
from .base import ScannerFinding
from .container import ContainerScanner
from .dast import DastScanner
from .iac import IacScanner
from .mode_labels import classify_raw_tool
from .sast import SastScanner
from .sca import ScaScanner
from .secrets import SecretsScanner

logger = logging.getLogger(__name__)

_ENGINE_CLASSES = {
    "sast": SastScanner,
    "sca": ScaScanner,
    "secrets": SecretsScanner,
    "iac": IacScanner,
    "container": ContainerScanner,
    "api": ApiScanner,
    "dast": DastScanner,
}

_BASE_FULL_ENGINES = ["sast", "sca", "secrets", "iac"]

_SPEC_FILENAMES = ("openapi.json", "openapi.yaml", "openapi.yml", "swagger.json", "swagger.yaml", "swagger.yml")


def _repo_has_dockerfile(repo_path: Path) -> bool:
    return repo_path.exists() and any(
        p.name == "Dockerfile" or p.name.startswith("Dockerfile.") for p in repo_path.glob("**/*") if p.is_file()
    )


def _repo_has_api_spec(repo_path: Path) -> bool:
    if not repo_path.exists():
        return False
    return any(p.is_file() and p.name.lower() in _SPEC_FILENAMES for p in repo_path.rglob("*"))


def _dockerfile_has_healthcheck(repo_path: Path, dockerfile_relative_path: str) -> bool:
    if not dockerfile_relative_path:
        return False
    try:
        content = (repo_path / dockerfile_relative_path).read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    return "HEALTHCHECK" in content.upper()


def _missing_health_finding(target_url: str) -> ScannerFinding:
    """
    Low-severity, non-blocking recommendation for a discovered/started
    application that has no dedicated health endpoint and/or Docker
    HEALTHCHECK. See docs/SMART_REPO_SCAN.md — this must never fail a scan,
    only surface as a helpful recommendation.
    """
    return ScannerFinding(
        title="Missing Docker HEALTHCHECK or application health endpoint",
        description=(
            f"SecureWise reached {target_url} but found no dedicated health endpoint "
            "(e.g. /health, /healthz) and/or no Docker HEALTHCHECK instruction. This makes "
            "it harder for orchestrators and monitoring tools to detect degraded instances."
        ),
        severity="low",
        confidence="medium",
        scanner_type="dast",
        endpoint=target_url,
        cwe_id="CWE-703",
        owasp_category="A10:2025",
        recommendation=(
            "Add a dedicated health endpoint (e.g. GET /health returning 200) and a Docker "
            "HEALTHCHECK instruction, for example:\n"
            "HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 "
            "CMD curl -f http://localhost:8000/health || exit 1"
        ),
        evidence={"raw_tool": "securewise-discovery"},
        fingerprint=f"dast-missing-health-{target_url}",
    )


class ScannerOrchestrator:
    """Resolves engines for a scan and runs them, persisting per-engine results."""

    def resolve_engines(self, scan, repo_path: Path | None = None) -> list[str]:
        if scan.scan_type != "full":
            return [scan.scan_type]

        engines = list(_BASE_FULL_ENGINES)
        repo_path = repo_path or Path("/nonexistent")
        discovery = None
        if repo_path.exists():
            try:
                discovery = ApplicationDiscoveryEngine().discover(repo_path)
            except Exception:  # pragma: no cover - defensive
                logger.exception("Discovery failed while resolving engines for scan %s", getattr(scan, "id", "unknown"))

        if scan.docker_image or (
            _repo_has_dockerfile(repo_path) and (discovery is None or discovery.project_type not in ("library", "cli"))
        ):
            engines.append("container")
        if scan.api_spec_url or _repo_has_api_spec(repo_path):
            engines.append("api")
        if scan.target_url:
            engines.append("dast")
        elif scan.repository_id and (discovery is None or discovery.requires_runtime):
            # `scan.repository_id` signals a real, repo-backed scan (as
            # opposed to unit tests that pass a bare repo_path with no
            # repository FK). For runtime-capable repos we keep DAST in the
            # engine list so smart discovery/runtime-start can supply a
            # target URL when the user did not configure one explicitly.
            # Library/CLI repos are intentionally excluded here because they
            # have no HTTP runtime to target.
            engines.append("dast")
        return engines

    def run(self, scan, repo_path: Path):
        """
        Run all resolved engines for `scan`. Returns (all_findings, engine_meta dict, any_failed, any_skipped).
        Persists SecureWiseScanEngineResult rows and updates scan.status/progress.
        """
        from apps.securewise.models import SecureWiseScan, SecureWiseScanEngineResult

        engines = self.resolve_engines(scan, repo_path)
        scan.selected_engines = engines
        scan.save(update_fields=["selected_engines"])

        metadata = {
            "docker_image": scan.docker_image,
            "api_spec_url": scan.api_spec_url,
            "target_url": scan.target_url,
        }

        discovery_plan = None
        runtime_manager = None
        self._active_runtime_manager = None
        self._discovery_findings: list[ScannerFinding] = []
        # Smart discovery/runtime auto-start: only attempted for real,
        # repo-backed scans (scan.repository_id set) that need DAST but
        # don't already have an explicit target_url. This never runs for
        # unit tests using bare tmp_path fixtures with no repository FK —
        # see docs/SMART_REPO_SCAN.md.
        if "dast" in engines and not scan.target_url and scan.repository_id:
            discovery_plan, metadata = self._run_discovery_and_runtime(scan, repo_path, metadata)
            runtime_manager = getattr(self, "_active_runtime_manager", None)

        all_findings: list[ScannerFinding] = []
        engine_meta: dict = {}
        seen_fingerprints: dict[str, ScannerFinding] = {}
        any_failed = False
        any_skipped = False
        total = len(engines) or 1

        try:
            for idx, engine_name in enumerate(engines):
                # Check for cancellation between engines.
                current_status = SecureWiseScan.objects.filter(id=scan.id).values_list("status", flat=True).first()
                if current_status == "cancelled":
                    logger.info("Scan %s cancelled mid-run; stopping before engine %s", scan.id, engine_name)
                    break

                scan.status = f"running_{engine_name}"
                scan.save(update_fields=["status"])

                engine_result = SecureWiseScanEngineResult.objects.create(
                    scan=scan,
                    engine=engine_name,
                    status="running",
                    started_at=timezone.now(),
                )

                engine_cls = _ENGINE_CLASSES[engine_name]
                engine = engine_cls()
                started = timezone.now()
                try:
                    result = engine.run(repo_path, str(scan.id), metadata)
                except Exception as exc:  # pragma: no cover - defensive
                    logger.exception("Engine %s failed for scan %s", engine_name, scan.id)
                    result = None
                    engine_result.status = "failed"
                    engine_result.error_message = str(exc)
                    any_failed = True

                completed = timezone.now()
                duration = int((completed - started).total_seconds())

                if result is not None:
                    if result.status == "skipped":
                        engine_result.status = "skipped"
                        engine_result.skipped_reason = result.skipped_reason
                        any_skipped = True
                    elif not result.success:
                        engine_result.status = "failed"
                        engine_result.error_message = result.error
                        any_failed = True
                    else:
                        engine_result.status = "completed"
                        for finding in result.findings:
                            if not finding.scanner_type:
                                finding.scanner_type = engine_name
                            self._dedupe_and_collect(finding, all_findings, seen_fingerprints)
                    engine_result.raw_summary = result.metadata or {}
                    # Label how this engine actually produced its results (real tool vs
                    # fallback heuristic vs passive-only vs not configured), so the scan
                    # can never silently present a fallback/passive run as a full real
                    # scan. See scanners/mode_labels.py + docs/CURRENT_SECUREWISE_REVIEW.md.
                    engine_result.raw_summary["mode"] = classify_raw_tool(engine_result.raw_summary.get("raw_tool"))
                    engine_result.findings_count = len(result.findings)

                if discovery_plan is not None and engine_name == "dast":
                    engine_result.raw_summary = engine_result.raw_summary or {}
                    engine_result.raw_summary["discovery"] = discovery_plan.to_dict()

                engine_result.started_at = started
                engine_result.completed_at = completed
                engine_result.duration_seconds = duration
                engine_result.save()

                engine_meta[engine_name] = engine_result.raw_summary

                scan.progress = int(round(((idx + 1) / total) * 100))
                scan.save(update_fields=["progress"])
        finally:
            if runtime_manager is not None:
                runtime_manager.stop()

        self._correlate(all_findings)
        self._populate_code_snippets(repo_path, all_findings)

        for finding in getattr(self, "_discovery_findings", []):
            self._dedupe_and_collect(finding, all_findings, seen_fingerprints)

        scan.status = "normalizing"
        scan.save(update_fields=["status"])

        return all_findings, engine_meta, any_failed, any_skipped

    # ------------------------------------------------------------------
    def _run_discovery_and_runtime(self, scan, repo_path: Path, metadata: dict):
        """
        Statically discover the application, then attempt to auto-start it in
        an isolated container so DAST has a real target URL. Always returns
        (plan, metadata) — never raises. On any failure, metadata is given a
        clear `dast_skip_reason` instead of a target_url.
        """
        try:
            plan = ApplicationDiscoveryEngine().discover(repo_path)
        except Exception:  # pragma: no cover - defensive; discovery must never crash a scan
            logger.exception("Application discovery failed for scan %s", scan.id)
            metadata["dast_skip_reason"] = "application discovery failed unexpectedly"
            return None, metadata

        scan.scanner_metadata = {**(scan.scanner_metadata or {}), "discovery": plan.to_dict()}
        scan.save(update_fields=["scanner_metadata"])

        if not plan.requires_runtime or not plan.can_auto_run:
            reason = (
                plan.skip_reasons[0]
                if plan.skip_reasons
                else "SecureWise could not determine how to start this application automatically"
            )
            metadata["dast_skip_reason"] = reason
            return plan, metadata

        manager = RuntimeEnvironmentManager()
        try:
            runtime_result = manager.try_start(repo_path, plan)
        except Exception:  # pragma: no cover - defensive; runtime start must never crash a scan
            logger.exception("Runtime auto-start failed unexpectedly for scan %s", scan.id)
            metadata["dast_skip_reason"] = "Application could not be auto-started due to an unexpected runtime error."
            return plan, metadata

        if not runtime_result.started:
            metadata["dast_skip_reason"] = (
                runtime_result.skip_reason
                or "Application could not be auto-started because required runtime dependencies were not available."
            )
            return plan, metadata

        plan.selected_runtime_url = runtime_result.runtime_url
        plan.selected_health_endpoint = runtime_result.selected_health_endpoint
        metadata["target_url"] = runtime_result.runtime_url
        # Keep the manager reachable so run() can stop the container in its
        # `finally` block regardless of what happens in the engine loop.
        self._active_runtime_manager = manager

        dockerfile_has_healthcheck = _dockerfile_has_healthcheck(repo_path, plan.dockerfile_path)
        if not runtime_result.has_dedicated_health_endpoint or (plan.has_dockerfile and not dockerfile_has_healthcheck):
            self._discovery_findings = [_missing_health_finding(runtime_result.runtime_url)]

        return plan, metadata

    # ------------------------------------------------------------------
    def _dedupe_and_collect(self, finding: ScannerFinding, all_findings: list, seen: dict):
        existing = seen.get(finding.fingerprint)
        if existing is None:
            seen[finding.fingerprint] = finding
            all_findings.append(finding)
            return
        # Same fingerprint reported by a later engine — bump confidence.
        order = ["low", "medium", "high", "very_high"]
        if order.index(finding.confidence) > order.index(existing.confidence):
            existing.confidence = finding.confidence
        existing.evidence.setdefault("also_reported_by", []).append(finding.scanner_type)

    def _correlate(self, all_findings: list[ScannerFinding]):
        """Bump confidence on SAST findings that are corroborated by a DAST finding."""
        sast_findings = [f for f in all_findings if f.scanner_type == "sast"]
        dast_findings = [f for f in all_findings if f.scanner_type == "dast"]
        if not sast_findings or not dast_findings:
            return
        for sast_f in sast_findings:
            stem = Path(sast_f.file_path).stem.lower() if sast_f.file_path else ""
            title_keywords = {w for w in sast_f.title.lower().split() if len(w) > 3}
            for dast_f in dast_findings:
                haystack = f"{dast_f.endpoint} {dast_f.title}".lower()
                match = (stem and stem in haystack) or any(kw in haystack for kw in title_keywords)
                if match:
                    sast_f.confidence = "very_high"
                    sast_f.evidence.setdefault("correlated_with", []).append(
                        {"engine": "dast", "title": dast_f.title, "endpoint": dast_f.endpoint}
                    )
                    break

    def _populate_code_snippets(self, repo_path: Path, findings: list[ScannerFinding]):
        repo_root = repo_path.resolve()
        for finding in findings:
            if not finding.file_path or not finding.line_number or finding.line_number < 1:
                continue
            snippet = self._extract_code_snippet(repo_root, finding.file_path, finding.line_number)
            if snippet:
                finding.code_snippet = snippet

    def _extract_code_snippet(self, repo_root: Path, file_path: str, line_number: int) -> str:
        try:
            candidate = (repo_root / file_path).resolve()
            candidate.relative_to(repo_root)
        except (OSError, ValueError):
            return ""

        if not candidate.is_file():
            return ""

        try:
            raw = candidate.read_bytes()
            if b"\x00" in raw:
                return ""
            content = raw.decode("utf-8")
        except (OSError, UnicodeDecodeError):
            return ""

        lines = content.splitlines()
        if line_number > len(lines):
            return ""

        start = max(1, line_number - 3)
        end = min(len(lines), line_number + 2)
        snippet_lines = []
        for current in range(start, end + 1):
            marker = ">>" if current == line_number else "  "
            snippet_lines.append(f"{marker} {current}: {lines[current - 1]}")
        return "\n".join(snippet_lines)
