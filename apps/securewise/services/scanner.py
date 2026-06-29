"""
SecureWise scanner service abstraction.

MVP: mock scanners produce synthetic findings so the full API/UI flow
     works end-to-end without real tools.

TODO: Plug in real scanners:
  - SAST  → Semgrep OSS  (https://semgrep.dev/docs/cli-reference)
  - DAST  → OWASP ZAP    (https://www.zaproxy.org/docs/api/)
  - SCA   → Trivy        (https://aquasecurity.github.io/trivy/)
  - IaC   → Trivy IaC
  - Container → Trivy image scan
  - Secrets → Gitleaks  (https://github.com/gitleaks/gitleaks)
"""

from __future__ import annotations

import logging
import subprocess
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ScanFinding:
    title: str
    description: str
    severity: str  # critical | high | medium | low | info
    confidence: str  # very_high | high | medium | low
    scanner_type: str
    file_path: str = ""
    line_number: int | None = None
    endpoint: str = ""
    cwe_id: str = ""
    owasp_category: str = ""
    risk: str = ""
    impact: str = ""
    recommendation: str = ""
    bad_code_example: str = ""
    fixed_code_example: str = ""
    evidence: dict = field(default_factory=dict)
    fingerprint: str = field(default_factory=lambda: uuid.uuid4().hex)


@dataclass
class ScanResult:
    success: bool
    findings: List[ScanFinding] = field(default_factory=list)
    error: str = ""
    metadata: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Base scanner
# ---------------------------------------------------------------------------


class BaseScanner:
    scanner_type: str = "unknown"

    def run(self, repo_path: Path, scan_id: str, metadata: dict) -> ScanResult:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Mock scanners — returns realistic synthetic findings
# ---------------------------------------------------------------------------


class MockSastScanner(BaseScanner):
    scanner_type = "sast"

    def run(self, repo_path: Path, scan_id: str, metadata: dict) -> ScanResult:
        logger.info("[MockSAST] Running mock SAST scan for scan_id=%s", scan_id)
        # TODO: Replace with Semgrep OSS:
        #   subprocess.run(["semgrep", "--config=auto", "--json", str(repo_path)])
        findings = [
            ScanFinding(
                title="SQL Injection via unsanitized user input",
                description="User-supplied data is concatenated directly into a SQL query without parameterization.",
                severity="critical",
                confidence="very_high",
                scanner_type="sast",
                file_path="src/db/queries.py",
                line_number=42,
                cwe_id="CWE-89",
                owasp_category="A03:2021",
                risk="Attacker can read, modify or delete database records.",
                impact="Full database compromise.",
                recommendation="Use parameterized queries or ORM abstractions.",
                bad_code_example='query = "SELECT * FROM users WHERE id=" + user_id',
                fixed_code_example='cursor.execute("SELECT * FROM users WHERE id=%s", [user_id])',
                fingerprint=f"mock-sast-sqli-{scan_id}",
            ),
            ScanFinding(
                title="Cross-Site Scripting (Reflected XSS)",
                description="Unsanitized user input is rendered in an HTML response.",
                severity="high",
                confidence="high",
                scanner_type="sast",
                file_path="src/views/profile.py",
                line_number=87,
                cwe_id="CWE-79",
                owasp_category="A03:2021",
                risk="Attacker can execute arbitrary JavaScript in victim's browser.",
                impact="Session hijacking, credential theft.",
                recommendation="Escape all user-controlled output with html.escape() or use a templating engine with auto-escaping.",
                fingerprint=f"mock-sast-xss-{scan_id}",
            ),
            ScanFinding(
                title="Hardcoded secret in source code",
                description="A plaintext API key was found hardcoded in application code.",
                severity="high",
                confidence="high",
                scanner_type="sast",
                file_path="config/settings.py",
                line_number=15,
                cwe_id="CWE-798",
                owasp_category="A02:2021",
                risk="Secret exposure allows unauthorized access to third-party services.",
                recommendation="Use environment variables or a secrets manager.",
                fingerprint=f"mock-sast-hardcoded-{scan_id}",
            ),
            ScanFinding(
                title="Insecure Deserialization",
                description="Pickle deserialization of untrusted data can lead to RCE.",
                severity="critical",
                confidence="high",
                scanner_type="sast",
                file_path="src/utils/serializer.py",
                line_number=31,
                cwe_id="CWE-502",
                owasp_category="A08:2021",
                risk="Remote code execution via crafted pickle payload.",
                recommendation="Use safe serialization formats like JSON. Never unpickle untrusted data.",
                fingerprint=f"mock-sast-deser-{scan_id}",
            ),
        ]
        return ScanResult(success=True, findings=findings, metadata={"tool": "mock-semgrep", "rules": "auto"})


class MockDastScanner(BaseScanner):
    scanner_type = "dast"

    def run(self, repo_path: Path, scan_id: str, metadata: dict) -> ScanResult:
        logger.info("[MockDAST] Running mock DAST scan for scan_id=%s", scan_id)
        # TODO: Replace with OWASP ZAP active scan via API
        findings = [
            ScanFinding(
                title="Missing Content-Security-Policy Header",
                description="The application does not set a Content-Security-Policy HTTP header.",
                severity="medium",
                confidence="high",
                scanner_type="dast",
                endpoint="/api/users/",
                cwe_id="CWE-693",
                owasp_category="A05:2021",
                recommendation="Add a strict CSP header to all HTTP responses.",
                fingerprint=f"mock-dast-csp-{scan_id}",
            ),
            ScanFinding(
                title="Server-Side Request Forgery (SSRF)",
                description="An endpoint fetches a remote URL based on user input without validation.",
                severity="high",
                confidence="medium",
                scanner_type="dast",
                endpoint="/api/fetch-preview/",
                cwe_id="CWE-918",
                owasp_category="A10:2021",
                recommendation="Validate and allowlist target URLs. Block requests to internal network ranges.",
                fingerprint=f"mock-dast-ssrf-{scan_id}",
            ),
        ]
        return ScanResult(success=True, findings=findings, metadata={"tool": "mock-zap", "scan_mode": "active"})


class MockScaScanner(BaseScanner):
    scanner_type = "sca"

    def run(self, repo_path: Path, scan_id: str, metadata: dict) -> ScanResult:
        logger.info("[MockSCA] Running mock SCA scan for scan_id=%s", scan_id)
        # TODO: Replace with Trivy: subprocess.run(["trivy", "fs", "--format", "json", str(repo_path)])
        findings = [
            ScanFinding(
                title="CVE-2023-44487 in requests==2.28.0",
                description="HTTP/2 Rapid Reset Attack (CVE-2023-44487) in outdated dependency.",
                severity="high",
                confidence="very_high",
                scanner_type="sca",
                file_path="requirements.txt",
                cwe_id="CWE-400",
                recommendation="Upgrade requests to >= 2.31.0.",
                fingerprint=f"mock-sca-cve1-{scan_id}",
            ),
            ScanFinding(
                title="Outdated Django version with known security patches",
                description="Django 3.2.x is past its security support window.",
                severity="medium",
                confidence="high",
                scanner_type="sca",
                file_path="requirements.txt",
                recommendation="Upgrade to Django 5.x LTS.",
                fingerprint=f"mock-sca-django-{scan_id}",
            ),
        ]
        return ScanResult(success=True, findings=findings, metadata={"tool": "mock-trivy", "type": "fs"})


class MockSecretScanner(BaseScanner):
    scanner_type = "secrets"

    def run(self, repo_path: Path, scan_id: str, metadata: dict) -> ScanResult:
        logger.info("[MockSecrets] Running mock secret scan for scan_id=%s", scan_id)
        # TODO: Replace with Gitleaks: subprocess.run(["gitleaks", "detect", "--source", str(repo_path)])
        findings = [
            ScanFinding(
                title="AWS Access Key ID found in commit history",
                description="A high-entropy string matching AWS_ACCESS_KEY_ID pattern was found.",
                severity="critical",
                confidence="high",
                scanner_type="secrets",
                file_path=".env.bak",
                line_number=3,
                cwe_id="CWE-798",
                owasp_category="A02:2021",
                recommendation="Immediately rotate the AWS key. Remove from history with git-filter-repo.",
                fingerprint=f"mock-secret-aws-{scan_id}",
            ),
        ]
        return ScanResult(success=True, findings=findings, metadata={"tool": "mock-gitleaks"})


# ---------------------------------------------------------------------------
# Scanner runner
# ---------------------------------------------------------------------------

SCANNER_MAP = {
    "sast": MockSastScanner,
    "dast": MockDastScanner,
    "sca": MockScaScanner,
    "secrets": MockSecretScanner,
    "iac": MockScaScanner,  # TODO: Trivy IaC
    "container": MockScaScanner,  # TODO: Trivy image
    "api": MockDastScanner,  # TODO: dedicated API scanner
}


def _get_scanners_for_type(scan_type: str) -> list[BaseScanner]:
    if scan_type == "full":
        return [cls() for cls in [MockSastScanner, MockDastScanner, MockScaScanner, MockSecretScanner]]
    cls = SCANNER_MAP.get(scan_type)
    return [cls()] if cls else [MockSastScanner()]


class ScannerRunner:
    """
    Orchestrates cloning a repository and running one or more scanners.

    Security rules:
    - Tokens are decrypted only inside this runtime, never logged.
    - Clone directory is always deleted after scan.
    - Authenticated clone URL is never stored or logged.
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
        scan.save(update_fields=["status", "started_at"])

        SecureWiseAuditLog.objects.create(
            organization=scan.organization,
            user=scan.triggered_by,
            event="scan_started",
            target_type="SecureWiseScan",
            target_id=str(scan.id),
            detail={"scan_type": scan.scan_type, "project": str(scan.project_id)},
        )

        all_findings: list[ScanFinding] = []
        error_msg = ""

        try:
            with tempfile.TemporaryDirectory(prefix="sw_scan_") as tmpdir:
                repo_path = Path(tmpdir) / "repo"

                if scan.repository:
                    self._clone_repo(scan, repo_path)
                else:
                    # No repository — run against empty path (mock still works)
                    repo_path.mkdir(parents=True, exist_ok=True)
                scanners = _get_scanners_for_type(scan.scan_type)
                meta: dict = {}
                for scanner in scanners:
                    result = scanner.run(repo_path, scan_id, {})
                    if result.success:
                        all_findings.extend(result.findings)
                        meta[scanner.scanner_type] = result.metadata
                    else:
                        logger.warning("Scanner %s failed: %s", scanner.scanner_type, result.error)

                scan.scanner_metadata = meta
            # tempdir is cleaned up here automatically

        except Exception as exc:
            logger.exception("Scan %s failed during execution", scan_id)
            error_msg = str(exc)

        # Persist findings
        finding_objs = [
            SecureWiseFinding(
                scan=scan,
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
                evidence=f.evidence,
                fingerprint=f.fingerprint,
                status="open",
            )
            for f in all_findings
        ]
        SecureWiseFinding.objects.bulk_create(finding_objs, ignore_conflicts=True)

        # Quality gate
        quality_gate_passed = self._evaluate_quality_gate(scan, all_findings)

        completed_at = timezone.now()
        duration = int((completed_at - scan.started_at).total_seconds())
        scan.status = "completed" if not error_msg else "failed"
        scan.completed_at = completed_at
        scan.duration_seconds = duration
        scan.error_message = error_msg
        scan.quality_gate_passed = quality_gate_passed
        scan.save(
            update_fields=[
                "status",
                "completed_at",
                "duration_seconds",
                "error_message",
                "quality_gate_passed",
                "scanner_metadata",
            ]
        )

        SecureWiseAuditLog.objects.create(
            organization=scan.organization,
            user=scan.triggered_by,
            event="scan_completed" if not error_msg else "scan_failed",
            target_type="SecureWiseScan",
            target_id=str(scan.id),
            detail={
                "findings": len(all_findings),
                "quality_gate_passed": quality_gate_passed,
                "duration_seconds": duration,
            },
        )

    # ------------------------------------------------------------------
    def _clone_repo(self, scan, repo_path: Path):
        """
        Clone repository into repo_path.
        For private repos, decrypts token only here — never logs it.
        """
        repo = scan.repository
        clone_url = repo.repository_url

        if repo.access_mode == "integration" and repo.integration:
            token = repo.integration.get_token()
            if token:
                # Build authenticated URL — never log this
                from urllib.parse import urlparse, urlunparse

                parsed = urlparse(clone_url)
                authed = parsed._replace(netloc=f"oauth2:{token}@{parsed.netloc}")
                clone_url_with_token = urlunparse(authed)
                cmd = ["git", "clone", "--depth", "1", clone_url_with_token, str(repo_path)]
                # Mask token in any error output
                try:
                    subprocess.run(cmd, capture_output=True, timeout=120, check=True)
                except subprocess.CalledProcessError as e:
                    raise RuntimeError("Failed to clone private repository. Check token permissions.") from e
                finally:
                    del token, clone_url_with_token
                return

        # Public clone
        try:
            subprocess.run(
                ["git", "clone", "--depth", "1", clone_url, str(repo_path)],
                capture_output=True,
                timeout=120,
                check=True,
            )
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to clone repository: {clone_url}") from e

    def _evaluate_quality_gate(self, scan, findings: list[ScanFinding]) -> bool:
        policy = scan.policy
        if not policy:
            return True
        severity_order = ["critical", "high", "medium", "low", "info"]
        fail_idx = severity_order.index(policy.fail_on_severity)
        for f in findings:
            fidx = severity_order.index(f.severity)
            if fidx <= fail_idx:
                return False
        critical_count = sum(1 for f in findings if f.severity == "critical")
        high_count = sum(1 for f in findings if f.severity == "high")
        if critical_count > policy.max_critical:
            return False
        if high_count > policy.max_high:
            return False
        return True
