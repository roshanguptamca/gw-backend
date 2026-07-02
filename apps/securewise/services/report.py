"""
SecureWise — report generation service.
"""

from __future__ import annotations

import logging
from collections import defaultdict

from django.utils import timezone

logger = logging.getLogger(__name__)

REPORT_TYPES = (
    "owasp_top10",
    "cwe_top25",
    "security_summary",
    "executive_summary",
    "developer_remediation",
    "quality_gate",
)

# The stable, currently-published OWASP Top 10 edition (2021) — used as the
# canonical category set for "owasp_top10" style reports.
_OWASP_TOP10_LABELS = {
    "A01:2021": "Broken Access Control",
    "A02:2021": "Cryptographic Failures",
    "A03:2021": "Injection",
    "A04:2021": "Insecure Design",
    "A05:2021": "Security Misconfiguration",
    "A06:2021": "Vulnerable and Outdated Components",
    "A07:2021": "Identification and Authentication Failures",
    "A08:2021": "Software and Data Integrity Failures",
    "A09:2021": "Security Logging and Monitoring Failures",
    "A10:2021": "Server-Side Request Forgery (SSRF)",
}

# A representative slice of the CWE Top 25 Most Dangerous Software Weaknesses.
_CWE_TOP25 = {
    "CWE-79", "CWE-787", "CWE-89", "CWE-352", "CWE-22", "CWE-125", "CWE-78",
    "CWE-416", "CWE-862", "CWE-434", "CWE-94", "CWE-20", "CWE-77", "CWE-287",
    "CWE-269", "CWE-502", "CWE-798", "CWE-918", "CWE-611", "CWE-476",
    "CWE-327", "CWE-190", "CWE-400", "CWE-306", "CWE-863",
}


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


def build_owasp_top10_report(scan) -> dict:
    """Group findings by OWASP Top 10 2021 category with coverage counts."""
    findings = list(scan.findings.all())
    by_category: dict[str, list] = defaultdict(list)
    for f in findings:
        if f.owasp_category:
            by_category[f.owasp_category].append(
                {"id": str(f.id), "title": f.title, "severity": f.severity, "file_path": f.file_path}
            )
    coverage = {
        code: {"label": label, "count": len(by_category.get(code, []))}
        for code, label in _OWASP_TOP10_LABELS.items()
    }
    return {
        "report_type": "owasp_top10",
        "generated_at": timezone.now().isoformat(),
        "scan_id": str(scan.id),
        "coverage": coverage,
        "findings_by_category": dict(by_category),
        "uncategorized_findings": sum(1 for f in findings if not f.owasp_category),
    }


def build_cwe_top25_report(scan) -> dict:
    """Highlight which CWE Top 25 weaknesses were found in this scan."""
    findings = list(scan.findings.all())
    matched: dict[str, list] = defaultdict(list)
    other_cwes: dict[str, list] = defaultdict(list)
    for f in findings:
        if not f.cwe_id:
            continue
        target = matched if f.cwe_id in _CWE_TOP25 else other_cwes
        target[f.cwe_id].append({"id": str(f.id), "title": f.title, "severity": f.severity})
    return {
        "report_type": "cwe_top25",
        "generated_at": timezone.now().isoformat(),
        "scan_id": str(scan.id),
        "cwe_top25_matches": dict(matched),
        "cwe_top25_coverage_count": len(matched),
        "other_cwes": dict(other_cwes),
    }


def build_security_summary_report(scan) -> dict:
    return generate_json_report(scan)


def build_executive_summary_report(scan) -> dict:
    findings = list(scan.findings.all())
    severity_counts = defaultdict(int)
    for f in findings:
        severity_counts[f.severity] += 1
    critical_high = severity_counts.get("critical", 0) + severity_counts.get("high", 0)
    risk_posture = "High Risk" if critical_high > 5 else "Moderate Risk" if critical_high > 0 else "Low Risk"
    return {
        "report_type": "executive_summary",
        "generated_at": timezone.now().isoformat(),
        "project": scan.project.name,
        "organization": scan.project.organization.name,
        "scan_id": str(scan.id),
        "risk_posture": risk_posture,
        "total_findings": len(findings),
        "critical_high_count": critical_high,
        "severity_counts": dict(severity_counts),
        "quality_gate_passed": scan.quality_gate_passed,
        "top_findings": [
            {"title": f.title, "severity": f.severity, "recommendation": f.recommendation}
            for f in sorted(findings, key=lambda x: ("critical", "high", "medium", "low", "info").index(x.severity))[:5]
        ],
    }


def build_developer_remediation_report(scan) -> dict:
    findings = list(scan.findings.all())
    by_file: dict[str, list] = defaultdict(list)
    for f in findings:
        key = f.file_path or f.endpoint or "unspecified"
        by_file[key].append(
            {
                "title": f.title,
                "severity": f.severity,
                "line_number": f.line_number,
                "recommendation": f.recommendation,
                "bad_code_example": f.bad_code_example,
                "fixed_code_example": f.fixed_code_example,
            }
        )
    return {
        "report_type": "developer_remediation",
        "generated_at": timezone.now().isoformat(),
        "scan_id": str(scan.id),
        "remediation_by_file": dict(by_file),
        "total_actionable_items": len(findings),
    }


def build_quality_gate_report(scan) -> dict:
    policy = scan.policy
    findings = list(scan.findings.all())
    severity_counts = defaultdict(int)
    for f in findings:
        severity_counts[f.severity] += 1
    return {
        "report_type": "quality_gate",
        "generated_at": timezone.now().isoformat(),
        "scan_id": str(scan.id),
        "quality_gate_passed": scan.quality_gate_passed,
        "policy": {
            "name": policy.name,
            "fail_on_severity": policy.fail_on_severity,
            "max_critical": policy.max_critical,
            "max_high": policy.max_high,
        }
        if policy
        else None,
        "severity_counts": dict(severity_counts),
    }


_REPORT_BUILDERS = {
    "owasp_top10": build_owasp_top10_report,
    "cwe_top25": build_cwe_top25_report,
    "security_summary": build_security_summary_report,
    "executive_summary": build_executive_summary_report,
    "developer_remediation": build_developer_remediation_report,
    "quality_gate": build_quality_gate_report,
}


def generate_report(scan, report_type: str = "") -> dict:
    """Dispatch to the correct report builder; default to the full JSON report."""
    builder = _REPORT_BUILDERS.get(report_type)
    if builder is None:
        return generate_json_report(scan)
    return builder(scan)
