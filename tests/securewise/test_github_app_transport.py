"""GitHub transport boundaries tested without network access or database setup."""

import io
from unittest.mock import Mock, call

import jwt
import pytest
import requests

from apps.securewise.services import github_app


@pytest.fixture(autouse=True)
def block_network(monkeypatch):
    monkeypatch.setattr(github_app.requests, "request", Mock(side_effect=AssertionError("Unexpected network request")))
    monkeypatch.setattr(github_app.requests, "get", Mock(side_effect=AssertionError("Unexpected archive request")))


def test_app_jwt_uses_short_lived_claims_and_normalizes_key(monkeypatch):
    monkeypatch.setenv("SECUREWISE_GITHUB_APP_ID", "123")
    monkeypatch.setenv("SECUREWISE_GITHUB_APP_PRIVATE_KEY", "synthetic\\nkey")
    monkeypatch.setattr(github_app.time, "time", lambda: 1000)
    encode = Mock(return_value="signed-test-token")
    monkeypatch.setattr(github_app.jwt, "encode", encode)

    assert github_app._app_jwt() == "signed-test-token"
    encode.assert_called_once_with({"iat": 940, "exp": 1540, "iss": "123"}, "synthetic\nkey", algorithm="RS256")


def test_app_jwt_rejects_missing_credentials(monkeypatch):
    monkeypatch.delenv("SECUREWISE_GITHUB_APP_ID", raising=False)
    monkeypatch.delenv("SECUREWISE_GITHUB_APP_PRIVATE_KEY", raising=False)
    with pytest.raises(github_app.GitHubAppError, match="credentials are not configured"):
        github_app._app_jwt()


@pytest.mark.parametrize("error", [jwt.PyJWTError("bad key"), ValueError("bad key"), TypeError("bad key")])
def test_app_jwt_sanitizes_signing_errors(monkeypatch, error):
    monkeypatch.setenv("SECUREWISE_GITHUB_APP_ID", "123")
    monkeypatch.setenv("SECUREWISE_GITHUB_APP_PRIVATE_KEY", "synthetic-key")
    monkeypatch.setattr(github_app.jwt, "encode", Mock(side_effect=error))
    with pytest.raises(github_app.GitHubAppError, match="private key could not be loaded"):
        github_app._app_jwt()


@pytest.mark.parametrize("slug", ["", "../other", "x" * 40])
def test_app_slug_rejects_invalid_configuration(monkeypatch, slug):
    monkeypatch.setenv("SECUREWISE_GITHUB_APP_SLUG", slug)
    with pytest.raises(github_app.GitHubAppError, match="slug is not configured"):
        github_app.app_slug()


@pytest.mark.parametrize("path", ["https://example.test/repos", "//example.test/repos", "repos"])
def test_request_rejects_non_api_paths(path):
    with pytest.raises(github_app.GitHubAppError, match="Invalid GitHub API path"):
        github_app._request("GET", path)
    github_app.requests.request.assert_not_called()


def test_request_returns_json_without_following_redirects(monkeypatch):
    response = Mock(is_redirect=False, status_code=200)
    response.json.return_value = {"id": 123}
    request = Mock(return_value=response)
    monkeypatch.setattr(github_app.requests, "request", request)

    assert github_app._request("GET", "/app/installations/123", app_token="synthetic-token") == {"id": 123}
    args, kwargs = request.call_args
    assert args == ("GET", "https://api.github.com/app/installations/123")
    assert kwargs["allow_redirects"] is False
    assert kwargs["timeout"] == (5, 20)
    assert "Authorization" in kwargs["headers"]


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (Mock(is_redirect=True, status_code=302), "unexpectedly redirected"),
        (Mock(is_redirect=False, status_code=401), "HTTP 401"),
        (Mock(is_redirect=False, status_code=503), "HTTP 503"),
    ],
)
def test_request_rejects_redirects_and_http_errors(monkeypatch, response, message):
    monkeypatch.setattr(github_app.requests, "request", Mock(return_value=response))
    with pytest.raises(github_app.GitHubAppError, match=message):
        github_app._request("GET", "/app")
    response.json.assert_not_called()


@pytest.mark.parametrize("payload", [[], "invalid", None])
def test_request_rejects_non_object_json(monkeypatch, payload):
    response = Mock(is_redirect=False, status_code=200)
    response.json.return_value = payload
    monkeypatch.setattr(github_app.requests, "request", Mock(return_value=response))
    with pytest.raises(github_app.GitHubAppError, match="invalid response"):
        github_app._request("GET", "/app")


def test_request_wraps_connection_and_json_errors(monkeypatch):
    monkeypatch.setattr(github_app.requests, "request", Mock(side_effect=requests.Timeout("offline")))
    with pytest.raises(github_app.GitHubAppError, match="Could not reach"):
        github_app._request("GET", "/app")

    response = Mock(is_redirect=False, status_code=200)
    response.json.side_effect = ValueError("invalid JSON")
    monkeypatch.setattr(github_app.requests, "request", Mock(return_value=response))
    with pytest.raises(github_app.GitHubAppError, match="invalid response"):
        github_app._request("GET", "/app")


@pytest.mark.parametrize("token", [None, "", 42])
def test_create_installation_token_rejects_missing_or_invalid_token(monkeypatch, token):
    monkeypatch.setattr(github_app, "_app_jwt", lambda: "synthetic-app-token")
    monkeypatch.setattr(github_app, "_request", Mock(return_value={"token": token}))
    with pytest.raises(github_app.GitHubAppError, match="did not issue"):
        github_app.create_installation_token(123)


@pytest.fixture
def installation_token(monkeypatch):
    monkeypatch.setattr(github_app, "create_installation_token", Mock(return_value="synthetic-installation-token"))


def test_repository_listing_paginates_with_installation_scope(monkeypatch, installation_token):
    first_page = [{"id": number} for number in range(100)]
    request = Mock(
        side_effect=[
            {"repositories": first_page, "total_count": 101},
            {"repositories": [{"id": 100}], "total_count": 101},
        ]
    )
    monkeypatch.setattr(github_app, "_request", request)

    assert github_app.list_installation_repositories(123) == first_page + [{"id": 100}]
    assert request.call_args_list == [
        call(
            "GET",
            f"/installation/repositories?per_page=100&page={page}",
            installation_token="synthetic-installation-token",
        )
        for page in (1, 2)
    ]


@pytest.mark.parametrize(
    "payload",
    [
        {"repositories": {}},
        {"repositories": ["not-a-repository"]},
        {"repositories": [], "total_count": "invalid"},
    ],
)
def test_repository_listing_rejects_malformed_results(monkeypatch, installation_token, payload):
    monkeypatch.setattr(github_app, "_request", Mock(return_value=payload))
    with pytest.raises(github_app.GitHubAppError, match="invalid repository"):
        github_app.list_installation_repositories(123)


def test_commit_lookup_encodes_ref_and_normalizes_sha(monkeypatch, installation_token):
    request = Mock(return_value={"sha": "A" * 40})
    monkeypatch.setattr(github_app, "_request", request)
    assert github_app.get_commit_sha(123, "owner/repo", "feature/name") == "a" * 40
    request.assert_called_once_with(
        "GET", "/repos/owner/repo/commits/feature%2Fname", installation_token="synthetic-installation-token"
    )


@pytest.mark.parametrize("sha", ["", "abc", "g" * 40])
def test_commit_lookup_rejects_invalid_sha(monkeypatch, installation_token, sha):
    monkeypatch.setattr(github_app, "_request", Mock(return_value={"sha": sha}))
    with pytest.raises(github_app.GitHubAppError, match="invalid commit identifier"):
        github_app.get_commit_sha(123, "owner/repo", "main")


def test_archive_download_does_not_forward_credentials_to_codeload(monkeypatch, installation_token):
    redirect = Mock(status_code=302, headers={"Location": "https://codeload.github.com/owner/repo/zip/abc"})
    archive = Mock(status_code=200)
    archive.iter_content.return_value = [b"archive-", b"content"]
    get = Mock(side_effect=[redirect, archive])
    monkeypatch.setattr(github_app.requests, "get", get)
    output = io.BytesIO()

    github_app.download_archive(123, "owner/repo", "a" * 40, output)

    assert output.getvalue() == b"archive-content"
    first, second = [entry.kwargs for entry in get.call_args_list]
    assert "Authorization" in first["headers"]
    assert "Authorization" not in second["headers"]
    assert first["allow_redirects"] is False and second["allow_redirects"] is False
    assert first["stream"] is True and second["stream"] is True
    redirect.close.assert_called()
    archive.close.assert_called_once()


@pytest.mark.parametrize(
    "location",
    [
        "http://codeload.github.com/owner/repo",
        "https://example.test/owner/repo",
        "https://codeload.github.com:8443/owner/repo",
        "https://user:password@codeload.github.com/owner/repo",
        "https://codeload.github.com/owner/repo#fragment",
    ],
)
def test_archive_download_rejects_untrusted_redirects(monkeypatch, installation_token, location):
    response = Mock(status_code=302, headers={"Location": location})
    get = Mock(return_value=response)
    monkeypatch.setattr(github_app.requests, "get", get)
    with pytest.raises(github_app.GitHubAppError, match="redirect destination is not permitted"):
        github_app.download_archive(123, "owner/repo", "a" * 40, io.BytesIO())
    get.assert_called_once()
    response.close.assert_called_once()


def test_archive_download_closes_response_after_http_error(monkeypatch, installation_token):
    response = Mock(status_code=403)
    monkeypatch.setattr(github_app.requests, "get", Mock(return_value=response))
    with pytest.raises(github_app.GitHubAppError, match="archive API returned HTTP 403"):
        github_app.download_archive(123, "owner/repo", "a" * 40, io.BytesIO())
    response.close.assert_called_once()


@pytest.mark.parametrize("failure_stage", ["api", "archive"])
def test_archive_download_wraps_connection_errors(monkeypatch, installation_token, failure_stage):
    redirect = Mock(status_code=302, headers={"Location": "https://codeload.github.com/owner/repo"})
    effects = [requests.Timeout("offline")] if failure_stage == "api" else [redirect, requests.Timeout("offline")]
    monkeypatch.setattr(github_app.requests, "get", Mock(side_effect=effects))
    with pytest.raises(github_app.GitHubAppError, match="Could not"):
        github_app.download_archive(123, "owner/repo", "a" * 40, io.BytesIO())
    if failure_stage == "archive":
        redirect.close.assert_called()


@pytest.mark.parametrize("status", [302, 404])
def test_archive_download_rejects_codeload_errors(monkeypatch, installation_token, status):
    redirect = Mock(status_code=302, headers={"Location": "https://codeload.github.com/owner/repo"})
    archive = Mock(status_code=status)
    monkeypatch.setattr(github_app.requests, "get", Mock(side_effect=[redirect, archive]))
    with pytest.raises(github_app.GitHubAppError, match=f"archive host returned HTTP {status}"):
        github_app.download_archive(123, "owner/repo", "a" * 40, io.BytesIO())
    archive.close.assert_called_once()


def test_archive_download_enforces_size_limit_before_writing(monkeypatch, installation_token):
    redirect = Mock(status_code=302, headers={"Location": "https://codeload.github.com/owner/repo"})
    archive = Mock(status_code=200)
    oversized_chunk = Mock()
    oversized_chunk.__len__ = Mock(return_value=1024**3 + 1)
    archive.iter_content.return_value = [oversized_chunk]
    monkeypatch.setattr(github_app.requests, "get", Mock(side_effect=[redirect, archive]))
    output = Mock()
    with pytest.raises(github_app.GitHubAppError, match="1 GiB download limit"):
        github_app.download_archive(123, "owner/repo", "a" * 40, output)
    output.write.assert_not_called()
    archive.close.assert_called_once()
