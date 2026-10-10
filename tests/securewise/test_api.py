"""
SecureWise SASP — API endpoint tests.
Tests all viewsets via the DRF test client to drive views.py coverage.
"""

from __future__ import annotations

import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone

import pytest
from rest_framework.test import APIClient

from apps.securewise.models import (
    PentestEvidence,
    PentestExecution,
    PentestSession,
    PentestTestCase,
    SecureWiseAuditLog,
    SecureWiseFinding,
    SecureWiseGitIntegration,
    SecureWiseMembership,
    SecureWiseOrganization,
    SecureWiseProject,
    SecureWiseReport,
    SecureWiseRepository,
    SecureWiseScan,
    SecureWiseScanEngineResult,
    SecureWiseScanPolicy,
    SecureWiseScanPolicyTemplate,
    SecureWiseWorkerRegistration,
)
from apps.securewise.services.scanner import ScannerRunner
from apps.securewise.views import AIRecommendationThrottle

User = get_user_model()
pytestmark = pytest.mark.django_db


def _results(resp_data):
    """Normalize paginated or plain list API responses."""
    if isinstance(resp_data, list):
        return resp_data
    return resp_data.get("results", resp_data)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def owner(db):
    return User.objects.create_user(username="api_owner", email="api_owner@sw.test", password="pass")


@pytest.fixture
def other_user(db):
    return User.objects.create_user(username="api_other", email="api_other@sw.test", password="pass")


@pytest.fixture
def auth_client(owner):
    c = APIClient()
    c.force_authenticate(user=owner)
    return c


@pytest.fixture
def other_client(other_user):
    c = APIClient()
    c.force_authenticate(user=other_user)
    return c


@pytest.fixture
def anon_client():
    return APIClient()


@pytest.fixture
def org(owner):
    o = SecureWiseOrganization.objects.create(name="APIOrg", slug="apiorg", owner=owner)
    SecureWiseMembership.objects.create(organization=o, user=owner, role="owner")
    return o


@pytest.fixture
def project(org, owner):
    return SecureWiseProject.objects.create(organization=org, name="APIProject", slug="apiproject", created_by=owner)


@pytest.fixture
def policy(org, project, owner):
    return SecureWiseScanPolicy.objects.create(
        organization=org,
        project=project,
        name="API Policy",
        scan_types=["sast"],
        fail_on_severity="high",
        max_critical=0,
        max_high=5,
        created_by=owner,
    )


@pytest.fixture
def repository(org, project, owner):
    return SecureWiseRepository.objects.create(
        organization=org,
        project=project,
        name="api-repo",
        repository_url="https://github.com/test/api-repo",
        clone_url="https://github.com/test/api-repo.git",
        access_mode="public",
        created_by=owner,
    )


@pytest.fixture
def scan(org, project, policy, owner):
    return SecureWiseScan.objects.create(
        organization=org,
        project=project,
        policy=policy,
        scan_type="sast",
        status="pending",
        triggered_by=owner,
    )


@pytest.fixture
def completed_scan(org, project, policy, owner, repository):
    s = SecureWiseScan.objects.create(
        organization=org,
        project=project,
        policy=policy,
        repository=repository,
        scan_type="sast",
        status="pending",
        triggered_by=owner,
    )

    def _seed_vulnerable_repo(scan, repo_path, allowed_root=None, timeout=120):
        repo_path.mkdir(parents=True, exist_ok=True)
        (repo_path / "app.py").write_text(
            "import pickle\n"
            'HARDCODED_SECRET_TOKEN = "not_a_real_secret_placeholder_value_123456"\n'
            "data = pickle.loads(raw_bytes)\n"
        )

    with patch("apps.securewise.services.scanner.clone_repository", side_effect=_seed_vulnerable_repo):
        ScannerRunner().run_scan(str(s.id))
    s.refresh_from_db()
    return s


@pytest.fixture
def finding(completed_scan, project, org):
    return SecureWiseFinding.objects.filter(scan=completed_scan).first()


# ---------------------------------------------------------------------------
# Unauthenticated access
# ---------------------------------------------------------------------------


class TestUnauthenticated:
    def test_orgs_requires_auth(self, anon_client):
        resp = anon_client.get("/api/securewise/organizations/")
        assert resp.status_code in (401, 403)

    def test_documentation_page_is_public(self, anon_client):
        resp = anon_client.get("/documentation/")
        assert resp.status_code == 200
        assert b"SecureWise Developer Documentation" in resp.content
        assert b"OPENAI_API_KEY" in resp.content
        assert b"sk-" not in resp.content.lower()
        assert b"ghp_" not in resp.content.lower()

    def test_user_manual_page_is_public(self, anon_client):
        resp = anon_client.get("/user-manual/")
        assert resp.status_code == 200
        assert b"SecureWise User Manual" in resp.content
        assert b"Organization Setup" in resp.content
        assert b"Run Your First Scan" in resp.content
        assert b"Scan a Local Repository" in resp.content
        assert b"OPENAI_API_KEY" not in resp.content
        assert b"sk-" not in resp.content.lower()
        assert b"ghp_" not in resp.content.lower()

    def test_projects_requires_auth(self, anon_client):
        resp = anon_client.get("/api/securewise/projects/")
        assert resp.status_code in (401, 403)

    def test_dashboard_requires_auth(self, anon_client):
        resp = anon_client.get("/api/securewise/dashboard/summary/")
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Organization endpoints
# ---------------------------------------------------------------------------


class TestOrganizationAPI:
    def test_list_own_orgs(self, auth_client, org):
        resp = auth_client.get("/api/securewise/organizations/")
        assert resp.status_code == 200
        data = resp.json()
        results = _results(data)
        slugs = [o["slug"] for o in results]
        assert "apiorg" in slugs

    def test_other_user_cannot_see_org(self, other_client, org):
        resp = other_client.get("/api/securewise/organizations/")
        assert resp.status_code == 200
        data = resp.json()
        results = _results(data)
        assert all(o["slug"] != "apiorg" for o in results)

    def test_create_org(self, auth_client):
        resp = auth_client.post(
            "/api/securewise/organizations/",
            {"name": "New Org", "slug": "new-org"},
            format="json",
        )
        assert resp.status_code == 201
        assert resp.json()["slug"] == "new-org"
        # Owner membership auto-created
        assert SecureWiseMembership.objects.filter(
            organization__slug="new-org", user__username="api_owner", role="owner"
        ).exists()

    def test_retrieve_org(self, auth_client, org):
        resp = auth_client.get(f"/api/securewise/organizations/{org.id}/")
        assert resp.status_code == 200
        assert resp.json()["slug"] == "apiorg"

    def test_other_user_cannot_retrieve_org(self, other_client, org):
        resp = other_client.get(f"/api/securewise/organizations/{org.id}/")
        assert resp.status_code == 404

    def test_update_org(self, auth_client, org):
        resp = auth_client.patch(
            f"/api/securewise/organizations/{org.id}/",
            {"name": "Updated Name"},
            format="json",
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated Name"

    def test_delete_org(self, auth_client):
        o = SecureWiseOrganization.objects.create(name="ToDelete", slug="to-delete", owner=None)
        o.owner = User.objects.get(username="api_owner")
        o.save()
        SecureWiseMembership.objects.create(organization=o, user=User.objects.get(username="api_owner"), role="owner")
        resp = auth_client.delete(f"/api/securewise/organizations/{o.id}/")
        assert resp.status_code == 204


# ---------------------------------------------------------------------------
# Project endpoints
# ---------------------------------------------------------------------------


class TestProjectAPI:
    def test_list_projects(self, auth_client, project, org):
        resp = auth_client.get("/api/securewise/projects/")
        assert resp.status_code == 200
        results = _results(resp.json())
        assert any(p["slug"] == "apiproject" for p in results)

    def test_create_project(self, auth_client, org):
        resp = auth_client.post(
            "/api/securewise/projects/",
            {"name": "New Project", "slug": "new-project", "organization": str(org.id)},
            format="json",
        )
        assert resp.status_code == 201

    def test_non_admin_cannot_promote_membership(self, org, other_user):
        membership = SecureWiseMembership.objects.create(organization=org, user=other_user, role="developer")
        auditor = User.objects.create_user(
            username="api_auditor", email="auditor@sw.test", password="local-test-password"
        )
        SecureWiseMembership.objects.create(organization=org, user=auditor, role="auditor")
        client = APIClient()
        client.force_authenticate(auditor)
        response = client.patch(
            f"/api/securewise/memberships/{membership.id}/",
            {"role": "admin"},
            format="json",
        )
        assert response.status_code == 403
        membership.refresh_from_db()
        assert membership.role == "developer"

    def test_retrieve_project(self, auth_client, project):
        resp = auth_client.get(f"/api/securewise/projects/{project.id}/")
        assert resp.status_code == 200

    def test_update_project(self, auth_client, project):
        resp = auth_client.patch(
            f"/api/securewise/projects/{project.id}/",
            {"name": "Renamed Project"},
            format="json",
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Renamed Project"

    def test_delete_project(self, auth_client, org, owner):
        p = SecureWiseProject.objects.create(organization=org, name="ToDelete", slug="td-project", created_by=owner)
        resp = auth_client.delete(f"/api/securewise/projects/{p.id}/")
        assert resp.status_code == 204

    def test_other_user_cannot_access_project(self, other_client, project):
        resp = other_client.get(f"/api/securewise/projects/{project.id}/")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Repository endpoints
# ---------------------------------------------------------------------------


class TestGitIntegrationAPI:
    def test_github_app_cannot_be_connected_as_a_legacy_token_integration(self, auth_client, org):
        response = auth_client.post(
            "/api/securewise/git-integrations/",
            {
                "organization": str(org.id),
                "provider": "github",
                "auth_type": "github_app",
                "name": "GitHub App",
                "access_token": "not-a-github-app-token",
            },
            format="json",
        )
        assert response.status_code == 400
        assert "auth_type" in response.json()
        assert SecureWiseGitIntegration.objects.count() == 0


class TestRepositoryAPI:
    def test_list_repositories(self, auth_client, repository):
        resp = auth_client.get("/api/securewise/repositories/")
        assert resp.status_code == 200
        results = _results(resp.json())
        assert any(r["name"] == "api-repo" for r in results)

    def test_create_repository(self, auth_client, org, project):
        resp = auth_client.post(
            "/api/securewise/repositories/",
            {
                "organization": str(org.id),
                "project": str(project.id),
                "name": "new-repo",
                "repository_url": "https://github.com/test/new-repo",
                "clone_url": "https://github.com/test/new-repo.git",
                "access_mode": "public",
            },
            format="json",
        )
        assert resp.status_code == 201

    def test_create_local_path_repository(self, auth_client, org, project, tmp_path):
        local_repo = tmp_path / "local-repo"
        local_repo.mkdir()
        (local_repo / "app.py").write_text("print('hello')\n", encoding="utf-8")

        resp = auth_client.post(
            "/api/securewise/repositories/",
            {
                "organization": str(org.id),
                "project": str(project.id),
                "name": "local-repo",
                "local_path": str(local_repo),
                "access_mode": "local_path",
            },
            format="json",
        )

        assert resp.status_code == 201
        data = resp.json()
        assert data["access_mode"] == "local_path"
        assert data["repository_url"] == ""
        assert data["local_path"] == str(local_repo.resolve())

    def test_retrieve_repository(self, auth_client, repository):
        resp = auth_client.get(f"/api/securewise/repositories/{repository.id}/")
        assert resp.status_code == 200

    def test_repository_cannot_borrow_another_organizations_integration(self, auth_client, org, project, other_user):
        other_org = SecureWiseOrganization.objects.create(name="Foreign", slug="foreign", owner=other_user)
        integration = SecureWiseGitIntegration.objects.create(
            organization=other_org,
            provider="github",
            auth_type="personal_access_token",
            name="Foreign GitHub",
        )
        response = auth_client.post(
            "/api/securewise/repositories/",
            {
                "organization": str(org.id),
                "project": str(project.id),
                "integration": str(integration.id),
                "name": "foreign-integration-repository",
                "repository_url": "https://github.com/example/private",
                "access_mode": "integration",
            },
            format="json",
        )
        assert response.status_code == 400
        assert "integration" in response.json()

    def test_viewer_cannot_test_github_integration(self, auth_client, org, owner):
        membership = SecureWiseMembership.objects.get(organization=org, user=owner)
        membership.role = "auditor"
        membership.save(update_fields=["role"])
        integration = SecureWiseGitIntegration.objects.create(
            organization=org,
            provider="github",
            auth_type="personal_access_token",
            name="Customer GitHub",
        )
        integration.set_token("opaque-test-token")
        integration.save(update_fields=["_encrypted_access_token", "token_last_four"])
        response = auth_client.post(f"/api/securewise/git-integrations/{integration.id}/test/")
        assert response.status_code == 403

    def test_validate_endpoint_valid_url(self, auth_client):
        resp = auth_client.post(
            "/api/securewise/repositories/validate/",
            {"url": "https://github.com/test/repo", "access_mode": "public"},
            format="json",
        )
        # Returns 200 or 400; just check it responds
        assert resp.status_code in (200, 400)

    def test_validate_endpoint_invalid_url(self, auth_client):
        resp = auth_client.post(
            "/api/securewise/repositories/validate/",
            {"url": "not-a-url", "access_mode": "public"},
            format="json",
        )
        assert resp.status_code == 400

    def test_validate_local_path_endpoint(self, auth_client, tmp_path):
        local_repo = tmp_path / "local-repo"
        local_repo.mkdir()
        (local_repo / "app.py").write_text("print('hello')\n", encoding="utf-8")

        resp = auth_client.post(
            "/api/securewise/repositories/validate/",
            {"local_path": str(local_repo), "access_mode": "local_path"},
            format="json",
        )

        assert resp.status_code == 200
        assert resp.json()["accessible"] is True

    def test_validate_local_path_endpoint_strips_quotes_and_whitespace(self, auth_client, tmp_path):
        local_repo = tmp_path / "local-repo"
        local_repo.mkdir()
        (local_repo / "app.py").write_text("print('hello')\n", encoding="utf-8")

        resp = auth_client.post(
            "/api/securewise/repositories/validate/",
            {"local_path": f'  "{local_repo}/"  ', "access_mode": "local_path"},
            format="json",
        )

        assert resp.status_code == 200
        assert resp.json()["accessible"] is True

    def test_test_access_endpoint(self, auth_client, repository):
        resp = auth_client.post(f"/api/securewise/repositories/{repository.id}/test-access/")
        # Returns 200 or 400 depending on network; just check it responds
        assert resp.status_code in (200, 400)

    def test_test_access_local_path_endpoint(self, auth_client, org, project, owner, tmp_path):
        local_repo = tmp_path / "local-repo"
        local_repo.mkdir()
        (local_repo / "app.py").write_text("print('hello')\n", encoding="utf-8")
        repo = SecureWiseRepository.objects.create(
            organization=org,
            project=project,
            name="local-repo",
            access_mode="local_path",
            local_path=str(local_repo),
            repository_url="",
            created_by=owner,
        )

        resp = auth_client.post(f"/api/securewise/repositories/{repo.id}/test-access/")

        assert resp.status_code == 200
        assert resp.json()["accessible"] is True


# ---------------------------------------------------------------------------
# Scan policy endpoints
# ---------------------------------------------------------------------------


class TestScanPolicyAPI:
    def test_list_policies(self, auth_client, policy):
        resp = auth_client.get("/api/securewise/scan-policies/")
        assert resp.status_code == 200
        results = _results(resp.json())
        assert any(p["name"] == "API Policy" for p in results)

    def test_create_policy(self, auth_client, org, project):
        resp = auth_client.post(
            "/api/securewise/scan-policies/",
            {
                "organization": str(org.id),
                "project": str(project.id),
                "name": "New Policy",
                "scan_types": ["dast"],
                "fail_on_severity": "critical",
                "max_critical": 0,
                "max_high": 10,
            },
            format="json",
        )
        assert resp.status_code == 201

    def test_retrieve_policy(self, auth_client, policy):
        resp = auth_client.get(f"/api/securewise/scan-policies/{policy.id}/")
        assert resp.status_code == 200

    def test_update_policy(self, auth_client, policy):
        resp = auth_client.patch(
            f"/api/securewise/scan-policies/{policy.id}/",
            {"name": "Renamed Policy", "max_high": 20, "fail_on_severity": "critical"},
            format="json",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Renamed Policy"
        assert data["max_high"] == 20
        assert data["fail_on_severity"] == "critical"
        policy.refresh_from_db()
        assert policy.name == "Renamed Policy"
        assert SecureWiseAuditLog.objects.filter(event="scan_policy_updated", target_id=str(policy.id)).exists()

    def test_update_policy_cannot_move_organization(self, auth_client, policy, owner):
        other_org = SecureWiseOrganization.objects.create(name="OtherOrg", slug="otherorg-move", owner=owner)
        SecureWiseMembership.objects.create(organization=other_org, user=owner, role="owner")
        resp = auth_client.patch(
            f"/api/securewise/scan-policies/{policy.id}/",
            {"organization": str(other_org.id)},
            format="json",
        )
        assert resp.status_code == 400
        policy.refresh_from_db()
        assert policy.organization_id != other_org.id

    def test_update_policy_denied_for_non_write_role(self, org, policy, other_user):
        SecureWiseMembership.objects.create(organization=org, user=other_user, role="auditor")
        client = APIClient()
        client.force_authenticate(user=other_user)
        resp = client.patch(
            f"/api/securewise/scan-policies/{policy.id}/",
            {"name": "Hacked"},
            format="json",
        )
        assert resp.status_code == 403
        policy.refresh_from_db()
        assert policy.name != "Hacked"

    def test_delete_policy(self, auth_client, policy):
        policy_id = policy.id
        resp = auth_client.delete(f"/api/securewise/scan-policies/{policy_id}/")
        assert resp.status_code == 204
        assert not SecureWiseScanPolicy.objects.filter(id=policy_id).exists()
        assert SecureWiseAuditLog.objects.filter(event="scan_policy_deleted", target_id=str(policy_id)).exists()

    def test_delete_policy_denied_for_non_write_role(self, org, policy, other_user):
        SecureWiseMembership.objects.create(organization=org, user=other_user, role="auditor")
        client = APIClient()
        client.force_authenticate(user=other_user)
        resp = client.delete(f"/api/securewise/scan-policies/{policy.id}/")
        assert resp.status_code == 403
        assert SecureWiseScanPolicy.objects.filter(id=policy.id).exists()


class TestScanPolicyTemplateAPI:
    @pytest.fixture
    def template(self):
        return SecureWiseScanPolicyTemplate.objects.create(
            key="latest-market-standard-test",
            name="Latest Market Standard Scan",
            description="Broad market baseline.",
            recommended_for="Default organization policy",
            scan_types=["full"],
            fail_on_severity="high",
            max_critical=0,
            max_high=0,
            max_medium=10,
            fail_on_secrets=True,
            is_recommended=True,
            sort_order=1,
        )

    def test_list_templates(self, auth_client, template):
        resp = auth_client.get("/api/securewise/scan-policy-templates/")
        assert resp.status_code == 200
        results = _results(resp.json())
        assert any(t["key"] == template.key for t in results)

    def test_create_policy_from_template_as_default(self, auth_client, org, template):
        resp = auth_client.post(
            f"/api/securewise/scan-policy-templates/{template.id}/create-policy/",
            {"organization": str(org.id), "set_as_default": True},
            format="json",
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Latest Market Standard Scan"
        assert data["scan_types"] == ["full"]
        assert data["is_default"] is True
        assert SecureWiseScanPolicy.objects.filter(organization=org, is_default=True, name=template.name).exists()

    def test_copy_template_uses_unique_name(self, auth_client, org, template):
        SecureWiseScanPolicy.objects.create(
            organization=org,
            name=template.name,
            scan_types=["sast"],
            created_by=org.owner,
        )
        resp = auth_client.post(
            f"/api/securewise/scan-policy-templates/{template.id}/create-policy/",
            {"organization": str(org.id), "set_as_default": False},
            format="json",
        )
        assert resp.status_code == 201
        assert resp.json()["name"] == "Latest Market Standard Scan (2)"

    def test_create_policy_from_template_denied_for_read_role(self, org, template, other_user):
        SecureWiseMembership.objects.create(organization=org, user=other_user, role="auditor")
        client = APIClient()
        client.force_authenticate(user=other_user)
        resp = client.post(
            f"/api/securewise/scan-policy-templates/{template.id}/create-policy/",
            {"organization": str(org.id), "set_as_default": True},
            format="json",
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Scan endpoints
# ---------------------------------------------------------------------------


class TestScanAPI:
    def test_list_scans(self, auth_client, scan):
        resp = auth_client.get("/api/securewise/scans/")
        assert resp.status_code == 200

    def test_create_scan(self, auth_client, org, project, repository, policy):
        resp = auth_client.post(
            "/api/securewise/scans/",
            {
                "organization": str(org.id),
                "project": str(project.id),
                "repository": str(repository.id),
                "policy": str(policy.id),
                "scan_type": "sca",
            },
            format="json",
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "pending"

    def test_create_scan_rejects_repository_from_another_project(self, auth_client, org, project, owner):
        other_project = SecureWiseProject.objects.create(
            organization=org,
            name="Different project",
            slug="different-project",
            created_by=owner,
        )
        other_repository = SecureWiseRepository.objects.create(
            organization=org,
            project=other_project,
            name="other-project-repo",
            repository_url="https://github.com/test/other-project-repo",
            clone_url="https://github.com/test/other-project-repo.git",
            access_mode="public",
            created_by=owner,
        )
        response = auth_client.post(
            "/api/securewise/scans/",
            {
                "project": str(project.id),
                "repository": str(other_repository.id),
                "scan_type": "sast",
            },
            format="json",
        )
        assert response.status_code == 400
        assert "repository" in response.json()

    def test_create_dast_scan_allows_repository_without_target_url(self, auth_client, org, project, repository, policy):
        resp = auth_client.post(
            "/api/securewise/scans/",
            {
                "organization": str(org.id),
                "project": str(project.id),
                "repository": str(repository.id),
                "policy": str(policy.id),
                "scan_type": "dast",
            },
            format="json",
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["scan_type"] == "dast"

    def test_create_source_scan_requires_repository(self, auth_client, org, project, policy):
        resp = auth_client.post(
            "/api/securewise/scans/",
            {
                "organization": str(org.id),
                "project": str(project.id),
                "policy": str(policy.id),
                "scan_type": "sca",
            },
            format="json",
        )
        assert resp.status_code == 400
        assert "repository" in resp.json()

    def test_retrieve_scan(self, auth_client, scan):
        resp = auth_client.get(f"/api/securewise/scans/{scan.id}/")
        assert resp.status_code == 200
        assert resp.json()["scan_type"] == "sast"

    def test_retrieve_completed_partial_scan_exposes_retry(self, auth_client, org, project, policy, owner, repository):
        scan = SecureWiseScan.objects.create(
            organization=org,
            project=project,
            policy=policy,
            repository=repository,
            scan_type="dast",
            status="completed_partial",
            triggered_by=owner,
        )
        resp = auth_client.get(f"/api/securewise/scans/{scan.id}/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed_partial"
        assert data["can_retry"] is True

    def test_start_scan(self, auth_client, scan):
        resp = auth_client.post(f"/api/securewise/scans/{scan.id}/start/")
        assert resp.status_code == 200
        scan.refresh_from_db()
        assert scan.status == "queued"

    def test_start_already_running_scan_fails(self, auth_client, scan):
        scan.status = "running"
        scan.save()
        resp = auth_client.post(f"/api/securewise/scans/{scan.id}/start/")
        assert resp.status_code == 400

    def test_retry_completed_partial_scan(self, auth_client, org, project, policy, owner, repository):
        scan = SecureWiseScan.objects.create(
            organization=org,
            project=project,
            policy=policy,
            repository=repository,
            scan_type="dast",
            status="completed_partial",
            triggered_by=owner,
        )
        resp = auth_client.post(f"/api/securewise/scans/{scan.id}/retry/")
        assert resp.status_code == 200

    def test_cancel_scan(self, auth_client, org, project, policy, owner):
        s = SecureWiseScan.objects.create(
            organization=org,
            project=project,
            policy=policy,
            scan_type="sast",
            status="queued",
            triggered_by=owner,
        )
        resp = auth_client.post(f"/api/securewise/scans/{s.id}/cancel/")
        assert resp.status_code == 200
        s.refresh_from_db()
        assert s.status == "cancelled"

    def test_cancel_completed_scan_fails(self, auth_client, completed_scan):
        resp = auth_client.post(f"/api/securewise/scans/{completed_scan.id}/cancel/")
        assert resp.status_code == 400

    def test_other_user_cannot_see_scan(self, other_client, scan):
        resp = other_client.get(f"/api/securewise/scans/{scan.id}/")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Finding endpoints
# ---------------------------------------------------------------------------


class TestFindingAPI:
    def test_list_findings(self, auth_client, finding):
        resp = auth_client.get("/api/securewise/findings/")
        assert resp.status_code == 200
        results = _results(resp.json())
        assert len(results) > 0

    def test_finding_creation_is_reserved_for_scanner_execution(self, auth_client, org, project, scan):
        response = auth_client.post(
            "/api/securewise/findings/",
            {
                "organization": str(org.id),
                "project": str(project.id),
                "scan": str(scan.id),
                "title": "User-supplied finding",
            },
            format="json",
        )
        assert response.status_code == 405
        assert not SecureWiseFinding.objects.filter(title="User-supplied finding").exists()

    def test_retrieve_finding(self, auth_client, finding):
        resp = auth_client.get(f"/api/securewise/findings/{finding.id}/")
        assert resp.status_code == 200
        data = resp.json()
        assert "severity" in data
        assert "title" in data

    def test_update_finding_status(self, auth_client, finding):
        resp = auth_client.patch(
            f"/api/securewise/findings/{finding.id}/",
            {"status": "fixed"},
            format="json",
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "fixed"

    def test_accept_risk(self, auth_client, finding):
        resp = auth_client.post(
            f"/api/securewise/findings/{finding.id}/accept-risk/",
            {"note": "Accepted by security team"},
            format="json",
        )
        assert resp.status_code == 200
        finding.refresh_from_db()
        assert finding.status == "accepted_risk"

    def test_mark_false_positive(self, auth_client, finding):
        resp = auth_client.post(
            f"/api/securewise/findings/{finding.id}/mark-false-positive/",
            {"note": "Not exploitable in this context"},
            format="json",
        )
        assert resp.status_code == 200
        finding.refresh_from_db()
        assert finding.status == "false_positive"

    def test_other_user_cannot_see_finding(self, other_client, finding):
        resp = other_client.get(f"/api/securewise/findings/{finding.id}/")
        assert resp.status_code == 404

    def test_filter_findings_by_severity(self, auth_client, completed_scan):
        resp = auth_client.get("/api/securewise/findings/?severity=critical")
        assert resp.status_code == 200

    def test_filter_findings_by_status(self, auth_client, completed_scan):
        resp = auth_client.get("/api/securewise/findings/?status=open")
        assert resp.status_code == 200

    def test_ai_suggestion_endpoint_returns_and_caches(self, auth_client, finding, owner):
        suggestion = {
            "explanation": "Validate and sanitize user input before use.",
            "why_dangerous": "Unsafe deserialization can execute attacker-controlled payloads.",
            "fixed_code_example": "data = json.loads(raw_bytes.decode())",
            "framework_guidance": "Prefer safe serializers in Django request handlers.",
            "confidence": "high",
        }
        with patch("apps.securewise.views.generate_ai_fix_suggestion", return_value=suggestion) as mock_generate:
            resp = auth_client.post(f"/api/securewise/findings/{finding.id}/ai-suggestion/")
            assert resp.status_code == 200
            assert resp.json() == {"ai_fix_suggestion": suggestion, "cached": False}

            finding.refresh_from_db()
            assert json.loads(finding.ai_fix_suggestion) == suggestion
            assert SecureWiseAuditLog.objects.filter(
                event="ai_suggestion_generated",
                target_type="SecureWiseFinding",
                target_id=str(finding.id),
            ).exists()

            cached_resp = auth_client.post(f"/api/securewise/findings/{finding.id}/ai-suggestion/")
            assert cached_resp.status_code == 200
            assert cached_resp.json() == {"ai_fix_suggestion": suggestion, "cached": True}
            assert mock_generate.call_count == 1

    def test_ai_suggestion_throttle_returns_429(self, auth_client, finding):
        cache.clear()
        suggestion = {
            "explanation": "Use parameterized queries.",
            "why_dangerous": "String interpolation can enable injection.",
            "fixed_code_example": "cursor.execute(query, [value])",
            "framework_guidance": "Use Django ORM filters or query parameters.",
            "confidence": "medium",
        }
        with (
            patch.object(AIRecommendationThrottle, "rate", "1/hour"),
            patch("apps.securewise.views.generate_ai_fix_suggestion", return_value=suggestion),
        ):
            first = auth_client.post(f"/api/securewise/findings/{finding.id}/ai-suggestion/")
            second = auth_client.post(f"/api/securewise/findings/{finding.id}/ai-suggestion/?force=true")

        assert first.status_code == 200
        assert second.status_code == 429
        cache.clear()


# ---------------------------------------------------------------------------
# Report endpoints
# ---------------------------------------------------------------------------


class TestReportAPI:
    def test_list_reports(self, auth_client, completed_scan, org, project, owner):
        SecureWiseReport.objects.create(
            organization=org,
            project=project,
            scan=completed_scan,
            title="Test Report",
            format="json",
            generated_by=owner,
            status="ready",
        )
        resp = auth_client.get("/api/securewise/reports/")
        assert resp.status_code == 200

    def test_create_report(self, auth_client, completed_scan, org, project):
        resp = auth_client.post(
            "/api/securewise/reports/",
            {
                "organization": str(org.id),
                "project": str(project.id),
                "scan": str(completed_scan.id),
                "title": "CI Report",
                "format": "json",
            },
            format="json",
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["format"] == "json"
        assert data["status"] in ("pending", "ready")

    def test_report_cannot_export_another_tenants_scan(self, auth_client, org, project, owner):
        foreign_org = SecureWiseOrganization.objects.create(name="Foreign", slug="report-foreign", owner=owner)
        SecureWiseMembership.objects.create(organization=foreign_org, user=owner, role="owner")
        foreign_project = SecureWiseProject.objects.create(
            organization=foreign_org,
            name="Foreign project",
            slug="foreign-project",
            created_by=owner,
        )
        foreign_scan = SecureWiseScan.objects.create(
            organization=foreign_org,
            project=foreign_project,
            scan_type="sast",
            status="completed",
            triggered_by=owner,
        )
        response = auth_client.post(
            "/api/securewise/reports/",
            {
                "organization": str(org.id),
                "project": str(project.id),
                "scan": str(foreign_scan.id),
                "title": "Cross-tenant report",
                "format": "json",
            },
            format="json",
        )
        assert response.status_code == 400
        assert "scan" in response.json()

    def test_worker_status_is_scoped_to_member_organizations(self, auth_client, other_client, org, project):
        scan = SecureWiseScan.objects.create(
            organization=org,
            project=project,
            scan_type="sast",
            status="queued",
            triggered_by=org.owner,
        )
        SecureWiseScanEngineResult.objects.create(scan=scan, engine="sast", status="completed")
        SecureWiseWorkerRegistration.objects.create(
            worker_id="worker-private-hostname",
            capabilities=["docker_daemon", "trivy"],
            metrics={"vmrss_kb": 128, "credential": "never expose"},
            status="online",
            last_seen_at=timezone.now(),
        )
        auditor = User.objects.create_user(
            username="worker_status_auditor", email="worker-status-auditor@sw.test", password="local-test-password"
        )
        SecureWiseMembership.objects.create(organization=org, user=auditor, role="auditor")
        auditor_client = APIClient()
        auditor_client.force_authenticate(auditor)
        owner_response = auth_client.get("/api/securewise/scans/worker-status/")
        stranger_response = other_client.get("/api/securewise/scans/worker-status/")
        auditor_response = auditor_client.get("/api/securewise/scans/worker-status/")
        assert owner_response.status_code == 200
        assert owner_response.json()["queue"]["queued_scans"] == 1
        assert owner_response.json()["worker_available"] is True
        assert owner_response.json()["resources"] == {"vmrss_kb": 128}
        assert owner_response.json()["engine_executions_last_7_days"] == [
            {"engine": "sast", "status": "completed", "count": 1, "average_duration_seconds": None}
        ]
        assert "worker-private-hostname" not in owner_response.content.decode()
        assert "credential" not in owner_response.content.decode()
        assert auditor_response.status_code == 200
        assert auditor_response.json()["resources"] == {}
        assert stranger_response.status_code == 403

    def test_tenant_cannot_read_other_tenants_scan_report_finding_or_evidence(
        self, other_client, completed_scan, org, project, repository, owner
    ):
        finding = SecureWiseFinding.objects.create(
            scan=completed_scan,
            project=project,
            organization=org,
            title="Tenant-scoped finding",
        )
        report = SecureWiseReport.objects.create(
            organization=org,
            project=project,
            scan=completed_scan,
            title="Tenant-scoped report",
            generated_by=owner,
            status="ready",
        )
        session = PentestSession.objects.create(
            organization=org,
            project=project,
            repository=repository,
            created_by=owner,
            authorization_confirmed=True,
            authorization_reference="controlled test authorization",
        )
        test_case = PentestTestCase.objects.create(
            session=session,
            test_key="tenant-case",
            title="Tenant evidence",
            category="authorization",
            expected_behavior="Evidence is visible only to organization members.",
        )
        execution = PentestExecution.objects.create(test_case=test_case, outcome="passed")
        evidence = PentestEvidence.objects.create(execution=execution, kind="assertion", content={"passed": True})

        protected_urls = (
            f"/api/securewise/scans/{completed_scan.id}/",
            f"/api/securewise/findings/{finding.id}/",
            f"/api/securewise/reports/{report.id}/",
            f"/api/securewise/reports/{report.id}/html/",
            f"/api/securewise/autopentest/sessions/{session.id}/",
        )
        assert all(other_client.get(url).status_code == 404 for url in protected_urls)
        assert evidence.execution.test_case.session.organization_id == org.id

    def test_report_html_endpoint(self, auth_client, completed_scan, org, project):
        create_resp = auth_client.post(
            "/api/securewise/reports/",
            {
                "organization": str(org.id),
                "project": str(project.id),
                "scan": str(completed_scan.id),
                "title": "SecureWise HTML Report",
                "format": "json",
            },
            format="json",
        )
        report_id = create_resp.json()["id"]

        resp = auth_client.get(f"/api/securewise/reports/{report_id}/html/")
        assert resp.status_code == 200
        assert resp["Content-Type"].startswith("text/html")
        content = resp.content.decode()
        assert "SecureWise" in content
        assert "SecureWise HTML Report" in content
        assert "Severity Counts" in content

    def test_report_pdf_endpoint(self, auth_client, completed_scan, org, project):
        create_resp = auth_client.post(
            "/api/securewise/reports/",
            {
                "organization": str(org.id),
                "project": str(project.id),
                "scan": str(completed_scan.id),
                "title": "SecureWise PDF Report",
                "format": "json",
            },
            format="json",
        )
        report_id = create_resp.json()["id"]

        with patch("apps.securewise.views.render_report_pdf", return_value=b"%PDF-1.4" + b"x" * 600):
            resp = auth_client.get(f"/api/securewise/reports/{report_id}/pdf/")
        assert resp.status_code == 200
        assert resp["Content-Type"] == "application/pdf"
        assert resp.content.startswith(b"%PDF")
        assert len(resp.content) > 500


# ---------------------------------------------------------------------------
# Dashboard endpoint
# ---------------------------------------------------------------------------


class TestDashboardAPI:
    def test_dashboard_summary(self, auth_client, completed_scan, org):
        resp = auth_client.get("/api/securewise/dashboard/summary/")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_projects" in data
        assert "total_scans" in data
        assert "open_findings" in data
        assert "security_score" in data
        assert "severity_counts" in data
        assert "recent_scans" in data
        assert "top_risky_projects" in data
        assert "critical_high_count" in data
        assert data["security_taxonomy"]["cwe_top25_edition"] == "MITRE CWE Top 25 2025"
        assert set(data["cwe_ids_covered"]).issubset(data["cwe_coverage"])
        assert len(data["cwe_coverage"]) == 25

    def test_dashboard_no_data(self, other_client):
        resp = other_client.get("/api/securewise/dashboard/summary/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_projects"] == 0
        assert data["total_scans"] == 0
        assert data["cwe_ids_covered"] == []


# ---------------------------------------------------------------------------
# Membership endpoints
# ---------------------------------------------------------------------------


class TestMembershipAPI:
    def test_list_memberships(self, auth_client, org):
        resp = auth_client.get("/api/securewise/memberships/")
        assert resp.status_code == 200
        results = _results(resp.json())
        assert any(m["role"] == "owner" for m in results)

    def test_add_member(self, auth_client, org, other_user):
        resp = auth_client.post(
            "/api/securewise/memberships/",
            {"organization": str(org.id), "user": other_user.id, "role": "developer"},
            format="json",
        )
        assert resp.status_code == 201

    def test_other_user_cannot_see_membership(self, other_client, org):
        resp = other_client.get("/api/securewise/memberships/")
        assert resp.status_code == 200
        results = _results(resp.json())
        # other_user is not a member of org, so no memberships visible
        assert all(str(m.get("organization")) != str(org.id) for m in results)
