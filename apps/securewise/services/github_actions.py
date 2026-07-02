"""
SecureWise GitHub issue + pull request automation for findings.
"""

from __future__ import annotations

import json
import ssl
import subprocess
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

import certifi
from django.conf import settings

from apps.securewise.scanners.repository import _resolve_safe_dest, build_authenticated_url, safe_clone


class GitHubActionError(Exception):
    """User-safe error raised when a GitHub action cannot be completed."""


def _parse_github_owner_repo(repository_url: str) -> tuple[str, str]:
    parsed = urlparse((repository_url or "").strip())
    if parsed.scheme not in {"http", "https"} or parsed.netloc.lower() != "github.com":
        raise GitHubActionError("Only github.com repositories are supported for this action right now.")

    path = parsed.path.rstrip("/")
    if path.endswith(".git"):
        path = path[:-4]
    parts = [part for part in path.split("/") if part]
    if len(parts) < 2:
        raise GitHubActionError("This repository URL is not a valid GitHub repository URL.")
    return parts[0], parts[1]


def _resolve_repository_for_finding(finding):
    repository = getattr(getattr(finding, "scan", None), "repository", None)
    if repository is not None:
        return repository

    project = getattr(finding, "project", None)
    if project is not None:
        repository = project.repositories.order_by("-created_at").first()
        if repository is not None:
            return repository

    raise GitHubActionError("No repository is linked to this finding.")


def _get_write_token(repository) -> str:
    if repository.access_mode != "integration" or repository.integration is None:
        raise GitHubActionError(
            "This repository has no GitHub integration configured with write access. "
            "Add a personal access token with 'repo' scope in Integrations settings."
        )

    token = repository.integration.get_token()
    if not token:
        raise GitHubActionError(
            "This repository has no GitHub integration configured with write access. "
            "Add a personal access token with 'repo' scope in Integrations settings."
        )
    return token


def _github_api_request(method: str, url: str, token: str, body: dict | None = None, timeout: int = 20) -> dict:
    ssl_context = ssl.create_default_context(cafile=certifi.where())
    payload = None if body is None else json.dumps(body).encode("utf-8")
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
        "User-Agent": "SecureWise-SASP/1.0",
    }
    request = urllib.request.Request(url, data=payload, headers=headers, method=method.upper())

    try:
        with urllib.request.urlopen(request, timeout=timeout, context=ssl_context) as response:
            raw_body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        raw_body = exc.read().decode("utf-8", errors="replace")
        message = "GitHub rejected the request."
        try:
            payload = json.loads(raw_body)
        except (TypeError, ValueError):
            payload = None
        if isinstance(payload, dict):
            reason = str(payload.get("message", "")).strip()
            if reason:
                message = f"GitHub rejected the request: {reason}."
        if exc.code in {401, 403}:
            message = f"{message} Check token scopes (needs 'repo')."
        raise GitHubActionError(message) from exc
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, ssl.SSLCertVerificationError) or "CERTIFICATE_VERIFY_FAILED" in str(exc.reason):
            raise GitHubActionError(
                "SSL certificate verification failed while contacting GitHub. "
                "Ensure the 'certifi' package is installed and up to date in this environment."
            ) from exc
        raise GitHubActionError(f"Could not reach GitHub: {exc.reason}") from exc
    except Exception as exc:
        raise GitHubActionError("Unexpected error while contacting GitHub.") from exc

    if not raw_body.strip():
        return {}
    try:
        return json.loads(raw_body)
    except (TypeError, ValueError) as exc:
        raise GitHubActionError("GitHub returned an unexpected response.") from exc


def _truncate_title(title: str, limit: int = 250) -> str:
    normalized = (title or "").strip() or "Security finding"
    return normalized[:limit]


def _finding_location(finding) -> str:
    if finding.file_path:
        return f"{finding.file_path}:{finding.line_number}" if finding.line_number else finding.file_path
    return finding.endpoint or "Not provided"


def _append_markdown_section(lines: list[str], heading: str, value: str) -> None:
    text = (value or "").strip()
    if not text:
        return
    lines.extend([f"### {heading}", text, ""])


def _append_code_block(lines: list[str], heading: str, value: str) -> None:
    text = (value or "").strip()
    if not text:
        return
    lines.extend([f"### {heading}", "```", text, "```", ""])


def _build_issue_body(finding) -> str:
    lines = [
        "## SecureWise Finding",
        "",
        f"- **Severity:** {finding.severity or 'unknown'}",
        f"- **Confidence:** {finding.confidence or 'unknown'}",
        f"- **CWE:** {finding.cwe_id or 'Not provided'}",
        f"- **OWASP:** {finding.owasp_category or 'Not provided'}",
        f"- **Location:** {_finding_location(finding)}",
        "",
    ]
    _append_markdown_section(lines, "Description", finding.description)
    _append_markdown_section(lines, "Risk", finding.risk)
    _append_markdown_section(lines, "Impact", finding.impact)
    _append_markdown_section(lines, "Recommendation", finding.recommendation)
    _append_code_block(lines, "Vulnerable Code Example", finding.bad_code_example)
    _append_code_block(lines, "Suggested Fix Example", finding.fixed_code_example)
    lines.append(f"_Created automatically by SecureWise from finding `{finding.id}`_")
    return "\n".join(lines)


def _build_pr_body(finding) -> str:
    lines = [
        "## SecureWise Automated Fix",
        "",
        f"- **Severity:** {finding.severity or 'unknown'}",
        f"- **Confidence:** {finding.confidence or 'unknown'}",
        f"- **CWE:** {finding.cwe_id or 'Not provided'}",
        f"- **OWASP:** {finding.owasp_category or 'Not provided'}",
        f"- **Location:** {_finding_location(finding)}",
        "",
    ]
    _append_markdown_section(lines, "Description", finding.description)
    _append_markdown_section(lines, "Recommendation", finding.recommendation)
    lines.append(f"_Created automatically by SecureWise from finding `{finding.id}`_")
    return "\n".join(lines)


def _git_command(repo_path: Path, *args: str) -> None:
    try:
        subprocess.run(
            ["git", "-C", str(repo_path), *args],
            capture_output=True,
            check=True,
            timeout=120,
        )
    except subprocess.CalledProcessError as exc:
        raise GitHubActionError("Git failed while preparing the pull request branch.") from exc
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired) as exc:
        raise GitHubActionError("Git is unavailable or timed out while preparing the pull request branch.") from exc


def _clone_url_for_repository(repository) -> str:
    clone_url = (repository.clone_url or "").strip()
    if clone_url:
        return clone_url
    if repository.repository_url.endswith(".git"):
        return repository.repository_url
    return f"{repository.repository_url}.git"


def _github_api_base(repository) -> str:
    integration = getattr(repository, "integration", None)
    base_url = (getattr(integration, "base_url", "https://github.com") or "https://github.com").rstrip("/")
    if base_url in ("https://github.com", "http://github.com"):
        return "https://api.github.com"
    return f"{base_url}/api/v3"


def _create_scratch_root() -> Path:
    scratch_root = Path(settings.BASE_DIR) / ".securewise-github-actions"
    scratch_root.mkdir(parents=True, exist_ok=True)
    return scratch_root


def _cleanup_scratch_root(root: Path) -> None:
    if root.exists() and not any(root.iterdir()):
        root.rmdir()


def create_github_issue(finding) -> str:
    repository = _resolve_repository_for_finding(finding)
    owner, repo = _parse_github_owner_repo(repository.repository_url)
    api_base = _github_api_base(repository)
    token = _get_write_token(repository)
    try:
        response = _github_api_request(
            "POST",
            f"{api_base}/repos/{owner}/{repo}/issues",
            token,
            body={
                "title": _truncate_title(f"[SecureWise] {finding.title}"),
                "body": _build_issue_body(finding),
            },
        )
    finally:
        del token

    issue_url = str(response.get("html_url", "")).strip()
    if not issue_url:
        raise GitHubActionError("GitHub did not return an issue URL.")
    return issue_url


def create_github_pr(finding) -> str:
    if not finding.file_path or not finding.bad_code_example.strip() or not finding.fixed_code_example.strip():
        raise GitHubActionError(
            "This finding doesn't have enough information (file path + before/after code) to generate an "
            "automatic pull request. Use 'Create Ticket' instead."
        )

    repository = _resolve_repository_for_finding(finding)
    owner, repo = _parse_github_owner_repo(repository.repository_url)
    api_base = _github_api_base(repository)
    token = _get_write_token(repository)
    clone_url = _clone_url_for_repository(repository)
    scratch_root = _create_scratch_root()
    authed_url = None

    try:
        with tempfile.TemporaryDirectory(dir=scratch_root, prefix="sw-gh-action-") as temp_dir:
            repo_path = Path(temp_dir) / "repo"
            clone_source = clone_url
            parsed_clone_url = urlparse(clone_url)
            try:
                if parsed_clone_url.scheme in {"http", "https"}:
                    authed_url = build_authenticated_url(clone_url, token)
                    clone_source = authed_url
                safe_clone(clone_source, repo_path, allowed_root=Path(temp_dir), timeout=120, shallow=False)
            finally:
                if authed_url is not None:
                    del authed_url
                    authed_url = None

            _git_command(repo_path, "config", "user.email", "securewise-bot@guidewisey.local")
            _git_command(repo_path, "config", "user.name", "SecureWise Bot")

            branch_name = f"securewise/fix-{str(finding.id)[:8]}"
            _git_command(repo_path, "checkout", "-b", branch_name)

            try:
                target_file = _resolve_safe_dest(repo_path / finding.file_path, repo_path)
            except ValueError as exc:
                raise GitHubActionError("The finding's file path is invalid.") from exc
            if not target_file.exists() or not target_file.is_file():
                raise GitHubActionError("The finding's file path could not be found in the repository.")

            original_content = target_file.read_text(encoding="utf-8", errors="ignore")
            bad_code = finding.bad_code_example.strip()
            if bad_code not in original_content:
                raise GitHubActionError(
                    "Could not locate the exact vulnerable code in the current version of the file "
                    "(it may have already changed). Please apply the fix manually using the recommendation "
                    "on this finding."
                )

            updated_content = original_content.replace(bad_code, finding.fixed_code_example, 1)
            target_file.write_text(updated_content, encoding="utf-8")

            _git_command(repo_path, "add", str(target_file.relative_to(repo_path)))
            commit_suffix = finding.cwe_id or finding.scanner_type or "finding"
            _git_command(repo_path, "commit", "-m", f"SecureWise: fix {finding.title} ({commit_suffix})")

            push_url = clone_url
            parsed_push_url = urlparse(clone_url)
            try:
                if parsed_push_url.scheme in {"http", "https"}:
                    authed_url = build_authenticated_url(clone_url, token)
                    push_url = authed_url
                _git_command(repo_path, "push", push_url, f"{branch_name}:{branch_name}")
            finally:
                if authed_url is not None:
                    del authed_url
                    authed_url = None

            response = _github_api_request(
                "POST",
                f"{api_base}/repos/{owner}/{repo}/pulls",
                token,
                body={
                    "title": _truncate_title(f"SecureWise: fix {finding.title}"),
                    "head": branch_name,
                    "base": repository.default_branch or "main",
                    "body": _build_pr_body(finding),
                },
            )
    finally:
        del token
        del clone_url
        _cleanup_scratch_root(scratch_root)

    pr_url = str(response.get("html_url", "")).strip()
    if not pr_url:
        raise GitHubActionError("GitHub did not return a pull request URL.")
    return pr_url
