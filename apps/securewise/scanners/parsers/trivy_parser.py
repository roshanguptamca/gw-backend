"""Parse `trivy` JSON output (fs vuln scan and config/IaC scan) into ScannerFinding objects."""

from __future__ import annotations

from ..base import ScannerFinding

_SEVERITY_MAP = {
    "CRITICAL": "critical",
    "HIGH": "high",
    "MEDIUM": "medium",
    "LOW": "low",
    "UNKNOWN": "info",
}


def parse_trivy_vuln_json(data: dict, scan_id: str) -> list[ScannerFinding]:
    findings: list[ScannerFinding] = []
    for result in data.get("Results", []) or []:
        target = result.get("Target", "")
        for vuln in result.get("Vulnerabilities", []) or []:
            severity = _SEVERITY_MAP.get(vuln.get("Severity", "MEDIUM"), "medium")
            findings.append(
                ScannerFinding(
                    title=f"{vuln.get('VulnerabilityID')} in {vuln.get('PkgName')}=={vuln.get('InstalledVersion')}",
                    description=vuln.get("Description", "") or vuln.get("Title", ""),
                    severity=severity,
                    confidence="very_high",
                    scanner_type="sca",
                    file_path=target,
                    recommendation=(
                        f"Upgrade {vuln.get('PkgName')} to {vuln.get('FixedVersion')}."
                        if vuln.get("FixedVersion")
                        else "No fixed version published yet; monitor the advisory."
                    ),
                    evidence={"raw_tool": "trivy", "vulnerability_id": vuln.get("VulnerabilityID")},
                    fingerprint=f"trivy-{vuln.get('VulnerabilityID')}-{vuln.get('PkgName')}",
                )
            )
    return findings


def parse_trivy_config_json(data: dict, scan_id: str) -> list[ScannerFinding]:
    findings: list[ScannerFinding] = []
    for result in data.get("Results", []) or []:
        target = result.get("Target", "")
        for mis in result.get("Misconfigurations", []) or []:
            severity = _SEVERITY_MAP.get(mis.get("Severity", "MEDIUM"), "medium")
            findings.append(
                ScannerFinding(
                    title=mis.get("Title", "IaC misconfiguration"),
                    description=mis.get("Description", "") or mis.get("Message", ""),
                    severity=severity,
                    confidence="high",
                    scanner_type="iac",
                    file_path=target,
                    recommendation=mis.get("Resolution", ""),
                    cwe_id="CWE-16",
                    evidence={"raw_tool": "trivy", "id": mis.get("ID")},
                    fingerprint=f"trivy-iac-{mis.get('ID')}-{target}",
                )
            )
    return findings
