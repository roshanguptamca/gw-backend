"""GitHub App API operations used for read-only repository access."""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import time
from urllib.parse import quote

import jwt
import requests
from django.utils import timezone

GITHUB_API = "https://api.github.com"
_API_HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "SecureWise-Security-Scanner",
}


class GitHubAppError(RuntimeError):
    pass


def app_configured() -> bool:
    return bool(os.environ.get("SECUREWISE_GITHUB_APP_ID") and os.environ.get("SECUREWISE_GITHUB_APP_PRIVATE_KEY"))


def app_slug() -> str:
    slug = os.environ.get("SECUREWISE_GITHUB_APP_SLUG", "")
    if not re.fullmatch(r"[A-Za-z0-9-]{1,39}", slug):
        raise GitHubAppError("GitHub App slug is not configured.")
    return slug


def _app_jwt() -> str:
    app_id = os.environ.get("SECUREWISE_GITHUB_APP_ID", "")
    private_key = os.environ.get("SECUREWISE_GITHUB_APP_PRIVATE_KEY", "").replace("\\n", "\n")
    if not app_id or not private_key:
        raise GitHubAppError("GitHub App credentials are not configured.")
    now = int(time.time())
    try:
        return jwt.encode({"iat": now - 60, "exp": now + 540, "iss": app_id}, private_key, algorithm="RS256")
    except (jwt.PyJWTError, ValueError, TypeError) as exc:
        raise GitHubAppError("GitHub App private key could not be loaded.") from exc


def _request(method: str, path: str, *, app_token: str | None = None, installation_token: str | None = None):
    if not path.startswith("/") or path.startswith("//"):
        raise GitHubAppError("Invalid GitHub API path.")
    headers = dict(_API_HEADERS)
    credential = installation_token or app_token
    if credential:
        headers["Authorization"] = f"Bearer {credential}"
    try:
        response = requests.request(
            method,
            f"{GITHUB_API}{path}",
            headers=headers,
            timeout=(5, 20),
            allow_redirects=False,
        )
    except requests.RequestException as exc:
        raise GitHubAppError("Could not reach the GitHub API.") from exc
    if response.is_redirect:
        raise GitHubAppError("GitHub API unexpectedly redirected the request.")
    if response.status_code < 200 or response.status_code >= 300:
        raise GitHubAppError(f"GitHub API returned HTTP {response.status_code}.")
    try:
        data = response.json()
    except ValueError as exc:
        raise GitHubAppError("GitHub API returned an invalid response.") from exc
    if not isinstance(data, dict):
        raise GitHubAppError("GitHub API returned an invalid response.")
    return data


def get_installation(installation_id: int) -> dict:
    return _request("GET", f"/app/installations/{installation_id}", app_token=_app_jwt())


def create_installation_token(installation_id: int) -> str:
    result = _request("POST", f"/app/installations/{installation_id}/access_tokens", app_token=_app_jwt())
    token = result.get("token")
    if not isinstance(token, str) or not token:
        raise GitHubAppError("GitHub did not issue an installation access token.")
    return token


def list_installation_repositories(installation_id: int) -> list[dict]:
    token = create_installation_token(installation_id)
    repositories: list[dict] = []
    try:
        for page in range(1, 11):
            data = _request(
                "GET",
                f"/installation/repositories?per_page=100&page={page}",
                installation_token=token,
            )
            items = data.get("repositories", [])
            if not isinstance(items, list):
                raise GitHubAppError("GitHub returned an invalid repository list.")
            if any(not isinstance(item, dict) for item in items):
                raise GitHubAppError("GitHub returned an invalid repository list.")
            repositories.extend(items)
            try:
                total_count = int(data.get("total_count", 0))
            except (TypeError, ValueError) as exc:
                raise GitHubAppError("GitHub returned an invalid repository count.") from exc
            if len(items) < 100 or len(repositories) >= total_count:
                break
    finally:
        del token
    return repositories


def get_commit_sha(installation_id: int, full_name: str, ref: str) -> str:
    token = create_installation_token(installation_id)
    try:
        result = _request(
            "GET",
            f"/repos/{quote(full_name, safe='/')}/commits/{quote(ref, safe='')}",
            installation_token=token,
        )
    finally:
        del token
    sha = result.get("sha", "")
    if not re.fullmatch(r"[0-9a-fA-F]{40}", sha):
        raise GitHubAppError("GitHub returned an invalid commit identifier.")
    return sha.lower()


def download_archive(installation_id: int, full_name: str, sha: str, output) -> None:
    """Download a pinned commit archive with no credential-bearing URL or redirects."""
    token = create_installation_token(installation_id)
    path = f"/repos/{quote(full_name, safe='/')}/zipball/{quote(sha, safe='')}"
    try:
        response = requests.get(
            f"{GITHUB_API}{path}",
            headers={**_API_HEADERS, "Authorization": f"Bearer {token}"},
            timeout=(5, 30),
            allow_redirects=False,
            stream=True,
        )
    except requests.RequestException as exc:
        raise GitHubAppError("Could not download the authorized repository archive.") from exc
    finally:
        del token

    try:
        if response.status_code not in (301, 302, 303, 307, 308):
            raise GitHubAppError(f"GitHub archive API returned HTTP {response.status_code}.")
        location = response.headers.get("Location", "")
        from urllib.parse import urlparse

        parsed = urlparse(location)
        if (
            parsed.scheme != "https"
            or parsed.hostname != "codeload.github.com"
            or parsed.port not in (None, 443)
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
        ):
            raise GitHubAppError("GitHub archive redirect destination is not permitted.")
        response.close()
        try:
            archive_response = requests.get(
                location,
                headers={"User-Agent": _API_HEADERS["User-Agent"]},
                timeout=(5, 60),
                allow_redirects=False,
                stream=True,
            )
        except requests.RequestException as exc:
            raise GitHubAppError("Could not retrieve the GitHub repository archive.") from exc
        try:
            if archive_response.status_code != 200:
                raise GitHubAppError(f"GitHub archive host returned HTTP {archive_response.status_code}.")
            total = 0
            for chunk in archive_response.iter_content(chunk_size=1024 * 1024):
                total += len(chunk)
                if total > 1024 * 1024 * 1024:
                    raise GitHubAppError("Repository archive exceeds the 1 GiB download limit.")
                output.write(chunk)
        finally:
            archive_response.close()
    finally:
        response.close()


def verify_webhook_signature(secret: str, body: bytes, signature: str) -> bool:
    if not secret or not signature.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def state_digest(raw_state: str) -> str:
    return hashlib.sha256(raw_state.encode()).hexdigest()


def installation_is_active(installation) -> bool:
    permissions = installation.permissions if isinstance(installation.permissions, dict) else {}
    return (
        installation.removed_at is None
        and installation.suspended_at is None
        and permissions.get("contents") == "read"
        and all(value == "read" for value in permissions.values())
    )


def mark_installation_event(installation, event_type: str, payload: dict) -> None:
    from django.utils.dateparse import parse_datetime

    details = payload.get("installation") or {}
    if not isinstance(details, dict):
        return
    if details.get("id") != installation.installation_id:
        return
    if event_type == "installation.deleted":
        installation.removed_at = timezone.now()
    elif event_type == "installation.suspend":
        suspended_at = parse_datetime(details.get("suspended_at") or "")
        installation.suspended_at = suspended_at if suspended_at and timezone.is_aware(suspended_at) else timezone.now()
    elif event_type == "installation.unsuspend":
        installation.suspended_at = None
    elif event_type == "installation.new_permissions_accepted":
        permissions = details.get("permissions")
        if isinstance(permissions, dict):
            installation.permissions = permissions
            installation.save(update_fields=["permissions", "updated_at"])
        return
    else:
        return
    installation.save(update_fields=["removed_at", "suspended_at", "updated_at"])
