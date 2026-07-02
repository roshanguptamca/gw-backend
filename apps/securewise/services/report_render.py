from __future__ import annotations

import logging

from django.template.loader import render_to_string

logger = logging.getLogger(__name__)


def _build_report_context(report) -> dict:
    report_data = report.report_data or {}
    scan = report.scan
    findings = report_data.get("findings", [])
    severity_counts = report_data.get("severity_counts", {})

    return {
        "report": report,
        "report_data": report_data,
        "report_title": report.title,
        "report_format": report.format,
        "generated_at": report_data.get("generated_at") or report.created_at,
        "project_name": report_data.get("project", {}).get("name") or getattr(report.project, "name", ""),
        "organization_name": report_data.get("project", {}).get("organization")
        or getattr(getattr(report.project, "organization", None), "name", ""),
        "scan_id": report_data.get("scan", {}).get("id") or report_data.get("scan_id") or getattr(scan, "id", ""),
        "scan_type": report_data.get("scan", {}).get("type") or getattr(scan, "scan_type", ""),
        "scan_branch": report_data.get("scan", {}).get("branch") or getattr(scan, "branch", ""),
        "scan_commit_sha": report_data.get("scan", {}).get("commit_sha") or getattr(scan, "commit_sha", ""),
        "scan_started_at": report_data.get("scan", {}).get("started_at") or getattr(scan, "started_at", None),
        "scan_completed_at": report_data.get("scan", {}).get("completed_at") or getattr(scan, "completed_at", None),
        "repository_name": getattr(getattr(scan, "repository", None), "name", ""),
        "repository_url": getattr(getattr(scan, "repository", None), "repository_url", ""),
        "severity_counts": severity_counts,
        "findings": findings,
        "report_type": report_data.get("report_type", "security_summary"),
        "quality_gate_passed": report_data.get("quality_gate", {}).get("passed", report_data.get("quality_gate_passed")),
        "owasp_mapping": report_data.get("owasp_mapping", {}),
        "cwe_mapping": report_data.get("cwe_mapping", {}),
        "owasp_coverage": report_data.get("coverage", {}),
        "owasp_findings_by_category": report_data.get("findings_by_category", {}),
        "cwe_top25_matches": report_data.get("cwe_top25_matches", {}),
        "other_cwes": report_data.get("other_cwes", {}),
        "quality_gate_policy": report_data.get("policy"),
        "recommended_fixes": report_data.get("recommended_fixes", []),
        "top_findings": report_data.get("top_findings", []),
        "remediation_by_file": report_data.get("remediation_by_file", {}),
        "summary": report_data.get("summary", {}),
        "risk_posture": report_data.get("risk_posture", ""),
        "critical_high_count": report_data.get("critical_high_count"),
        "total_findings": report_data.get("total_findings", len(findings)),
    }


def render_report_html(report) -> str:
    return render_to_string("securewise/reports/report_detail.html", _build_report_context(report))


def render_report_pdf(report) -> bytes:
    html = render_report_html(report)
    try:
        from weasyprint import HTML

        return HTML(string=html).write_pdf()
    except Exception as exc:  # pragma: no cover - depends on system renderer
        logger.exception("SecureWise PDF rendering failed for report %s", report.id)
        raise RuntimeError("SecureWise PDF rendering is unavailable right now.") from exc
