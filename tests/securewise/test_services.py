"""
SecureWise SASP — permissions and service layer tests.
Drives coverage for permissions.py, services/repository.py, services/scanner.py.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model

import pytest

from apps.securewise.models import (
    SecureWiseMembership,
    SecureWiseOrganization,
    SecureWiseProject,
    SecureWiseScan,
    SecureWiseScanPolicy,
)
from apps.securewise.permissions import (
    ADMIN_ROLES,
    WRITE_ROLES,
    IsSecureWiseAdmin,
    IsSecureWiseMember,
    IsSecureWiseWriteMember,
    _get_org_from_obj,
    _membership,
)
from apps.securewise.services.repository import (
    check_private_access,
    check_public_access,
    detect_provider,
    normalize_url,
    validate_url_format,
)
from apps.securewise.services.scanner import (
    MockDastScanner,
    MockSastScanner,
    MockScaScanner,
    MockSecretScanner,
    ScannerRunner,
    _get_scanners_for_type,
)

User = get_user_model()
pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Permission class unit tests
# ---------------------------------------------------------------------------


@pytest.fixture
def owner(db):
    return User.objects.create_user(username="perm_owner", email="perm_owner@sw.test", password="pass")


@pytest.fixture
def developer(db):
    return User.objects.create_user(username="perm_dev", email="perm_dev@sw.test", password="pass")


@pytest.fixture
def org(owner):
    o = SecureWiseOrganization.objects.create(name="PermOrg", slug="permorg", owner=owner)
    SecureWiseMembership.objects.create(organization=o, user=owner, role="owner")
    return o


@pytest.fixture
def dev_membership(org, developer):
    return SecureWiseMembership.objects.create(organization=org, user=developer, role="developer")


class TestPermissionHelpers:
    def test_get_org_from_org_object(self, org):
        assert _get_org_from_obj(org) is org

    def test_get_org_from_project(self, org, owner):
        project = SecureWiseProject.objects.create(organization=org, name="P", slug="p", created_by=owner)
        assert _get_org_from_obj(project) == org

    def test_get_org_returns_none_for_unknown(self):
        obj = MagicMock(spec=[])  # no .organization attribute
        result = _get_org_from_obj(obj)
        assert result is None

    def test_membership_returns_none_for_unauthenticated(self, org):
        anon = MagicMock()
        anon.is_authenticated = False
        result = _membership(anon, org)
        assert result is None

    def test_membership_returns_none_when_org_is_none(self, owner):
        result = _membership(owner, None)
        assert result is None

    def test_membership_returns_record_for_member(self, org, owner):
        m = _membership(owner, org)
        assert m is not None
        assert m.role == "owner"

    def test_membership_returns_none_for_non_member(self, org):
        stranger = User.objects.create_user(username="stranger99", password="pass")
        assert _membership(stranger, org) is None

    def test_admin_roles_set(self):
        assert "owner" in ADMIN_ROLES
        assert "admin" in ADMIN_ROLES
        assert "developer" not in ADMIN_ROLES

    def test_write_roles_set(self):
        assert "owner" in WRITE_ROLES
        assert "security_engineer" in WRITE_ROLES
        assert "auditor" not in WRITE_ROLES


class TestIsSecureWiseMember:
    def _make_request(self, user=None, method="GET"):
        req = MagicMock()
        req.user = user or MagicMock(is_authenticated=False)
        req.method = method
        return req

    def test_unauthenticated_denied(self):
        perm = IsSecureWiseMember()
        req = self._make_request()
        req.user.is_authenticated = False
        assert perm.has_permission(req, None) is False

    def test_authenticated_allowed_at_view_level(self, owner):
        perm = IsSecureWiseMember()
        req = MagicMock()
        req.user = owner  # real User object, is_authenticated = True
        assert perm.has_permission(req, None) is True

    def test_member_has_object_permission(self, org, owner):
        perm = IsSecureWiseMember()
        req = self._make_request(user=owner)
        assert perm.has_object_permission(req, None, org) is True

    def test_non_member_denied_object_permission(self, org):
        perm = IsSecureWiseMember()
        stranger = User.objects.create_user(username="str_member", password="pass")
        req = self._make_request(user=stranger)
        assert perm.has_object_permission(req, None, org) is False


class TestIsSecureWiseWriteMember:
    def _make_request(self, user, method="POST"):
        req = MagicMock()
        req.user = user
        req.method = method
        return req

    def test_owner_can_write(self, org, owner):
        perm = IsSecureWiseWriteMember()
        req = self._make_request(owner, "POST")
        assert perm.has_object_permission(req, None, org) is True

    def test_developer_cannot_write(self, org, developer, dev_membership):
        perm = IsSecureWiseWriteMember()
        req = self._make_request(developer, "POST")
        assert perm.has_object_permission(req, None, org) is False

    def test_developer_can_read(self, org, developer, dev_membership):
        perm = IsSecureWiseWriteMember()
        req = self._make_request(developer, "GET")
        assert perm.has_object_permission(req, None, org) is True

    def test_non_member_denied(self, org):
        perm = IsSecureWiseWriteMember()
        stranger = User.objects.create_user(username="str_write", password="pass")
        req = self._make_request(stranger, "POST")
        assert perm.has_object_permission(req, None, org) is False


class TestIsSecureWiseAdmin:
    def _make_request(self, user):
        req = MagicMock()
        req.user = user
        req.method = "DELETE"
        return req

    def test_owner_is_admin(self, org, owner):
        perm = IsSecureWiseAdmin()
        req = self._make_request(owner)
        assert perm.has_object_permission(req, None, org) is True

    def test_developer_is_not_admin(self, org, developer, dev_membership):
        perm = IsSecureWiseAdmin()
        req = self._make_request(developer)
        assert perm.has_object_permission(req, None, org) is False

    def test_admin_role_granted(self, org, developer):
        SecureWiseMembership.objects.filter(organization=org, user=developer).delete()
        SecureWiseMembership.objects.create(organization=org, user=developer, role="admin")
        perm = IsSecureWiseAdmin()
        req = self._make_request(developer)
        assert perm.has_object_permission(req, None, org) is True


# ---------------------------------------------------------------------------
# Repository service tests
# ---------------------------------------------------------------------------


class TestDetectProvider:
    def test_github(self):
        assert detect_provider("https://github.com/org/repo") == "github"

    def test_gitlab(self):
        assert detect_provider("https://gitlab.com/org/repo") == "gitlab"

    def test_bitbucket(self):
        assert detect_provider("https://bitbucket.org/org/repo") == "bitbucket"

    def test_azure_devops(self):
        assert detect_provider("https://dev.azure.com/org/project") == "azure_devops"

    def test_unknown_defaults_to_github(self):
        assert detect_provider("https://my-private-git.example.com/repo") == "github"

    def test_invalid_url(self):
        # Should not raise, returns default
        result = detect_provider("not-a-url")
        assert isinstance(result, str)


class TestNormalizeUrl:
    def test_strips_dot_git(self):
        assert normalize_url("https://github.com/org/repo.git") == "https://github.com/org/repo"

    def test_strips_trailing_slash(self):
        assert normalize_url("https://github.com/org/repo/") == "https://github.com/org/repo"

    def test_strips_whitespace(self):
        assert normalize_url("  https://github.com/org/repo  ") == "https://github.com/org/repo"

    def test_no_change_for_clean_url(self):
        url = "https://github.com/org/repo"
        assert normalize_url(url) == url


class TestValidateUrlFormat:
    def test_valid_https_url(self):
        ok, msg = validate_url_format("https://github.com/org/repo")
        assert ok is True
        assert msg == ""

    def test_valid_http_url(self):
        ok, _ = validate_url_format("http://github.com/org/repo")
        assert ok is True

    def test_invalid_no_scheme(self):
        ok, msg = validate_url_format("github.com/org/repo")
        assert ok is False
        assert msg != ""

    def test_invalid_empty(self):
        ok, msg = validate_url_format("")
        assert ok is False

    def test_invalid_just_text(self):
        ok, msg = validate_url_format("not-a-url")
        assert ok is False


class TestCheckPublicAccess:
    def test_success_when_ls_remote_returns_zero(self, tmp_path):
        with patch("apps.securewise.services.repository.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            ok, msg = check_public_access("https://github.com/org/repo")
        assert ok is True
        assert "accessible" in msg.lower()

    def test_failure_when_ls_remote_returns_nonzero(self):
        with patch("apps.securewise.services.repository.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=128, stderr=b"not found")
            ok, msg = check_public_access("https://github.com/org/private-repo")
        assert ok is False

    def test_404_message(self):
        with patch("apps.securewise.services.repository.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=128, stderr=b"404")
            ok, msg = check_public_access("https://github.com/org/missing")
        assert ok is False
        assert "not found" in msg.lower() or "not publicly" in msg.lower()

    def test_timeout(self):
        import subprocess as sp

        with patch(
            "apps.securewise.services.repository.subprocess.run",
            side_effect=sp.TimeoutExpired(cmd="git", timeout=15),
        ):
            ok, msg = check_public_access("https://github.com/org/repo")
        assert ok is False
        assert "timed out" in msg.lower()

    def test_git_not_installed(self):
        with patch(
            "apps.securewise.services.repository.subprocess.run",
            side_effect=FileNotFoundError,
        ):
            ok, msg = check_public_access("https://github.com/org/repo")
        assert ok is True  # skipped, not failed
        assert "skipped" in msg.lower()

    def test_unexpected_exception(self):
        with patch(
            "apps.securewise.services.repository.subprocess.run",
            side_effect=OSError("disk error"),
        ):
            ok, msg = check_public_access("https://github.com/org/repo")
        assert ok is False


class TestCheckPrivateAccess:
    def test_success(self):
        with patch("apps.securewise.services.repository.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            ok, msg = check_private_access("https://github.com/org/private", "secret-token")
        assert ok is True

    def test_failure(self):
        with patch("apps.securewise.services.repository.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=128, stderr=b"auth failed")
            ok, msg = check_private_access("https://github.com/org/private", "bad-token")
        assert ok is False

    def test_timeout(self):
        import subprocess as sp

        with patch(
            "apps.securewise.services.repository.subprocess.run",
            side_effect=sp.TimeoutExpired(cmd="git", timeout=15),
        ):
            ok, msg = check_private_access("https://github.com/org/repo", "token")
        assert ok is False

    def test_git_not_installed(self):
        with patch(
            "apps.securewise.services.repository.subprocess.run",
            side_effect=FileNotFoundError,
        ):
            ok, msg = check_private_access("https://github.com/org/repo", "token")
        assert ok is True  # skipped


# ---------------------------------------------------------------------------
# Scanner service tests
# ---------------------------------------------------------------------------


class TestMockScanners:
    def test_dast_scanner_returns_findings(self, tmp_path):
        scanner = MockDastScanner()
        result = scanner.run(tmp_path, "test-dast-001", {})
        assert result.success is True
        assert len(result.findings) >= 2
        types = {f.scanner_type for f in result.findings}
        assert "dast" in types

    def test_sca_scanner_returns_findings(self, tmp_path):
        scanner = MockScaScanner()
        result = scanner.run(tmp_path, "test-sca-001", {})
        assert result.success is True
        assert any(f.scanner_type == "sca" for f in result.findings)

    def test_secret_scanner_returns_findings(self, tmp_path):
        scanner = MockSecretScanner()
        result = scanner.run(tmp_path, "test-sec-001", {})
        assert result.success is True
        assert result.findings[0].severity == "critical"
        assert result.findings[0].cwe_id == "CWE-798"

    def test_sast_finding_has_required_fields(self, tmp_path):
        scanner = MockSastScanner()
        result = scanner.run(tmp_path, "x", {})
        f = result.findings[0]
        assert f.title
        assert f.severity in ("critical", "high", "medium", "low", "info")
        assert f.scanner_type == "sast"
        assert f.fingerprint


class TestGetScannersForType:
    def test_sast_type(self):
        scanners = _get_scanners_for_type("sast")
        assert len(scanners) == 1
        assert isinstance(scanners[0], MockSastScanner)

    def test_dast_type(self):
        scanners = _get_scanners_for_type("dast")
        assert isinstance(scanners[0], MockDastScanner)

    def test_sca_type(self):
        scanners = _get_scanners_for_type("sca")
        assert isinstance(scanners[0], MockScaScanner)

    def test_secrets_type(self):
        scanners = _get_scanners_for_type("secrets")
        assert isinstance(scanners[0], MockSecretScanner)

    def test_full_type_returns_all_scanners(self):
        scanners = _get_scanners_for_type("full")
        assert len(scanners) == 4

    def test_unknown_type_defaults_to_sast(self):
        scanners = _get_scanners_for_type("unknown_type")
        assert isinstance(scanners[0], MockSastScanner)

    def test_iac_type(self):
        scanners = _get_scanners_for_type("iac")
        assert len(scanners) == 1

    def test_container_type(self):
        scanners = _get_scanners_for_type("container")
        assert len(scanners) == 1


class TestScannerRunnerEdgeCases:
    @pytest.fixture
    def scan_fixture(self, db):
        owner = User.objects.create_user(username="runner_owner2", email="r2@sw.test", password="pass")
        org = SecureWiseOrganization.objects.create(name="RunnerOrg2", slug="runnerorg2", owner=owner)
        SecureWiseMembership.objects.create(organization=org, user=owner, role="owner")
        project = SecureWiseProject.objects.create(
            organization=org, name="RunnerProject2", slug="runnerproject2", created_by=owner
        )
        policy = SecureWiseScanPolicy.objects.create(
            organization=org,
            project=project,
            name="RP2",
            scan_types=["dast"],
            fail_on_severity="critical",
            max_critical=0,
            max_high=10,
            created_by=owner,
        )
        return SecureWiseScan.objects.create(
            organization=org,
            project=project,
            policy=policy,
            scan_type="dast",
            status="pending",
            triggered_by=owner,
        )

    def test_dast_scan_completes(self, scan_fixture):
        ScannerRunner().run_scan(str(scan_fixture.id))
        scan_fixture.refresh_from_db()
        assert scan_fixture.status == "completed"

    def test_invalid_scan_id_does_not_raise(self):
        """Runner should handle missing scan gracefully without raising."""
        import uuid

        runner = ScannerRunner()
        # Should not raise — logs error and returns
        runner.run_scan(str(uuid.uuid4()))

    def test_full_scan_type(self, db):
        owner = User.objects.create_user(username="full_scan_owner", email="fs@sw.test", password="pass")
        org = SecureWiseOrganization.objects.create(name="FullOrg", slug="fullorg", owner=owner)
        SecureWiseMembership.objects.create(organization=org, user=owner, role="owner")
        project = SecureWiseProject.objects.create(organization=org, name="FP", slug="fp", created_by=owner)
        policy = SecureWiseScanPolicy.objects.create(
            organization=org,
            project=project,
            name="FPol",
            scan_types=["full"],
            fail_on_severity="critical",
            max_critical=0,
            max_high=10,
            created_by=owner,
        )
        scan = SecureWiseScan.objects.create(
            organization=org,
            project=project,
            policy=policy,
            scan_type="full",
            status="pending",
            triggered_by=owner,
        )
        ScannerRunner().run_scan(str(scan.id))
        scan.refresh_from_db()
        assert scan.status == "completed"
        from apps.securewise.models import SecureWiseFinding

        # Full scan = 4 mock scanners → many findings
        assert SecureWiseFinding.objects.filter(scan=scan).count() > 4
