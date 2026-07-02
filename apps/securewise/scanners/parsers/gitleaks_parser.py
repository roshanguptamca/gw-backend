"""Parse `gitleaks detect --report-format json` output into ScannerFinding objects."""

from __future__ import annotations

from ..base import ScannerFinding


def _mask_secret(secret: str) -> str:
    if not secret:
        return ""
    if len(secret) <= 4:
        return "*" * len(secret)
    return "*" * (len(secret) - 4) + secret[-4:]


def parse_gitleaks_json(data: list, scan_id: str) -> list[ScannerFinding]:
    findings: list[ScannerFinding] = []
    for item in data or []:
        secret = item.get("Secret", "")
        rule_id = item.get("RuleID", "secret")
        file_path = item.get("File", "")
        line_number = item.get("StartLine")
        commit = item.get("Commit", "")
        findings.append(
            ScannerFinding(
                title=f"Leaked secret detected: {rule_id}",
                description=item.get("Description", f"gitleaks rule '{rule_id}' matched a potential secret."),
                severity="critical",
                confidence="high",
                scanner_type="secrets",
                file_path=file_path,
                line_number=line_number,
                cwe_id="CWE-798",
                owasp_category="A02:2021",
                recommendation="Rotate the exposed credential immediately and remove it from git history.",
                evidence={
                    "raw_tool": "gitleaks",
                    "rule_id": rule_id,
                    "secret_masked": _mask_secret(secret),
                    "commit": commit,
                },
                fingerprint=f"gitleaks-{rule_id}-{file_path}-{line_number}",
            )
        )
    return findings
