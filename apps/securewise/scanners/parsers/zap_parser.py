"""
Parse OWASP ZAP JSON report output (e.g. from zap-baseline.py -J report.json)
into ScannerFinding objects.

Not exercised by default scanning (ZAP is not installed in this environment)
but implemented and unit-tested against a small sample fixture so it is
ready to use once ZAP is available.
"""

from __future__ import annotations

from ..base import ScannerFinding

_RISK_MAP = {
    "High": "high",
    "Medium": "medium",
    "Low": "low",
    "Informational": "info",
}


def parse_zap_json(data: dict, scan_id: str) -> list[ScannerFinding]:
    findings: list[ScannerFinding] = []
    for site in data.get("site", []) or []:
        for alert in site.get("alerts", []) or []:
            risk = alert.get("riskdesc", "Medium").split(" ")[0]
            severity = _RISK_MAP.get(risk, "medium")
            instances = alert.get("instances", []) or []
            endpoint = instances[0].get("uri", "") if instances else ""
            findings.append(
                ScannerFinding(
                    title=alert.get("name", "DAST finding"),
                    description=alert.get("desc", ""),
                    severity=severity,
                    confidence="high",
                    scanner_type="dast",
                    endpoint=endpoint,
                    recommendation=alert.get("solution", ""),
                    evidence={"raw_tool": "zap", "plugin_id": alert.get("pluginid")},
                    fingerprint=f"zap-{alert.get('pluginid')}-{endpoint}",
                )
            )
    return findings
