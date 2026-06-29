"""
SecureWise — report generation service.
"""

from __future__ import annotations

import logging
from collections import defaultdict

from django.utils import timezone

logger = logging.getLogger(__name__)


def generate_json_report(scan) -> dict:
    """Build a JSON report dict from a completed scan."""
    from apps.securewise.models import SecureWiseFinding  # noqa: F401 — unused but kept for future use

    # findings already loaded via the scan relation

    findings = list(scan.findings.all())

    severity_counts: dict[str, int] = defaultdict(int)
    cwe_map: dict[str, list] = defaultdict(list)
    owasp_map: dict[str, list] = defaultdict(list)
    findings_data = []

    for f in findings:
        severity_counts[f.severity] += 1
        if f.cwe_id:
            cwe_map[f.cwe_id].append(f.title)
        if f.owasp_category:
            owasp_map[f.owasp_category].append(f.title)
        findings_data.append(
            {
                "id": str(f.id),
                "title": f.title,
                "severity": f.severity,
                "confidence": f.confidence,
                "status": f.status,
                "cwe_id": f.cwe_id,
                "owasp_category": f.owasp_category,
                "file_path": f.file_path,
                "line_number": f.line_number,
                "endpoint": f.endpoint,
                "scanner_type": f.scanner_type,
                "description": f.description,
                "recommendation": f.recommendation,
                "bad_code_example": f.bad_code_example,
                "fixed_code_example": f.fixed_code_example,
                "ai_fix_suggestion": f.ai_fix_suggestion,
            }
        )

    total = len(findings)
    return {
        "report_version": "1.0",
        "generated_at": timezone.now().isoformat(),
        "project": {
            "id": str(scan.project.id),
            "name": scan.project.name,
            "organization": scan.project.organization.name,
        },
        "scan": {
            "id": str(scan.id),
            "type": scan.scan_type,
            "branch": scan.branch,
            "commit_sha": scan.commit_sha,
            "started_at": scan.started_at.isoformat() if scan.started_at else None,
            "completed_at": scan.completed_at.isoformat() if scan.completed_at else None,
            "duration_seconds": scan.duration_seconds,
        },
        "summary": {
            "total_findings": total,
            "open_findings": sum(1 for f in findings if f.status == "open"),
            "fixed_findings": sum(1 for f in findings if f.status == "fixed"),
        },
        "severity_counts": dict(severity_counts),
        "cwe_mapping": {k: list(set(v)) for k, v in cwe_map.items()},
        "owasp_mapping": {k: list(set(v)) for k, v in owasp_map.items()},
        "quality_gate": {
            "passed": scan.quality_gate_passed,
        },
        "findings": findings_data,
        "recommended_fixes": [
            {
                "title": f["title"],
                "recommendation": f["recommendation"],
                "ai_fix_suggestion": f["ai_fix_suggestion"],
            }
            for f in findings_data
            if f.get("recommendation") or f.get("ai_fix_suggestion")
        ],
    }
