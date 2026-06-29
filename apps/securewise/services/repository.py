"""
SecureWise — repository validation service.

Checks public/private reachability before saving a SecureWiseRepository.
"""

from __future__ import annotations

import logging
import re
import subprocess
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

PROVIDER_URL_MAP = {
    "github.com": "github",
    "gitlab.com": "gitlab",
    "bitbucket.org": "bitbucket",
    "dev.azure.com": "azure_devops",
}

_URL_RE = re.compile(r"^https?://[^\s/$.?#].[^\s]*$", re.IGNORECASE)


def detect_provider(url: str) -> str:
    """Detect Git provider from repository URL."""
    try:
        host = urlparse(url).hostname or ""
        for domain, provider in PROVIDER_URL_MAP.items():
            if domain in host:
                return provider
    except Exception:
        pass
    return "github"  # default


def normalize_url(url: str) -> str:
    """Strip trailing .git and whitespace."""
    return url.strip().rstrip("/").removesuffix(".git")


def validate_url_format(url: str) -> tuple[bool, str]:
    if not _URL_RE.match(url):
        return False, "Invalid repository URL format."
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False, "Only http/https URLs are supported."
    return True, ""


def check_public_access(url: str) -> tuple[bool, str]:
    """
    Try git ls-remote without credentials.
    Returns (accessible: bool, message: str).
    """
    clone_url = url if url.endswith(".git") else url + ".git"
    try:
        result = subprocess.run(
            ["git", "ls-remote", "--heads", clone_url],
            capture_output=True,
            timeout=15,
        )
        if result.returncode == 0:
            return True, "Repository is publicly accessible."
        stderr = result.stderr.decode(errors="replace")
        if "not found" in stderr.lower() or "404" in stderr:
            return False, "Repository not found. Check the URL."
        return False, "Repository is not publicly accessible. Please connect a Git provider integration."
    except subprocess.TimeoutExpired:
        return False, "Repository check timed out."
    except FileNotFoundError:
        # git not installed — skip check in dev
        logger.warning("git binary not found; skipping ls-remote check")
        return True, "Repository access check skipped (git not available)."
    except Exception as exc:
        logger.exception("Repository access check failed")
        return False, f"Repository access check failed: {exc}"


def check_private_access(url: str, token: str) -> tuple[bool, str]:
    """
    Try git ls-remote with oauth2 token.
    Token is NEVER logged.
    """
    from urllib.parse import urlparse, urlunparse

    clone_url = url if url.endswith(".git") else url + ".git"
    parsed = urlparse(clone_url)
    authed = parsed._replace(netloc=f"oauth2:{token}@{parsed.netloc}")
    authed_url = urlunparse(authed)
    try:
        result = subprocess.run(
            ["git", "ls-remote", "--heads", authed_url],
            capture_output=True,
            timeout=15,
            env={"GIT_TERMINAL_PROMPT": "0"},
        )
        del token, authed_url  # remove from scope immediately
        if result.returncode == 0:
            return True, "Repository access verified using integration."
        return False, "Repository is private or token does not have read access."
    except subprocess.TimeoutExpired:
        return False, "Repository check timed out."
    except FileNotFoundError:
        logger.warning("git binary not found; skipping ls-remote check")
        return True, "Repository access check skipped (git not available)."
    except Exception as exc:
        logger.exception("Private repository access check failed")
        return False, f"Repository access check failed: {exc}"
