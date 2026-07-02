"""
IaC engine: real trivy config scan via subprocess when available, else a
fallback that inspects Dockerfiles, Kubernetes YAML, and Terraform files.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
from pathlib import Path

from .base import BaseScanner, ScannerFinding, ScannerResult
from .parsers.trivy_parser import parse_trivy_config_json
from .recommendation import RecommendationEngine

logger = logging.getLogger(__name__)

_DOCKERFILE_NAMES = {"Dockerfile", "dockerfile"}
_K8S_HINT_RE = re.compile(r"^\s*(apiVersion|kind):\s*", re.MULTILINE)


def _find_iac_files(repo_path: Path) -> dict[str, list[Path]]:
    files: dict[str, list[Path]] = {"dockerfile": [], "k8s": [], "terraform": [], "helm": []}
    if not repo_path.exists():
        return files
    for path in repo_path.rglob("*"):
        if not path.is_file() or ".git" in path.parts:
            continue
        if path.name in _DOCKERFILE_NAMES or path.name.startswith("Dockerfile."):
            files["dockerfile"].append(path)
        elif path.suffix in (".yaml", ".yml"):
            try:
                text = path.read_text(errors="ignore")
            except OSError:
                continue
            if path.name in ("values.yaml",) or "helm" in str(path).lower():
                files["helm"].append(path)
            elif _K8S_HINT_RE.search(text):
                files["k8s"].append(path)
        elif path.suffix == ".tf":
            files["terraform"].append(path)
    return files


class IacScanner(BaseScanner):
    scanner_type = "iac"

    def is_available(self) -> bool:
        return True

    def run(self, repo_path: Path, scan_id: str, metadata: dict) -> ScannerResult:
        if shutil.which("trivy"):
            return self._run_trivy(repo_path, scan_id)
        return self._run_fallback(repo_path, scan_id)

    def _run_trivy(self, repo_path: Path, scan_id: str) -> ScannerResult:
        try:
            proc = subprocess.run(
                ["trivy", "config", "--format", "json", str(repo_path)],
                capture_output=True,
                timeout=120,
            )
            data = json.loads(proc.stdout or b"{}")
            findings = parse_trivy_config_json(data, scan_id)
            return ScannerResult(success=True, findings=findings, metadata={"raw_tool": "trivy"})
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("trivy config run failed, falling back")
            return self._run_fallback(repo_path, scan_id, error=str(exc))

    def _run_fallback(self, repo_path: Path, scan_id: str, error: str = "") -> ScannerResult:
        iac_files = _find_iac_files(repo_path)
        total_files = sum(len(v) for v in iac_files.values())
        if total_files == 0:
            return ScannerResult(
                success=True,
                findings=[],
                status="skipped",
                skipped_reason="no IaC files found",
                metadata={"raw_tool": "fallback-iac-checks", "files_scanned": 0, "note": error or None},
            )

        findings: list[ScannerFinding] = []
        for path in iac_files["dockerfile"]:
            findings.extend(self._check_dockerfile(path, repo_path))
        for path in iac_files["k8s"]:
            findings.extend(self._check_k8s(path, repo_path))
        for path in iac_files["terraform"]:
            findings.extend(self._check_terraform(path, repo_path))
        for path in iac_files["helm"]:
            findings.extend(self._check_helm(path, repo_path))

        return ScannerResult(
            success=True,
            findings=findings,
            metadata={"raw_tool": "fallback-iac-checks", "files_scanned": total_files, "note": error or None},
        )

    # ------------------------------------------------------------------
    def _make_finding(self, issue_key: str, rel_path: str, line_number: int | None = None) -> ScannerFinding:
        rec = RecommendationEngine.get_recommendation(issue_key, "generic")
        return ScannerFinding(
            title=rec["what"],
            description=rec["why"],
            severity="medium",
            confidence="medium",
            scanner_type="iac",
            file_path=rel_path,
            line_number=line_number,
            cwe_id=rec["cwe_id"],
            owasp_category=rec["owasp_category"],
            recommendation=rec["recommendation"],
            bad_code_example=rec["bad_code_example"],
            fixed_code_example=rec["fixed_code_example"],
            evidence={"raw_tool": "fallback-iac-checks", "issue_key": issue_key},
            fingerprint=f"fallback-iac-{issue_key}-{rel_path}",
        )

    def _check_dockerfile(self, path: Path, repo_path: Path) -> list[ScannerFinding]:
        findings = []
        rel_path = str(path.relative_to(repo_path))
        try:
            text = path.read_text(errors="ignore")
        except OSError:
            return findings
        if "USER " not in text:
            findings.append(self._make_finding("insecure_dockerfile", rel_path))
        if re.search(r"^\s*ADD\s+\S", text, re.MULTILINE) and not re.search(r"^\s*ADD\s+https?://", text, re.MULTILINE):
            f = self._make_finding("insecure_dockerfile", rel_path)
            f.title = "Dockerfile uses ADD instead of COPY for local files"
            f.fingerprint += "-add"
            findings.append(f)
        for match in re.finditer(r"^\s*FROM\s+(\S+)", text, re.MULTILINE):
            image = match.group(1)
            if ":" not in image or image.endswith(":latest"):
                f = self._make_finding("insecure_dockerfile", rel_path)
                f.title = f"Unpinned base image tag: {image}"
                f.fingerprint += f"-{image}"
                findings.append(f)
        return findings

    def _check_k8s(self, path: Path, repo_path: Path) -> list[ScannerFinding]:
        findings = []
        rel_path = str(path.relative_to(repo_path))
        try:
            text = path.read_text(errors="ignore")
        except OSError:
            return findings
        if re.search(r"privileged:\s*true", text):
            findings.append(self._make_finding("k8s_privileged_container", rel_path))
        if re.search(r"hostNetwork:\s*true", text):
            f = self._make_finding("k8s_privileged_container", rel_path)
            f.title = "Pod spec sets hostNetwork: true"
            f.fingerprint += "-hostnetwork"
            findings.append(f)
        if "resources:" not in text or "limits:" not in text:
            f = self._make_finding("k8s_privileged_container", rel_path)
            f.title = "Container spec missing resource limits"
            f.fingerprint += "-nolimits"
            f.severity = "low"
            findings.append(f)
        return findings

    def _check_terraform(self, path: Path, repo_path: Path) -> list[ScannerFinding]:
        findings = []
        rel_path = str(path.relative_to(repo_path))
        try:
            text = path.read_text(errors="ignore")
        except OSError:
            return findings
        if "0.0.0.0/0" in text and re.search(r"ingress", text, re.IGNORECASE):
            findings.append(self._make_finding("iac_misconfiguration", rel_path))
        if re.search(r'acl\s*=\s*"public-read"', text):
            f = self._make_finding("iac_misconfiguration", rel_path)
            f.title = "Terraform resource configured with public-read ACL"
            f.fingerprint += "-acl"
            findings.append(f)
        return findings

    def _check_helm(self, path: Path, repo_path: Path) -> list[ScannerFinding]:
        findings = []
        rel_path = str(path.relative_to(repo_path))
        try:
            text = path.read_text(errors="ignore")
        except OSError:
            return findings
        if re.search(r"privileged:\s*true", text):
            findings.append(self._make_finding("k8s_privileged_container", rel_path))
        return findings
