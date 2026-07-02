"""Parse `semgrep --json` output into ScannerFinding objects."""

from __future__ import annotations

from ..base import ScannerFinding

_SEVERITY_MAP = {
    "ERROR": "high",
    "WARNING": "medium",
    "INFO": "low",
}


def parse_semgrep_json(data: dict, scan_id: str) -> list[ScannerFinding]:
    findings: list[ScannerFinding] = []
    for result in data.get("results", []):
        extra = result.get("extra", {}) or {}
        metadata = extra.get("metadata", {}) or {}
        severity = _SEVERITY_MAP.get(extra.get("severity", "WARNING"), "medium")
        cwe = metadata.get("cwe")
        cwe_id = ""
        if isinstance(cwe, list) and cwe:
            cwe_id = str(cwe[0]).split(":")[0].strip() if ":" not in str(cwe[0]) else str(cwe[0]).split(":")[0]
            cwe_id = str(cwe[0]) if str(cwe[0]).startswith("CWE-") else cwe_id
        elif isinstance(cwe, str):
            cwe_id = cwe
        owasp = metadata.get("owasp")
        owasp_category = owasp[0] if isinstance(owasp, list) and owasp else (owasp or "")

        line_start = (result.get("start") or {}).get("line")
        findings.append(
            ScannerFinding(
                title=result.get("check_id", "SAST finding"),
                description=extra.get("message", ""),
                severity=severity,
                confidence="high",
                scanner_type="sast",
                file_path=result.get("path", ""),
                line_number=line_start,
                cwe_id=cwe_id,
                owasp_category=owasp_category,
                evidence={"raw_tool": "semgrep", "check_id": result.get("check_id")},
                fingerprint=f"semgrep-{result.get('check_id')}-{result.get('path')}-{line_start}",
            )
        )
    return findings
