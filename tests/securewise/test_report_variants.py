from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from apps.securewise.services import report


def finding(**overrides):
    return SimpleNamespace(
        **{
            "id": "finding-test",
            "title": "Synthetic finding",
            "severity": "high",
            "file_path": "app.py",
            "endpoint": "/api/items",
            "line_number": 10,
            "cwe_id": "CWE-79",
            "owasp_category": "A03:2021",
            "recommendation": "Escape output",
            "bad_code_example": "unsafe",
            "fixed_code_example": "escaped",
            **overrides,
        }
    )


@pytest.fixture
def scan():
    return SimpleNamespace(
        id="scan-test",
        project=SimpleNamespace(name="Project", organization=SimpleNamespace(name="Organization")),
        findings=Mock(),
        policy=None,
        quality_gate_passed=False,
    )


def test_taxonomy_reports_separate_unmapped_and_uncategorized_findings(scan):
    scan.findings.all.return_value = [
        finding(),
        finding(cwe_id="CWE-unknown", owasp_category=""),
        finding(cwe_id="", owasp_category=""),
    ]
    owasp = report.generate_report(scan, "owasp_top10")
    assert owasp["coverage"]["A03:2021"]["count"] == 1
    assert owasp["uncategorized_findings"] == 2
    cwe = report.generate_report(scan, "cwe_top25")
    assert cwe["cwe_top25_coverage_count"] == 1
    assert cwe["cwe_top25_matches"]["CWE-79"][0]["id"] == "finding-test"
    assert len(cwe["other_cwes"]["CWE-unknown"]) == 1


@pytest.mark.parametrize(("count", "risk"), [(0, "Low Risk"), (1, "Moderate Risk"), (6, "High Risk")])
def test_executive_summary_expresses_risk_and_limits_top_findings(scan, count, risk):
    scan.findings.all.return_value = [finding(severity="high") for _ in range(count)] + [finding(severity="low")]
    data = report.generate_report(scan, "executive_summary")
    assert data["risk_posture"] == risk
    assert data["critical_high_count"] == count
    assert len(data["top_findings"]) == min(count + 1, 5)
    if count:
        assert data["top_findings"][0]["severity"] == "high"


def test_remediation_groups_source_endpoint_and_unspecified_locations(scan):
    scan.findings.all.return_value = [
        finding(),
        finding(file_path=""),
        finding(file_path="", endpoint=""),
    ]
    data = report.generate_report(scan, "developer_remediation")
    assert set(data["remediation_by_file"]) == {"app.py", "/api/items", "unspecified"}
    assert data["total_actionable_items"] == 3
    assert data["remediation_by_file"]["app.py"][0]["fixed_code_example"] == "escaped"


@pytest.mark.parametrize("has_policy", [True, False])
def test_quality_gate_report_preserves_policy_and_result(scan, has_policy):
    scan.findings.all.return_value = [finding()]
    if has_policy:
        scan.policy = SimpleNamespace(name="Strict", fail_on_severity="high", max_critical=0, max_high=0)
    data = report.generate_report(scan, "quality_gate")
    assert data["quality_gate_passed"] is False
    assert data["severity_counts"] == {"high": 1}
    assert (data["policy"]["name"] if has_policy else data["policy"]) == ("Strict" if has_policy else None)
