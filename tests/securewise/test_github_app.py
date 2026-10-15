from __future__ import annotations

import hashlib
import hmac
import io
import json
import zipfile
from datetime import timedelta
from unittest.mock import Mock, patch

from django.utils import timezone

import pytest
from rest_framework.test import APIClient

from apps.securewise.models import (
    SecureWiseGitHubAppInstallation,
    SecureWiseGitHubAppState,
    SecureWiseGitHubWebhookDelivery,
    SecureWiseMembership,
    SecureWiseOrganization,
    SecureWiseProject,
    SecureWiseRepository,
    SecureWiseScan,
)
from apps.securewise.scanners.orchestrator import ScannerOrchestrator
from apps.securewise.scanners.repository import clone_repository, extract_pinned_archive
from apps.securewise.services.github_app import (
    GitHubAppError,
    mark_installation_event,
    state_digest,
    verify_webhook_signature,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def github_workspace(db, django_user_model):
    owner = django_user_model.objects.create_user(username="github_owner", email="owner@example.test")
    outsider = django_user_model.objects.create_user(username="github_outsider", email="other@example.test")
    organization = SecureWiseOrganization.objects.create(name="GitHub Org", slug="github-org", owner=owner)
    SecureWiseMembership.objects.create(organization=organization, user=owner, role="owner")
    project = SecureWiseProject.objects.create(organization=organization, name="App", slug="app", created_by=owner)
    client = APIClient()
    client.force_authenticate(user=owner)
    return owner, outsider, organization, project, client


def test_connect_requires_admin_and_returns_single_use_state(github_workspace, monkeypatch):
    owner, outsider, organization, _, client = github_workspace
    monkeypatch.setattr("apps.securewise.services.github_app.app_configured", lambda: True)
    monkeypatch.setattr("apps.securewise.services.github_app.app_slug", lambda: "securewise")

    response = client.post(
        "/api/securewise/github-app/connect/",
        {"organization": str(organization.id)},
        format="json",
    )
    assert response.status_code == 200
    state = response.json()["installation_url"].split("state=", 1)[1]
    assert SecureWiseGitHubAppState.objects.filter(
        state_digest=state_digest(state), user=owner, consumed_at__isnull=True
    ).exists()
    assert state not in SecureWiseGitHubAppState.objects.values_list("state_digest", flat=True)

    client.force_authenticate(user=outsider)
    response = client.post(
        "/api/securewise/github-app/connect/",
        {"organization": str(organization.id)},
        format="json",
    )
    assert response.status_code == 403


def test_callback_consumes_state_and_persists_no_token(github_workspace, monkeypatch):
    owner, _, organization, _, client = github_workspace
    raw_state = "state-value-used-once"
    SecureWiseGitHubAppState.objects.create(
        state_digest=state_digest(raw_state),
        organization=organization,
        user=owner,
        expires_at=timezone.now() + timedelta(minutes=5),
    )
    monkeypatch.setattr("apps.securewise.services.github_app.app_configured", lambda: True)
    monkeypatch.setattr(
        "apps.securewise.services.github_app.get_installation",
        lambda installation_id: {
            "id": installation_id,
            "account": {"id": 42, "login": "customer-org", "type": "Organization"},
            "permissions": {"metadata": "read", "contents": "read"},
            "created_at": timezone.now().isoformat(),
        },
    )

    response = client.get(
        "/api/securewise/github-app/callback/",
        {"state": raw_state, "installation_id": "1234", "setup_action": "install"},
    )
    assert response.status_code == 200
    installation = SecureWiseGitHubAppInstallation.objects.get(installation_id=1234)
    assert installation.organization == organization
    assert "token" not in response.content.decode().lower()
    assert not hasattr(installation, "_encrypted_access_token")

    replay = client.get(
        "/api/securewise/github-app/callback/",
        {"state": raw_state, "installation_id": "1234", "setup_action": "install"},
    )
    assert replay.status_code == 400


def test_callback_rejects_write_permissions(github_workspace, monkeypatch):
    owner, _, organization, _, client = github_workspace
    state = "write-permission-state"
    SecureWiseGitHubAppState.objects.create(
        state_digest=state_digest(state),
        organization=organization,
        user=owner,
        expires_at=timezone.now() + timedelta(minutes=5),
    )
    monkeypatch.setattr("apps.securewise.services.github_app.app_configured", lambda: True)
    monkeypatch.setattr(
        "apps.securewise.services.github_app.get_installation",
        lambda installation_id: {
            "id": installation_id,
            "account": {"id": 42, "login": "customer-org"},
            "permissions": {"contents": "write"},
            "created_at": timezone.now().isoformat(),
        },
    )
    response = client.get(
        "/api/securewise/github-app/callback/",
        {"state": state, "installation_id": "1234", "setup_action": "install"},
    )
    assert response.status_code == 403
    assert not SecureWiseGitHubAppInstallation.objects.exists()


def test_callback_cannot_rebind_installation_across_organizations(github_workspace, monkeypatch, django_user_model):
    owner, _, organization, _, client = github_workspace
    other_owner = django_user_model.objects.create_user(username="other_org_owner")
    other_org = SecureWiseOrganization.objects.create(name="Other", slug="other-org", owner=other_owner)
    existing = SecureWiseGitHubAppInstallation.objects.create(
        organization=other_org,
        installation_id=4321,
        account_id=42,
        account_login="customer-org",
        permissions={"metadata": "read", "contents": "read"},
    )
    state = "org-rebinding-state"
    SecureWiseGitHubAppState.objects.create(
        state_digest=state_digest(state),
        organization=organization,
        user=owner,
        expires_at=timezone.now() + timedelta(minutes=5),
    )
    monkeypatch.setattr("apps.securewise.services.github_app.app_configured", lambda: True)
    monkeypatch.setattr(
        "apps.securewise.services.github_app.get_installation",
        lambda installation_id: {
            "id": installation_id,
            "account": {"id": 42, "login": "customer-org"},
            "permissions": {"metadata": "read", "contents": "read"},
        },
    )
    response = client.get(
        "/api/securewise/github-app/callback/",
        {"state": state, "installation_id": "4321", "setup_action": "update"},
    )
    assert response.status_code == 409
    existing.refresh_from_db()
    assert existing.organization == other_org


def test_repository_selection_is_installation_and_org_scoped(github_workspace, monkeypatch):
    owner, outsider, organization, project, client = github_workspace
    installation = SecureWiseGitHubAppInstallation.objects.create(
        organization=organization,
        installation_id=777,
        account_id=42,
        account_login="customer-org",
        permissions={"contents": "read", "metadata": "read"},
    )
    monkeypatch.setattr(
        "apps.securewise.services.github_app.list_installation_repositories",
        lambda installation_id: [
            {
                "id": 987,
                "full_name": "customer-org/private-app",
                "private": True,
                "default_branch": "main",
            }
        ],
    )
    response = client.post(
        "/api/securewise/github-app/repositories/select/",
        {"installation": str(installation.id), "repository_ids": [987], "project": str(project.id)},
        format="json",
    )
    assert response.status_code == 200
    repository = SecureWiseRepository.objects.get(provider_repository_id=987)
    assert repository.access_mode == "github_app"
    assert repository.github_app_installation == installation
    assert repository.project == project
    assert repository.clone_url == ""

    client.force_authenticate(user=outsider)
    response = client.post(
        "/api/securewise/github-app/repositories/select/",
        {"installation": str(installation.id), "repository_ids": [987]},
        format="json",
    )
    assert response.status_code == 404

    owner_client = APIClient()
    owner_client.force_authenticate(user=owner)
    response = owner_client.patch(
        f"/api/securewise/repositories/{repository.id}/",
        {"name": "customer-org/another-repository"},
        format="json",
    )
    assert response.status_code == 400


def test_github_app_repository_snapshot_pins_commit_and_extracts_safely(github_workspace, tmp_path, monkeypatch):
    owner, _, organization, project, _ = github_workspace
    installation = SecureWiseGitHubAppInstallation.objects.create(
        organization=organization,
        installation_id=777,
        account_id=42,
        account_login="customer-org",
        permissions={"contents": "read", "metadata": "read"},
    )
    repository = SecureWiseRepository.objects.create(
        organization=organization,
        project=project,
        github_app_installation=installation,
        provider_repository_id=987,
        name="customer-org/private-app",
        provider="github",
        repository_url="https://github.com/customer-org/private-app",
        default_branch="main",
        visibility="private",
        access_mode="github_app",
    )
    scan = SecureWiseScan.objects.create(
        organization=organization,
        project=project,
        repository=repository,
        scan_type="sast",
        branch="main",
    )
    sha = "a" * 40
    monkeypatch.setattr(
        "apps.securewise.services.github_app.get_commit_sha",
        lambda installation_id, full_name, ref: sha,
    )

    def write_archive(installation_id, full_name, commit_sha, output):
        with zipfile.ZipFile(output, "w") as archive:
            archive.writestr("repo-root/src/app.py", "print('static source only')\n")

    monkeypatch.setattr("apps.securewise.services.github_app.download_archive", write_archive)
    destination = tmp_path / "repo"
    clone_repository(scan, destination, allowed_root=tmp_path)

    scan.refresh_from_db()
    assert scan.commit_sha == sha
    assert (destination / "src/app.py").read_text() == "print('static source only')\n"


def test_github_app_scan_never_enters_runtime_build_gate(github_workspace, tmp_path, monkeypatch):
    owner, _, organization, project, _ = github_workspace
    installation = SecureWiseGitHubAppInstallation.objects.create(
        organization=organization,
        installation_id=777,
        account_id=42,
        account_login="customer-org",
    )
    repository = SecureWiseRepository.objects.create(
        organization=organization,
        project=project,
        github_app_installation=installation,
        provider_repository_id=987,
        name="customer-org/private-app",
        provider="github",
        repository_url="https://github.com/customer-org/private-app",
        default_branch="main",
        visibility="private",
        access_mode="github_app",
    )
    scan = SecureWiseScan.objects.create(
        organization=organization,
        project=project,
        repository=repository,
        scan_type="full",
    )
    (tmp_path / "Dockerfile").write_text("FROM scratch\nRUN touch /tmp/build-was-run\n")

    class RuntimePlan:
        requires_runtime = True
        can_auto_run = True
        skip_reasons = []

        def to_dict(self):
            return {}

    monkeypatch.setattr(ScannerOrchestrator, "resolve_engines", lambda self, scan, repo_path: ["dast", "container"])
    monkeypatch.setattr(
        "apps.securewise.scanners.orchestrator.ApplicationDiscoveryEngine.discover",
        lambda self, repo_path: RuntimePlan(),
    )
    monkeypatch.setattr(
        "apps.securewise.runtime.trust.trusted_runtime_content",
        lambda *args: pytest.fail("GitHub App repository must bypass content-based runtime trust"),
    )
    monkeypatch.setattr(
        "apps.securewise.scanners.orchestrator.RuntimeEnvironmentManager",
        lambda: pytest.fail("GitHub App repository must never construct a runtime manager"),
    )

    _, engine_results, _, skipped = ScannerOrchestrator().run(scan, tmp_path)
    assert skipped
    assert "dast_skip_reason" in engine_results["dast"]
    assert SecureWiseScan.objects.get(id=scan.id).engine_results.filter(status="skipped").count() == 2


def test_archive_extraction_rejects_zip_slip_and_symlinks(tmp_path):
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr("root/../../escape.txt", "unsafe")
    archive.seek(0)
    with pytest.raises(RuntimeError, match="unsafe path"):
        extract_pinned_archive(archive, tmp_path / "bad", tmp_path)
    assert not (tmp_path / "escape.txt").exists()


def test_archive_extraction_rejects_symlinks_and_multiple_roots(tmp_path):
    symlink_archive = io.BytesIO()
    symlink = zipfile.ZipInfo("root/link")
    symlink.create_system = 3
    symlink.external_attr = (0o120777 << 16) | 0xA000
    with zipfile.ZipFile(symlink_archive, "w") as zipped:
        zipped.writestr(symlink, "target")
    symlink_archive.seek(0)
    with pytest.raises(RuntimeError, match="special file"):
        extract_pinned_archive(symlink_archive, tmp_path / "symlink", tmp_path)

    multiple_roots = io.BytesIO()
    with zipfile.ZipFile(multiple_roots, "w") as zipped:
        zipped.writestr("root-a/a.txt", "a")
        zipped.writestr("root-b/b.txt", "b")
    multiple_roots.seek(0)
    with pytest.raises(RuntimeError, match="multiple root"):
        extract_pinned_archive(multiple_roots, tmp_path / "roots", tmp_path)


def test_github_api_uses_bearer_header_and_never_follows_redirects(monkeypatch):
    import apps.securewise.services.github_app as github_app

    response = Mock(status_code=200, is_redirect=False)
    response.json.return_value = {"ok": True}
    with patch("apps.securewise.services.github_app.requests.request", return_value=response) as request:
        assert github_app._request("GET", "/installation/repositories", installation_token="temporary-token") == {
            "ok": True
        }
    args, kwargs = request.call_args
    assert args[1] == "https://api.github.com/installation/repositories"
    assert kwargs["headers"]["Authorization"] == "Bearer temporary-token"
    assert kwargs["allow_redirects"] is False

    redirect = Mock(status_code=302, is_redirect=True, headers={"Location": "https://evil.example/archive"})
    with patch("apps.securewise.services.github_app.create_installation_token", return_value="temporary-token"):
        with patch("apps.securewise.services.github_app.requests.get", return_value=redirect) as get:
            with pytest.raises(GitHubAppError, match="redirect destination"):
                github_app.download_archive(12, "org/repo", "a" * 40, io.BytesIO())
    assert get.call_count == 1


def test_webhook_signature_replay_and_installation_suspension(github_workspace, monkeypatch):
    _, _, organization, _, client = github_workspace
    installation = SecureWiseGitHubAppInstallation.objects.create(
        organization=organization,
        installation_id=777,
        account_id=42,
        account_login="customer-org",
    )
    secret = "test-webhook-secret"
    monkeypatch.setenv("SECUREWISE_GITHUB_APP_WEBHOOK_SECRET", secret)
    payload = {
        "action": "suspend",
        "installation": {
            "id": 777,
            "suspended_at": timezone.now().isoformat(),
        },
    }
    body = json.dumps(payload).encode()
    signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    headers = {
        "HTTP_X_HUB_SIGNATURE_256": signature,
        "HTTP_X_GITHUB_DELIVERY": "delivery-123",
        "HTTP_X_GITHUB_EVENT": "installation",
    }

    assert verify_webhook_signature(secret, body, signature)
    invalid = client.post(
        "/api/securewise/github-app/webhook/",
        data=body,
        content_type="application/json",
        HTTP_X_HUB_SIGNATURE_256="sha256=invalid",
        HTTP_X_GITHUB_DELIVERY="delivery-invalid",
        HTTP_X_GITHUB_EVENT="installation",
    )
    assert invalid.status_code == 401
    response = client.post(
        "/api/securewise/github-app/webhook/",
        data=body,
        content_type="application/json",
        **headers,
    )
    assert response.status_code == 202
    installation.refresh_from_db()
    assert installation.suspended_at is not None
    assert SecureWiseGitHubWebhookDelivery.objects.count() == 1

    replay = client.post(
        "/api/securewise/github-app/webhook/",
        data=body,
        content_type="application/json",
        **headers,
    )
    assert replay.status_code == 202
    assert SecureWiseGitHubWebhookDelivery.objects.count() == 1


def test_new_write_permission_webhook_blocks_future_repository_use(github_workspace):
    _, _, organization, _, _ = github_workspace
    installation = SecureWiseGitHubAppInstallation.objects.create(
        organization=organization,
        installation_id=888,
        account_id=84,
        account_login="customer-org",
        permissions={"contents": "read", "metadata": "read"},
    )
    mark_installation_event(
        installation,
        "installation.new_permissions_accepted",
        {"installation": {"id": 888, "permissions": {"contents": "write", "metadata": "read"}}},
    )
    installation.refresh_from_db()
    from apps.securewise.services.github_app import installation_is_active

    assert not installation_is_active(installation)
