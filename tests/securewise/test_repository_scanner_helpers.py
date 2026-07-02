"""
SecureWise — unit tests for apps.securewise.scanners.repository:
public-repo validation, safe-clone path-traversal guarding, authenticated
URL construction, and the clone_repository() dispatch between public and
integration (private) access modes.
"""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from apps.securewise.scanners.repository import (
    _resolve_safe_dest,
    build_authenticated_url,
    clone_repository,
    safe_clone,
    validate_public_repo,
)

pytestmark = pytest.mark.django_db


class TestValidatePublicRepo:
    def test_returns_true_on_success(self):
        with patch("apps.securewise.scanners.repository.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            assert validate_public_repo("https://github.com/example/repo") is True

    def test_returns_false_on_nonzero_exit(self):
        with patch("apps.securewise.scanners.repository.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1)
            assert validate_public_repo("https://github.com/example/nope") is False

    def test_returns_false_on_timeout(self):
        with patch(
            "apps.securewise.scanners.repository.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="git", timeout=15),
        ):
            assert validate_public_repo("https://github.com/example/slow") is False

    def test_returns_false_on_oserror(self):
        with patch("apps.securewise.scanners.repository.subprocess.run", side_effect=OSError("git not found")):
            assert validate_public_repo("https://github.com/example/broken") is False

    def test_appends_git_suffix_when_missing(self):
        with patch("apps.securewise.scanners.repository.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            validate_public_repo("https://github.com/example/repo")
            called_args = mock_run.call_args[0][0]
            assert called_args[-1].endswith(".git")


class TestResolveSafeDest:
    def test_allows_dest_within_allowed_root(self, tmp_path):
        allowed_root = tmp_path
        dest = tmp_path / "clone-target"
        assert _resolve_safe_dest(dest, allowed_root) == dest.resolve()

    def test_rejects_dest_outside_allowed_root(self, tmp_path):
        allowed_root = tmp_path / "sandbox"
        allowed_root.mkdir()
        outside_dest = tmp_path / "escape"
        with pytest.raises(ValueError):
            _resolve_safe_dest(outside_dest, allowed_root)


class TestSafeClone:
    def test_successful_clone_invokes_git(self, tmp_path):
        dest = tmp_path / "repo"
        with patch("apps.securewise.scanners.repository.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            safe_clone("https://github.com/example/repo.git", dest, allowed_root=tmp_path)
        called_args = mock_run.call_args[0][0]
        assert called_args[0] == "git"
        assert "clone" in called_args
        assert "--depth" in called_args  # shallow=True by default

    def test_non_shallow_clone_omits_depth_flag(self, tmp_path):
        dest = tmp_path / "repo"
        with patch("apps.securewise.scanners.repository.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            safe_clone("https://github.com/example/repo.git", dest, allowed_root=tmp_path, shallow=False)
        called_args = mock_run.call_args[0][0]
        assert "--depth" not in called_args

    def test_clone_failure_raises_runtime_error(self, tmp_path):
        dest = tmp_path / "repo"
        with patch(
            "apps.securewise.scanners.repository.subprocess.run",
            side_effect=subprocess.CalledProcessError(returncode=128, cmd="git clone"),
        ):
            with pytest.raises(RuntimeError, match="Failed to clone repository"):
                safe_clone("https://github.com/example/repo.git", dest, allowed_root=tmp_path)

    def test_rejects_dest_outside_allowed_root(self, tmp_path):
        allowed_root = tmp_path / "sandbox"
        allowed_root.mkdir()
        outside_dest = tmp_path / "escape"
        with pytest.raises(ValueError):
            safe_clone("https://github.com/example/repo.git", outside_dest, allowed_root=allowed_root)


class TestBuildAuthenticatedUrl:
    def test_embeds_oauth2_token_in_netloc(self):
        url = build_authenticated_url("https://github.com/example/repo.git", "secret-token")
        assert url == "https://oauth2:secret-token@github.com/example/repo.git"

    def test_preserves_path(self):
        url = build_authenticated_url("https://gitlab.com/group/sub/repo.git", "tok")
        assert url.endswith("/group/sub/repo.git")


class TestCloneRepository:
    def test_public_repo_uses_plain_clone_url(self, tmp_path):
        repo = MagicMock()
        repo.repository_url = "https://github.com/example/repo"
        repo.access_mode = "public"
        repo.integration = None
        scan = MagicMock(repository=repo)
        repo_path = tmp_path / "clone"

        with patch("apps.securewise.scanners.repository.safe_clone") as mock_safe_clone:
            clone_repository(scan, repo_path, allowed_root=tmp_path)

        mock_safe_clone.assert_called_once()
        called_url = mock_safe_clone.call_args[0][0]
        assert called_url == "https://github.com/example/repo.git"
        assert "oauth2" not in called_url

    def test_integration_repo_uses_authenticated_url_and_scrubs_token(self, tmp_path):
        integration = MagicMock()
        integration.get_token.return_value = "super-secret-token"
        repo = MagicMock()
        repo.repository_url = "https://github.com/example/private-repo.git"
        repo.access_mode = "integration"
        repo.integration = integration
        scan = MagicMock(repository=repo)
        repo_path = tmp_path / "clone"

        with patch("apps.securewise.scanners.repository.safe_clone") as mock_safe_clone:
            clone_repository(scan, repo_path, allowed_root=tmp_path)

        mock_safe_clone.assert_called_once()
        called_url = mock_safe_clone.call_args[0][0]
        assert "super-secret-token" in called_url
        assert called_url.startswith("https://oauth2:super-secret-token@")

    def test_integration_repo_falls_back_to_plain_clone_when_token_missing(self, tmp_path):
        integration = MagicMock()
        integration.get_token.return_value = None
        repo = MagicMock()
        repo.repository_url = "https://github.com/example/private-repo.git"
        repo.access_mode = "integration"
        repo.integration = integration
        scan = MagicMock(repository=repo)
        repo_path = tmp_path / "clone"

        with patch("apps.securewise.scanners.repository.safe_clone") as mock_safe_clone:
            clone_repository(scan, repo_path, allowed_root=tmp_path)

        mock_safe_clone.assert_called_once()
        called_url = mock_safe_clone.call_args[0][0]
        assert called_url == "https://github.com/example/private-repo.git"
