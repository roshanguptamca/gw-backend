from __future__ import annotations

import json
import shutil
import subprocess
import urllib.error
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.securewise.models import (
    SecureWiseAuditLog,
    SecureWiseFinding,
    SecureWiseGitIntegration,
    SecureWiseMembership,
    SecureWiseOrganization,
    SecureWiseProject,
    SecureWiseRepository,
    SecureWiseScan,
)
from apps.securewise.services.github_actions import (
    GitHubActionError,
    create_github_issue,
    create_github_pr,
)
from apps.securewise.views import GitHubActionThrottle

User = get_user_model()
pytestmark = pytest.mark.django_db


class _FakeHTTPResponse:
    def __init__(self, status: int, payload: dict):
        self.status = status
        self._payload = payload

    def read(self):
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def _run(command: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(command, cwd=cwd, capture_output=True, check=True, text=True)


def _local_artifacts_root() -> Path:
    root = Path(settings.BASE_DIR) / ".test-securewise-github-actions"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _cleanup_path(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    parent = path.parent
    if parent.exists() and parent.name == ".test-securewise-github-actions" and not any(parent.iterdir()):
        parent.rmdir()


@pytest.fixture
def owner(db):
    return User.objects.create_user(username="gh_owner", email="gh_owner@sw.test", password="testpass123")


@pytest.fixture
def other_user(db):
    return User.objects.create_user(username="gh_other", email="gh_other@sw.test", password="testpass123")


@pytest.fixture
def auth_client(owner):
    client = APIClient()
    client.force_authenticate(user=owner)
    return client


@pytest.fixture
def other_client(other_user):
    client = APIClient()
    client.force_authenticate(user=other_user)
    return client


@pytest.fixture
def org(owner):
    organization = SecureWiseOrganization.objects.create(name="GitHub Org", slug=f"gh-org-{uuid4().hex[:6]}", owner=owner)
    SecureWiseMembership.objects.create(organization=organization, user=owner, role="owner")
    return organization


@pytest.fixture
def project(org, owner):
    return SecureWiseProject.objects.create(
        organization=org,
        name="GitHub Project",
        slug=f"gh-project-{uuid4().hex[:6]}",
        created_by=owner,
    )


@pytest.fixture
def integration(org, owner):
    instance = SecureWiseGitIntegration.objects.create(
        organization=org,
        provider="github",
        auth_type="personal_access_token",
        name="GitHub PAT",
        connected_by=owner,
    )
    instance.set_token("ghp_secret_token_123456789")
    instance.save()
    instance.refresh_from_db()
    return instance


@pytest.fixture
def repository(org, project, owner, integration):
    return SecureWiseRepository.objects.create(
        organization=org,
        project=project,
        integration=integration,
        name="securewise-repo",
        provider="github",
        repository_url="https://github.com/example/securewise-repo",
        clone_url="https://github.com/example/securewise-repo.git",
        access_mode="integration",
        default_branch="main",
        created_by=owner,
    )


@pytest.fixture
def scan(org, project, owner, repository):
    return SecureWiseScan.objects.create(
        organization=org,
        project=project,
        repository=repository,
        scan_type="sast",
        status="completed",
        triggered_by=owner,
    )


@pytest.fixture
def finding(org, project, scan):
    return SecureWiseFinding.objects.create(
        scan=scan,
        first_seen_scan=scan,
        project=project,
        organization=org,
        title="Unsafe deserialization via pickle",
        description="User-controlled bytes are deserialized without validation.",
        file_path="app.py",
        line_number=3,
        cwe_id="CWE-502",
        owasp_category="A08:2021",
        scanner_type="sast",
        severity="high",
        confidence="high",
        risk="Remote code execution is possible.",
        impact="Attackers may run arbitrary code on the server.",
        recommendation="Use json.loads for trusted JSON payloads instead of pickle.",
        bad_code_example="data = pickle.loads(raw_bytes)",
        fixed_code_example="data = json.loads(raw_bytes.decode())",
        code_snippet="data = pickle.loads(raw_bytes)",
    )


@pytest.fixture
def local_remote_repo():
    root = _local_artifacts_root() / uuid4().hex
    seed_repo = root / "seed"
    bare_repo = root / "remote.git"
    seed_repo.mkdir(parents=True, exist_ok=True)
    try:
        _run(["git", "init", "-b", "main"], cwd=seed_repo)
        _run(["git", "config", "user.email", "tests@guidewisey.local"], cwd=seed_repo)
        _run(["git", "config", "user.name", "SecureWise Tests"], cwd=seed_repo)
        (seed_repo / "app.py").write_text(
            "import json\n"
            "import pickle\n"
            "data = pickle.loads(raw_bytes)\n",
            encoding="utf-8",
        )
        _run(["git", "add", "app.py"], cwd=seed_repo)
        _run(["git", "commit", "-m", "Initial commit"], cwd=seed_repo)
        _run(["git", "init", "--bare", "--initial-branch=main", str(bare_repo)])
        _run(["git", "remote", "add", "origin", str(bare_repo)], cwd=seed_repo)
        _run(["git", "push", "origin", "main"], cwd=seed_repo)
        yield {"root": root, "seed_repo": seed_repo, "bare_repo": bare_repo}
    finally:
        _cleanup_path(root)


class TestCreateGitHubIssue:
    def test_success(self, finding):
        captured: dict[str, object] = {}

        def fake_urlopen(request, timeout=0, context=None):
            captured["url"] = request.full_url
            captured["method"] = request.get_method()
            captured["authorization"] = request.get_header("Authorization")
            captured["accept"] = request.get_header("Accept")
            captured["user_agent"] = request.get_header("User-agent")
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return _FakeHTTPResponse(201, {"html_url": "https://github.com/example/securewise-repo/issues/99"})

        with patch("apps.securewise.services.github_actions.urllib.request.urlopen", side_effect=fake_urlopen):
            issue_url = create_github_issue(finding)

        assert issue_url == "https://github.com/example/securewise-repo/issues/99"
        assert captured["url"] == "https://api.github.com/repos/example/securewise-repo/issues"
        assert captured["method"] == "POST"
        assert captured["authorization"] == "token ghp_secret_token_123456789"
        assert captured["accept"] == "application/vnd.github+json"
        assert captured["user_agent"] == "SecureWise-SASP/1.0"
        assert captured["body"]["title"] == "[SecureWise] Unsafe deserialization via pickle"
        assert "CWE-502" in captured["body"]["body"]
        assert str(finding.id) in captured["body"]["body"]

    def test_requires_integration_write_access(self, org, project, owner, scan):
        public_repo = SecureWiseRepository.objects.create(
            organization=org,
            project=project,
            name="public-repo",
            provider="github",
            repository_url="https://github.com/example/public-repo",
            clone_url="https://github.com/example/public-repo.git",
            access_mode="public",
            created_by=owner,
        )
        scan.repository = public_repo
        scan.save(update_fields=["repository"])
        finding = SecureWiseFinding.objects.create(
            scan=scan,
            project=project,
            organization=org,
            title="Missing auth",
        )

        with pytest.raises(GitHubActionError) as excinfo:
            create_github_issue(finding)

        message = str(excinfo.value)
        assert "no GitHub integration configured with write access" in message
        assert "ghp_secret_token_123456789" not in message

    def test_surfaces_clean_scope_error(self, finding):
        error = urllib.error.HTTPError(
            url="https://api.github.com/repos/example/securewise-repo/issues",
            code=403,
            msg="Forbidden",
            hdrs=None,
            fp=BytesIO(b'{"message":"Resource not accessible by personal access token"}'),
        )

        with patch("apps.securewise.services.github_actions.urllib.request.urlopen", side_effect=error):
            with pytest.raises(GitHubActionError) as excinfo:
                create_github_issue(finding)

        message = str(excinfo.value)
        assert "GitHub rejected the request: Resource not accessible by personal access token." in message
        assert "needs 'repo'" in message
        assert "ghp_secret_token_123456789" not in message


class TestCreateGitHubPullRequest:
    def test_success(self, finding, repository, local_remote_repo):
        repository.clone_url = str(local_remote_repo["bare_repo"])
        repository.save(update_fields=["clone_url"])

        with patch(
            "apps.securewise.services.github_actions.urllib.request.urlopen",
            return_value=_FakeHTTPResponse(201, {"html_url": "https://github.com/example/securewise-repo/pull/7"}),
        ):
            pr_url = create_github_pr(finding)

        assert pr_url == "https://github.com/example/securewise-repo/pull/7"

        inspect_repo = local_remote_repo["root"] / "inspect"
        _run(["git", "clone", str(local_remote_repo["bare_repo"]), str(inspect_repo)])
        try:
            branch_name = f"securewise/fix-{str(finding.id)[:8]}"
            remote_branch = f"origin/{branch_name}"
            branches = _run(["git", "branch", "-a"], cwd=inspect_repo).stdout
            assert branch_name in branches

            fixed_file = _run(["git", "show", f"{remote_branch}:app.py"], cwd=inspect_repo).stdout
            assert "data = json.loads(raw_bytes.decode())" in fixed_file
            assert "data = pickle.loads(raw_bytes)" not in fixed_file

            commit_subject = _run(["git", "log", remote_branch, "-1", "--pretty=%s"], cwd=inspect_repo).stdout.strip()
            assert commit_subject == "SecureWise: fix Unsafe deserialization via pickle (CWE-502)"
        finally:
            _cleanup_path(inspect_repo)

    def test_failure_when_exact_code_not_found_cleans_up(self, finding, repository, local_remote_repo):
        repository.clone_url = str(local_remote_repo["bare_repo"])
        repository.save(update_fields=["clone_url"])
        finding.bad_code_example = "data = pickle.loads(other_bytes)"
        finding.save(update_fields=["bad_code_example"])

        scratch_root = Path(settings.BASE_DIR) / ".securewise-github-actions"
        if scratch_root.exists():
            shutil.rmtree(scratch_root)

        with pytest.raises(GitHubActionError) as excinfo:
            create_github_pr(finding)

        assert "Could not locate the exact vulnerable code" in str(excinfo.value)
        assert not scratch_root.exists() or not any(scratch_root.iterdir())

    def test_failure_when_finding_lacks_code_data(self, finding):
        finding.file_path = ""
        finding.bad_code_example = ""
        finding.fixed_code_example = ""

        with patch("apps.securewise.services.github_actions.subprocess.run") as mock_run:
            with pytest.raises(GitHubActionError) as excinfo:
                create_github_pr(finding)

        assert "doesn't have enough information" in str(excinfo.value)
        mock_run.assert_not_called()


class TestFindingGitHubActionViews:
    def test_create_ticket_success(self, auth_client, finding):
        with patch(
            "apps.securewise.views.create_github_issue",
            return_value="https://github.com/example/securewise-repo/issues/11",
        ):
            response = auth_client.post(f"/api/securewise/findings/{finding.id}/create-ticket/")

        assert response.status_code == 200
        assert response.json() == {"ticket_url": "https://github.com/example/securewise-repo/issues/11"}
        finding.refresh_from_db()
        assert finding.ticket_url.endswith("/issues/11")
        assert finding.ticket_created_at is not None
        assert SecureWiseAuditLog.objects.filter(
            event="finding_ticket_created",
            target_type="SecureWiseFinding",
            target_id=str(finding.id),
        ).exists()

    def test_create_ticket_failure(self, auth_client, finding):
        with patch(
            "apps.securewise.views.create_github_issue",
            side_effect=GitHubActionError("GitHub rejected the request: Forbidden. Check token scopes (needs 'repo')."),
        ):
            response = auth_client.post(f"/api/securewise/findings/{finding.id}/create-ticket/")

        assert response.status_code == 400
        assert "needs 'repo'" in response.json()["detail"]
        assert SecureWiseAuditLog.objects.filter(
            event="finding_ticket_failed",
            target_type="SecureWiseFinding",
            target_id=str(finding.id),
        ).exists()

    def test_create_pr_success(self, auth_client, finding):
        with patch(
            "apps.securewise.views.create_github_pr",
            return_value="https://github.com/example/securewise-repo/pull/12",
        ):
            response = auth_client.post(f"/api/securewise/findings/{finding.id}/create-pr/")

        assert response.status_code == 200
        assert response.json() == {"pr_url": "https://github.com/example/securewise-repo/pull/12"}
        finding.refresh_from_db()
        assert finding.pr_url.endswith("/pull/12")
        assert finding.pr_created_at is not None
        assert SecureWiseAuditLog.objects.filter(
            event="finding_pr_created",
            target_type="SecureWiseFinding",
            target_id=str(finding.id),
        ).exists()

    def test_create_pr_failure(self, auth_client, finding):
        with patch(
            "apps.securewise.views.create_github_pr",
            side_effect=GitHubActionError("Could not locate the exact vulnerable code in the current version of the file."),
        ):
            response = auth_client.post(f"/api/securewise/findings/{finding.id}/create-pr/")

        assert response.status_code == 400
        assert "Could not locate the exact vulnerable code" in response.json()["detail"]
        assert SecureWiseAuditLog.objects.filter(
            event="finding_pr_failed",
            target_type="SecureWiseFinding",
            target_id=str(finding.id),
        ).exists()

    def test_non_member_gets_404(self, other_client, finding):
        response = other_client.post(f"/api/securewise/findings/{finding.id}/create-ticket/")
        assert response.status_code == 404

    def test_github_action_throttle_returns_429(self, auth_client, finding):
        cache.clear()
        with patch.object(GitHubActionThrottle, "rate", "1/hour", create=True), patch(
            "apps.securewise.views.create_github_issue",
            return_value="https://github.com/example/securewise-repo/issues/22",
        ):
            first = auth_client.post(f"/api/securewise/findings/{finding.id}/create-ticket/")
            second = auth_client.post(f"/api/securewise/findings/{finding.id}/create-ticket/")

        assert first.status_code == 200
        assert second.status_code == 429
        cache.clear()
