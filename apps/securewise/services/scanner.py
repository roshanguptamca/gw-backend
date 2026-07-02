"""
SecureWise scanner service — orchestrates cloning a repository and running
the resolved set of real/fallback scan engines via ScannerOrchestrator.

Security rules:
- Tokens are decrypted only inside this runtime, never logged.
- Clone directory is always deleted after scan.
- Authenticated clone URL is never stored or logged.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from apps.securewise.scanners.orchestrator import ScannerOrchestrator
from apps.securewise.scanners.repository import clone_repository

logger = logging.getLogger(__name__)


class ScannerRunner:
    """
    Orchestrates cloning a repository and running one or more scan engines.
    """

    def run_scan(self, scan_id: str) -> None:
        """Entry point called by the view after saving the scan."""
        from django.utils import timezone

        from apps.securewise.models import SecureWiseAuditLog, SecureWiseFinding, SecureWiseScan

        try:
            scan = SecureWiseScan.objects.select_related(
                "repository", "repository__integration", "project", "organization", "policy"
            ).get(id=scan_id)
        except SecureWiseScan.DoesNotExist:
            logger.error("ScannerRunner: scan %s not found", scan_id)
            return

        scan.status = "running"
        scan.started_at = timezone.now()
        scan.progress = 0
        scan.save(update_fields=["status", "started_at", "progress"])

        SecureWiseAuditLog.objects.create(
            organization=scan.organization,
            user=scan.triggered_by,
            event="scan_started",
            target_type="SecureWiseScan",
            target_id=str(scan.id),
            detail={"scan_type": scan.scan_type, "project": str(scan.project_id)},
        )

        all_findings = []
        engine_meta: dict = {}
        any_engine_failed = False
        error_msg = ""

        try:
            with tempfile.TemporaryDirectory(prefix="sw_scan_") as tmpdir:
                repo_path = Path(tmpdir) / "repo"

                if scan.repository:
                    scan.status = "cloning"
                    scan.save(update_fields=["status"])
                    clone_repository(scan, repo_path, allowed_root=Path(tmpdir))
                else:
                    repo_path.mkdir(parents=True, exist_ok=True)

                orchestrator = ScannerOrchestrator()
                all_findings, engine_meta, any_engine_failed = orchestrator.run(scan, repo_path)
                scan.scanner_metadata = engine_meta
            # tempdir is cleaned up here automatically

        except Exception as exc:
            logger.exception("Scan %s failed during execution", scan_id)
            error_msg = str(exc)

        # Persist findings — deduplicated by (project, fingerprint) so rescans of
        # unchanged code update the existing issue instead of creating duplicates.
        new_count, recurring_count, reopened_count, new_finding_ids = self._persist_findings(scan, all_findings)

        if new_count:
            SecureWiseAuditLog.objects.create(
                organization=scan.organization,
                user=scan.triggered_by,
                event="finding_created",
                target_type="SecureWiseScan",
                target_id=str(scan.id),
                detail={"count": new_count},
            )
        if reopened_count:
            SecureWiseAuditLog.objects.create(
                organization=scan.organization,
                user=scan.triggered_by,
                event="finding_reopened",
                target_type="SecureWiseScan",
                target_id=str(scan.id),
                detail={"count": reopened_count},
            )

        # Auto-resolve: findings the just-ran engines used to detect but no longer do.
        auto_resolved_count = self._auto_resolve_findings(scan, engine_meta, all_findings)
        if auto_resolved_count:
            SecureWiseAuditLog.objects.create(
                organization=scan.organization,
                user=scan.triggered_by,
                event="finding_auto_resolved",
                target_type="SecureWiseScan",
                target_id=str(scan.id),
                detail={"count": auto_resolved_count},
            )

        # Quality gate — evaluated against the current persisted/deduplicated state.
        quality_gate_passed = self._evaluate_quality_gate(scan, new_finding_ids)

        completed_at = timezone.now()
        duration = int((completed_at - scan.started_at).total_seconds())

        scan.refresh_from_db(fields=["status"])
        if scan.status == "cancelled":
            final_status = "cancelled"
        elif error_msg:
            final_status = "failed"
        elif any_engine_failed:
            final_status = "completed_with_warnings"
        else:
            final_status = "completed"

        scan.status = final_status
        scan.completed_at = completed_at
        scan.duration_seconds = duration
        scan.error_message = error_msg
        scan.quality_gate_passed = quality_gate_passed
        scan.progress = 100 if final_status != "cancelled" else scan.progress
        scan.save(
            update_fields=[
                "status",
                "completed_at",
                "duration_seconds",
                "error_message",
                "quality_gate_passed",
                "scanner_metadata",
                "progress",
            ]
        )

        SecureWiseAuditLog.objects.create(
            organization=scan.organization,
            user=scan.triggered_by,
            event="scan_completed" if final_status in ("completed", "completed_with_warnings") else "scan_failed",
            target_type="SecureWiseScan",
            target_id=str(scan.id),
            detail={
                "findings": len(all_findings),
                "quality_gate_passed": quality_gate_passed,
                "duration_seconds": duration,
                "status": final_status,
            },
        )

    # ------------------------------------------------------------------
    def _persist_findings(self, scan, findings: list) -> tuple[int, int, int, set]:
        """
        Merge normalized findings into SecureWiseFinding rows, deduplicated by
        (project, fingerprint). Rescanning the same repository re-detects the
        same issues — we must update the existing row (bump occurrence/last
        seen, reopen if it had been marked fixed) instead of inserting a
        duplicate. Findings without a fingerprint are always inserted as-is
        (can't be safely deduplicated).

        Returns (new_count, recurring_count, reopened_count, new_finding_ids).
        """
        from django.utils import timezone

        from apps.securewise.models import SecureWiseFinding

        now = timezone.now()
        new_count = 0
        recurring_count = 0
        reopened_count = 0
        new_finding_ids: set = set()

        fingerprints = [f.fingerprint for f in findings if f.fingerprint]
        existing_by_fp = {
            fp: obj
            for fp, obj in SecureWiseFinding.objects.filter(
                project=scan.project, fingerprint__in=fingerprints
            ).values_list("fingerprint", "id")
        }
        # Re-query full objects only for the ones we need to update.
        existing_objs = {
            obj.fingerprint: obj
            for obj in SecureWiseFinding.objects.filter(project=scan.project, fingerprint__in=fingerprints)
        }

        to_create = []
        to_update = []
        for f in findings:
            existing = existing_objs.get(f.fingerprint) if f.fingerprint else None
            if existing:
                existing.scan = scan
                existing.last_seen_at = now
                existing.occurrence_count = (existing.occurrence_count or 1) + 1
                # Refresh descriptive fields in case code/content changed slightly.
                existing.severity = f.severity
                existing.confidence = f.confidence
                existing.description = f.description
                existing.evidence = f.evidence
                existing.code_snippet = f.code_snippet
                if existing.status == "fixed":
                    existing.status = "open"
                    existing.review_note = (
                        f"Automatically reopened: recurred in scan {scan.id}."
                        + (f" {existing.review_note}" if existing.review_note else "")
                    )
                    reopened_count += 1
                else:
                    recurring_count += 1
                to_update.append(existing)
            else:
                obj = SecureWiseFinding(
                    scan=scan,
                    first_seen_scan=scan,
                    last_seen_at=now,
                    occurrence_count=1,
                    project=scan.project,
                    organization=scan.organization,
                    title=f.title,
                    description=f.description,
                    severity=f.severity,
                    confidence=f.confidence,
                    scanner_type=f.scanner_type,
                    file_path=f.file_path,
                    line_number=f.line_number,
                    endpoint=f.endpoint,
                    cwe_id=f.cwe_id,
                    owasp_category=f.owasp_category,
                    risk=f.risk,
                    impact=f.impact,
                    recommendation=f.recommendation,
                    bad_code_example=f.bad_code_example,
                    fixed_code_example=f.fixed_code_example,
                    code_snippet=f.code_snippet,
                    evidence=f.evidence,
                    fingerprint=f.fingerprint,
                    status="open",
                )
                to_create.append(obj)
                new_count += 1

        if to_create:
            created = SecureWiseFinding.objects.bulk_create(to_create, ignore_conflicts=True)
            new_finding_ids.update(obj.id for obj in created)
        if to_update:
            SecureWiseFinding.objects.bulk_update(
                to_update,
                [
                    "scan",
                    "last_seen_at",
                    "occurrence_count",
                    "severity",
                    "confidence",
                    "description",
                    "evidence",
                    "code_snippet",
                    "status",
                    "review_note",
                ],
            )

        return new_count, recurring_count, reopened_count, new_finding_ids

    # ------------------------------------------------------------------
    def _auto_resolve_findings(self, scan, engine_meta: dict, findings: list) -> int:
        """
        For each engine that just ran successfully, any previously-open finding
        of that scanner_type that was NOT re-detected this run is considered
        fixed (the code/config no longer triggers it) and is auto-resolved —
        mirroring how SonarQube/Snyk/Semgrep handle disappearing issues on
        rescans. Only applies to engines that actually completed (skipped or
        failed engines give no signal either way, so we leave those findings
        alone).
        """
        from django.utils import timezone

        from apps.securewise.models import SecureWiseFinding

        detected_fingerprints = {f.fingerprint for f in findings if f.fingerprint}
        completed_engines = list(
            scan.engine_results.filter(status="completed").values_list("engine", flat=True)
        )
        if not completed_engines:
            return 0

        stale_findings = list(
            SecureWiseFinding.objects.filter(
                project=scan.project,
                scanner_type__in=completed_engines,
                status="open",
            )
            .exclude(fingerprint="")
            .exclude(fingerprint__in=detected_fingerprints)
        )
        if not stale_findings:
            return 0

        now = timezone.now()
        for finding in stale_findings:
            finding.status = "fixed"
            finding.reviewed_at = now
            finding.review_note = f"Auto-resolved: not detected in scan {scan.id}."

        SecureWiseFinding.objects.bulk_update(stale_findings, ["status", "reviewed_at", "review_note"])
        return len(stale_findings)

    # ------------------------------------------------------------------
    def _evaluate_quality_gate(self, scan, new_finding_ids: set) -> bool | None:
        """
        Returns True/False if a quality gate policy was evaluated, or None if
        no policy is attached to this scan, or the user explicitly bypassed
        the gate for this run — either way "not applicable" must NOT be
        rendered as "passed" by callers/UI.

        Evaluates against the *current* persisted/deduplicated open findings
        for the project (not just this run's raw output), so a policy
        correctly reflects recurring unresolved issues too — unless the
        policy opts into fail_on_new_findings_only.
        """
        from apps.securewise.models import SecureWiseFinding

        if scan.bypass_quality_gate:
            return None
        policy = scan.policy
        if not policy:
            return None

        statuses = ["open"]
        if not policy.allow_accepted_risks:
            statuses.append("accepted_risk")
        if not policy.allow_false_positives:
            statuses.append("false_positive")

        qs = SecureWiseFinding.objects.filter(project=scan.project, status__in=statuses)
        if policy.fail_on_new_findings_only:
            qs = qs.filter(id__in=new_finding_ids)

        if policy.fail_on_secrets and qs.filter(scanner_type="secrets").exists():
            return False

        severity_order = ["critical", "high", "medium", "low", "info"]
        fail_idx = severity_order.index(policy.fail_on_severity)
        if qs.filter(severity__in=severity_order[: fail_idx + 1]).exists():
            return False

        critical_count = qs.filter(severity="critical").count()
        high_count = qs.filter(severity="high").count()
        medium_count = qs.filter(severity="medium").count()
        if critical_count > policy.max_critical:
            return False
        if high_count > policy.max_high:
            return False
        if policy.max_medium >= 0 and medium_count > policy.max_medium:
            return False
        return True
