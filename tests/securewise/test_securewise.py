"""
SecureWise SASP — backend unit tests.
Covers: models, permissions, org isolation, project CRUD,
        scan creation, mock scan execution, findings, report generation.
"""

from django.contrib.auth import get_user_model

import pytest
from unittest.mock import patch

from apps.securewise.models import (
    SecureWiseAuditLog,
    SecureWiseFinding,
    SecureWiseGitIntegration,
    SecureWiseMembership,
    SecureWiseOrganization,
    SecureWiseProject,
    SecureWiseReport,
    SecureWiseRepository,
    SecureWiseScan,
    SecureWiseScanPolicy,
)
from apps.securewise.services.report import generate_json_report
from apps.securewise.services.scanner import ScannerRunner
from apps.securewise.scanners.sast import SastScanner

User = get_user_model()

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def owner(db):
    return User.objects.create_user(username="sw_owner", email="owner@sw.test", password="pass")


@pytest.fixture
def member(db):
    return User.objects.create_user(username="sw_member", email="member@sw.test", password="pass")


@pytest.fixture
def outsider(db):
    return User.objects.create_user(username="sw_outsider", email="outsider@sw.test", password="pass")


@pytest.fixture
def org(owner):
    o = SecureWiseOrganization.objects.create(name="TestOrg", slug="testorg", owner=owner)
    SecureWiseMembership.objects.create(organization=o, user=owner, role="owner")
    return o


@pytest.fixture
def project(org, owner):
    return SecureWiseProject.objects.create(organization=org, name="TestProject", slug="testproject", created_by=owner)


@pytest.fixture
def repository(org, project, owner):
    return SecureWiseRepository.objects.create(
        organization=org,
        project=project,
        name="test-repo",
        repository_url="https://github.com/test/repo",
        clone_url="https://github.com/test/repo.git",
        access_mode="public",
        created_by=owner,
    )


@pytest.fixture
def policy(org, project, owner):
    return SecureWiseScanPolicy.objects.create(
        organization=org,
        project=project,
        name="Default Policy",
        scan_types=["sast"],
        fail_on_severity="high",
        max_critical=0,
        max_high=5,
        created_by=owner,
    )


@pytest.fixture
def scan(org, project, policy, owner, repository):
    return SecureWiseScan.objects.create(
        organization=org,
        project=project,
        policy=policy,
        repository=repository,
        scan_type="sast",
        status="pending",
        triggered_by=owner,
    )


# ---------------------------------------------------------------------------
# Model creation tests
# ---------------------------------------------------------------------------


class TestModelCreation:
    def test_organization_created(self, org):
        assert SecureWiseOrganization.objects.filter(slug="testorg").exists()
        assert str(org) == "TestOrg"

    def test_membership_created(self, org, owner):
        m = SecureWiseMembership.objects.get(organization=org, user=owner)
        assert m.role == "owner"

    def test_project_created(self, project, org):
        assert project.organization == org
        assert SecureWiseProject.objects.filter(slug="testproject").exists()

    def test_repository_created(self, repository, project):
        assert repository.project == project
        assert repository.access_mode == "public"

    def test_scan_policy_created(self, policy):
        assert policy.scan_types == ["sast"]
        assert policy.fail_on_severity == "high"

    def test_scan_created(self, scan):
        assert scan.status == "pending"
        assert scan.scan_type == "sast"

    def test_git_integration_token_encryption(self, org, owner):
        integration = SecureWiseGitIntegration.objects.create(
            organization=org,
            provider="github",
            auth_type="personal_access_token",
            name="My GitHub",
            connected_by=owner,
        )
        raw_token = "ghp_testtoken1234abcd"
        integration.set_token(raw_token)
        integration.save()

        # Reload from DB
        integration.refresh_from_db()
        assert integration.get_token() == raw_token
        assert integration.token_last_four == "abcd"
        # Raw token must not be stored in plaintext
        assert raw_token.encode() not in bytes(integration._encrypted_access_token)


# ---------------------------------------------------------------------------
# Permission / isolation tests
# ---------------------------------------------------------------------------


class TestOrgIsolation:
    def test_member_can_see_org(self, org, member):
        SecureWiseMembership.objects.create(organization=org, user=member, role="developer")
        assert SecureWiseMembership.objects.filter(organization=org, user=member).exists()

    def test_outsider_cannot_see_org(self, org, outsider):
        from apps.securewise.views import _get_user_org_ids

        ids = list(_get_user_org_ids(outsider))
        assert str(org.id) not in [str(i) for i in ids]

    def test_owner_membership_role(self, org, owner):
        m = SecureWiseMembership.objects.get(organization=org, user=owner)
        assert m.role == "owner"

    def test_two_orgs_isolated(self, owner, outsider):
        org2 = SecureWiseOrganization.objects.create(name="Org2", slug="org2", owner=outsider)
        SecureWiseMembership.objects.create(organization=org2, user=outsider, role="owner")
        from apps.securewise.views import _get_user_org_ids

        owner_orgs = list(_get_user_org_ids(owner))
        outsider_orgs = list(_get_user_org_ids(outsider))
        assert not set(owner_orgs) & set(outsider_orgs)


# ---------------------------------------------------------------------------
# Scanner tests
# ---------------------------------------------------------------------------


def _seed_vulnerable_repo(scan, repo_path, allowed_root=None, timeout=120):
    """Stand-in for a real git clone — writes a small vulnerable file so the
    real SAST fallback engine has something concrete to detect."""
    repo_path.mkdir(parents=True, exist_ok=True)
    (repo_path / "app.py").write_text(
        "import pickle\n"
        'HARDCODED_SECRET_TOKEN = "not_a_real_secret_placeholder_value_123456"\n'
        "data = pickle.loads(raw_bytes)\n"
    )


class TestScanEngine:
    def test_sast_fallback_returns_findings(self, tmp_path):
        (tmp_path / "app.py").write_text("import pickle\ndata = pickle.loads(raw)\n")
        scanner = SastScanner()
        result = scanner.run(tmp_path, "test-scan-001", {})
        assert result.success is True
        assert len(result.findings) > 0
        severities = {f.severity for f in result.findings}
        assert "critical" in severities or "high" in severities

    def test_scan_runner_completes(self, scan):
        with patch("apps.securewise.services.scanner.clone_repository", side_effect=_seed_vulnerable_repo):
            runner = ScannerRunner()
            runner.run_scan(str(scan.id))

        scan.refresh_from_db()
        assert scan.status in ("completed", "completed_with_warnings")
        assert scan.completed_at is not None
        assert scan.duration_seconds is not None

    def test_scan_runner_creates_findings(self, scan):
        with patch("apps.securewise.services.scanner.clone_repository", side_effect=_seed_vulnerable_repo):
            runner = ScannerRunner()
            runner.run_scan(str(scan.id))
        findings = SecureWiseFinding.objects.filter(scan=scan)
        assert findings.count() > 0

    def test_quality_gate_fails_with_critical(self, scan):
        with patch("apps.securewise.services.scanner.clone_repository", side_effect=_seed_vulnerable_repo):
            runner = ScannerRunner()
            runner.run_scan(str(scan.id))
        scan.refresh_from_db()
        # Policy has max_critical=0, seeded file has a critical pickle.loads finding
        assert scan.quality_gate_passed is False

    def test_audit_log_created_for_scan(self, scan):
        with patch("apps.securewise.services.scanner.clone_repository", side_effect=_seed_vulnerable_repo):
            runner = ScannerRunner()
            runner.run_scan(str(scan.id))
        logs = SecureWiseAuditLog.objects.filter(target_type="SecureWiseScan", target_id=str(scan.id))
        assert logs.filter(event="scan_started").exists()
        # Completed or failed — either is logged
        assert logs.filter(event__in=["scan_completed", "scan_failed"]).exists()


# ---------------------------------------------------------------------------
# Finding tests
# ---------------------------------------------------------------------------


class TestFindingCreation:
    def test_finding_fields(self, scan, project, org):
        f = SecureWiseFinding.objects.create(
            scan=scan,
            project=project,
            organization=org,
            title="Test XSS",
            severity="high",
            confidence="high",
            status="open",
            cwe_id="CWE-79",
            owasp_category="A03:2021",
            scanner_type="sast",
        )
        assert f.severity == "high"
        assert f.cwe_id == "CWE-79"
        assert str(f).startswith("[HIGH]")

    def test_finding_status_changes(self, scan, project, org):
        f = SecureWiseFinding.objects.create(
            scan=scan,
            project=project,
            organization=org,
            title="Test",
            severity="medium",
            confidence="medium",
            status="open",
            scanner_type="sast",
        )
        f.status = "accepted_risk"
        f.save()
        f.refresh_from_db()
        assert f.status == "accepted_risk"


# ---------------------------------------------------------------------------
# Report generation tests
# ---------------------------------------------------------------------------


class TestReportGeneration:
    def test_generate_json_report(self, scan, project, org):
        # First run scanner to populate findings
        with patch("apps.securewise.services.scanner.clone_repository", side_effect=_seed_vulnerable_repo):
            runner = ScannerRunner()
            runner.run_scan(str(scan.id))
        scan.refresh_from_db()

        report_data = generate_json_report(scan)

        assert report_data["report_version"] == "1.0"
        assert report_data["project"]["name"] == project.name
        assert "severity_counts" in report_data
        assert "findings" in report_data
        assert len(report_data["findings"]) > 0
        assert "cwe_mapping" in report_data
        assert "owasp_mapping" in report_data
        assert "quality_gate" in report_data

    def test_report_model_created(self, scan, project, org, owner):
        with patch("apps.securewise.services.scanner.clone_repository", side_effect=_seed_vulnerable_repo):
            runner = ScannerRunner()
            runner.run_scan(str(scan.id))
        scan.refresh_from_db()

        report = SecureWiseReport.objects.create(
            organization=org,
            project=project,
            scan=scan,
            title="Test Report",
            format="json",
            generated_by=owner,
        )
        report.report_data = generate_json_report(scan)
        report.status = "ready"
        report.save()

        report.refresh_from_db()
        assert report.status == "ready"
        assert report.report_data["report_version"] == "1.0"
