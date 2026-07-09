"""
SecureWise — repository clone/validation helpers used by scan engines.

This module centralizes:
  - public repository validation (`git ls-remote`)
  - safe, path-traversal-resistant cloning into a scoped temp directory

Security rules:
  - Tokens are decrypted only by the caller and passed in; never logged here.
  - Any authenticated URL built here is deleted from scope as soon as possible.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlparse, urlunparse

logger = logging.getLogger(__name__)


class GitUnavailableError(RuntimeError):
    """Raised when the `git` binary is not installed/on PATH in this environment."""

    def __init__(self) -> None:
        super().__init__(
            "Git is not installed in this environment, so repository scanning is "
            "unavailable. Ask an administrator to install `git` on the scan runner."
        )


def _require_git() -> None:
    """Raise a clear, actionable error instead of letting a bare FileNotFoundError leak."""
    if shutil.which("git") is None:
        logger.error("git binary not found on PATH; repository scanning is unavailable")
        raise GitUnavailableError()


def validate_public_repo(url: str, timeout: int = 15) -> bool:
    """Return True if `git ls-remote --exit-code <url>` succeeds."""
    if shutil.which("git") is None:
        logger.warning("git binary not found on PATH; cannot validate repository %s", url)
        return False
    clone_url = url if url.endswith(".git") else url + ".git"
    try:
        result = subprocess.run(
            ["git", "ls-remote", "--exit-code", "--heads", clone_url],
            capture_output=True,
            timeout=timeout,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def _resolve_safe_dest(dest: Path, allowed_root: Path) -> Path:
    """Resolve `dest` and confirm it is contained within `allowed_root`."""
    resolved_root = allowed_root.resolve()
    resolved_dest = dest.resolve()
    if resolved_root != resolved_dest and resolved_root not in resolved_dest.parents:
        raise ValueError("Refusing to clone outside of the sandboxed temp directory.")
    return resolved_dest


def safe_clone(
    clone_url: str,
    dest: Path,
    allowed_root: Path | None = None,
    timeout: int = 120,
    shallow: bool = True,
) -> None:
    """
    Clone `clone_url` (which may already contain embedded credentials) into
    `dest`. `dest` must resolve to a path inside `allowed_root` (defaults to
    dest's own parent, i.e. the caller is expected to have created dest under
    a tempfile.TemporaryDirectory()).

    Never logs `clone_url` since it may contain a token.

    Raises GitUnavailableError if `git` is not installed in this environment,
    and RuntimeError with a clear message if the clone itself fails.
    """
    _require_git()
    allowed_root = allowed_root or dest.parent
    safe_dest = _resolve_safe_dest(dest, allowed_root)
    try:
        command = ["git", "clone"]
        if shallow:
            command.extend(["--depth", "1"])
        command.extend([clone_url, str(safe_dest)])
        subprocess.run(
            command,
            capture_output=True,
            timeout=timeout,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError("Failed to clone repository. Check the URL and access permissions.") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Cloning the repository timed out.") from exc
    except OSError as exc:
        # Defensive: _require_git() already checked, but guard against a TOCTOU
        # race (e.g. git removed mid-scan) with the same clear message instead
        # of leaking a raw "[Errno 2] No such file or directory: 'git'".
        raise GitUnavailableError() from exc
    finally:
        del clone_url


def build_authenticated_url(url: str, token: str) -> str:
    """Build an oauth2-token-authenticated clone URL. Caller must `del` the result ASAP."""
    parsed = urlparse(url)
    authed = parsed._replace(netloc=f"oauth2:{token}@{parsed.netloc}")
    return urlunparse(authed)


def clone_repository(scan, repo_path: Path, allowed_root: Path | None = None, timeout: int = 120) -> None:
    """
    Clone the repository attached to `scan` into `repo_path`.

    For private repos, decrypts the integration token only within this call
    and never logs it. `finally` blocks scrub sensitive locals.
    """
    repo = scan.repository
    if repo.access_mode == "local_path":
        copy_local_repository(repo.local_path, repo_path, allowed_root=allowed_root)
        return

    clone_url = repo.repository_url if repo.repository_url.endswith(".git") else repo.repository_url + ".git"

    if repo.access_mode == "integration" and repo.integration:
        token = repo.integration.get_token()
        authed_url = None
        try:
            if token:
                authed_url = build_authenticated_url(clone_url, token)
                safe_clone(authed_url, repo_path, allowed_root=allowed_root, timeout=timeout)
                return
        finally:
            del token
            if authed_url is not None:
                del authed_url

    safe_clone(clone_url, repo_path, allowed_root=allowed_root, timeout=timeout)


def validate_local_repository_path(path: str | Path) -> tuple[bool, str, Path | None]:
    repo_path = Path(path).expanduser()
    try:
        repo_path = repo_path.resolve()
    except OSError as exc:
        return False, f"Local path cannot be resolved: {exc}", None
    if not repo_path.exists():
        return False, "Local path does not exist.", None
    if not repo_path.is_dir():
        return False, "Local path is not a directory.", None
    if not os_access_readable(repo_path):
        return False, "Local path is not readable by the SecureWise backend process.", None
    try:
        if not any(repo_path.iterdir()):
            return False, "Local repository path is empty.", None
    except OSError:
        return False, "Local path cannot be read by the SecureWise backend process.", None
    return True, "Local repository path is accessible.", repo_path


def copy_local_repository(local_path: str | Path, dest: Path, allowed_root: Path | None = None) -> None:
    valid, message, source = validate_local_repository_path(local_path)
    if not valid or source is None:
        raise RuntimeError(message)
    allowed_root = allowed_root or dest.parent
    safe_dest = _resolve_safe_dest(dest, allowed_root)
    shutil.copytree(
        source,
        safe_dest,
        symlinks=False,
        ignore=shutil.ignore_patterns(".git", "node_modules", ".venv", "venv", "__pycache__", ".pytest_cache"),
    )


def os_access_readable(path: Path) -> bool:
    try:
        path.iterdir()
        return True
    except OSError:
        return False
