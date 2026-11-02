import ssl
import urllib.error
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock

from django.utils import timezone

import pytest
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.securewise import application_views, views


@pytest.fixture
def api_request():
    return SimpleNamespace(user=SimpleNamespace(id=1), data={}, query_params={})


@pytest.fixture
def organization():
    return SimpleNamespace(id="organization-a", owner_id=1)


@pytest.mark.parametrize("role", [None, "auditor"])
@pytest.mark.parametrize("view_class", [views.IntegrationViewSet, views.GitIntegrationViewSet])
@pytest.mark.parametrize("operation", ["create", "update", "destroy"])
def test_integration_mutations_require_admin_membership(
    monkeypatch, api_request, organization, role, view_class, operation
):
    monkeypatch.setattr(views, "_membership", lambda *args: None if role is None else SimpleNamespace(role=role))
    view = view_class()
    view.request = api_request
    instance = Mock(organization=organization, organization_id=organization.id)
    serializer = Mock(instance=instance, validated_data={"organization": organization})
    argument = instance if operation == "destroy" else serializer
    with pytest.raises(PermissionDenied):
        getattr(view, f"perform_{operation}")(argument)
    serializer.save.assert_not_called()
    instance.delete.assert_not_called()


@pytest.mark.parametrize("view_class", [views.IntegrationViewSet, views.GitIntegrationViewSet])
@pytest.mark.parametrize("operation", ["create", "update", "destroy"])
def test_admin_integration_mutations_save_and_audit(monkeypatch, api_request, organization, view_class, operation):
    monkeypatch.setattr(views, "_membership", lambda *args: SimpleNamespace(role="admin"))
    audit = Mock()
    monkeypatch.setattr(views, "_audit", audit)
    view = view_class()
    view.request = api_request
    instance = Mock(organization=organization, organization_id=organization.id)
    serializer = Mock(instance=instance, validated_data={"organization": organization})
    serializer.save.return_value = instance
    getattr(view, f"perform_{operation}")(instance if operation == "destroy" else serializer)
    if operation == "destroy":
        instance.delete.assert_called_once()
    else:
        serializer.save.assert_called_once()
    if view_class is views.GitIntegrationViewSet:
        audit.assert_called_once()


@pytest.mark.parametrize("view_class", [views.IntegrationViewSet, views.RepositoryViewSet])
def test_objects_cannot_be_moved_between_organizations(monkeypatch, api_request, organization, view_class):
    monkeypatch.setattr(views, "_membership", lambda *args: SimpleNamespace(role="admin"))
    view = view_class()
    view.request = api_request
    instance = Mock(organization=organization, organization_id=organization.id)
    serializer = Mock(instance=instance, validated_data={"organization": SimpleNamespace(id="other-organization")})
    with pytest.raises(ValidationError):
        view.perform_update(serializer)
    serializer.save.assert_not_called()


@pytest.mark.parametrize(
    ("provider", "base", "endpoint"),
    [
        ("github", "https://github.com", "https://api.github.com/user"),
        ("github_enterprise", "https://git.example.test", "https://git.example.test/api/v3/user"),
        ("gitlab", "https://gitlab.com", "https://gitlab.com/api/v4/user"),
        ("custom", "https://git.example.test", "https://git.example.test"),
    ],
)
def test_git_connectivity_tests_use_provider_endpoint_and_mark_success(
    monkeypatch, api_request, provider, base, endpoint
):
    monkeypatch.setattr(views, "_membership", lambda *args: SimpleNamespace(role="admin"))
    integration = Mock(provider=provider, base_url=base)
    integration.get_token.return_value = "synthetic-token"
    response = Mock(status=200)
    opened = Mock()
    opened.__enter__ = Mock(return_value=response)
    opened.__exit__ = Mock(return_value=False)
    urlopen = Mock(return_value=opened)
    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    view = views.GitIntegrationViewSet()
    view.get_object = lambda: integration
    result = view.test(api_request)
    assert result.status_code == 200 and result.data["status"] == "active"
    assert urlopen.call_args.args[0].full_url == endpoint
    assert integration.status == "active"
    integration.save.assert_called_once_with(update_fields=["last_used_at", "status"])


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (urllib.error.HTTPError("https://example.test", 401, "denied", {}, None), "Authentication failed"),
        (urllib.error.HTTPError("https://example.test", 404, "missing", {}, None), "API endpoint not found"),
        (urllib.error.HTTPError("https://example.test", 503, "unavailable", {}, None), "HTTP 503"),
        (urllib.error.URLError(ssl.SSLCertVerificationError("CERTIFICATE_VERIFY_FAILED")), "SSL certificate"),
        (urllib.error.URLError("offline"), "Could not reach"),
        (RuntimeError("unexpected"), "Unexpected error"),
    ],
)
def test_git_connectivity_errors_are_explicit_and_never_report_success(monkeypatch, api_request, error, message):
    monkeypatch.setattr(views, "_membership", lambda *args: SimpleNamespace(role="admin"))
    integration = Mock(provider="github", base_url="https://github.com")
    integration.get_token.return_value = "synthetic-token"
    monkeypatch.setattr("urllib.request.urlopen", Mock(side_effect=error))
    view = views.GitIntegrationViewSet()
    view.get_object = lambda: integration
    result = view.test(api_request)
    assert result.status_code == 400
    assert message in result.data["detail"]
    assert "synthetic-token" not in result.data["detail"]
    assert integration.status == "error"
    integration.save.assert_called_once_with(update_fields=["status"])


@pytest.mark.parametrize("role", [None, "auditor"])
def test_membership_deletion_requires_admin_and_does_not_remove_records(monkeypatch, api_request, organization, role):
    monkeypatch.setattr(views, "_membership", lambda *args: None if role is None else SimpleNamespace(role=role))
    view = views.MembershipViewSet()
    view.request = api_request
    member = Mock(organization=organization, user_id=2)
    with pytest.raises(PermissionDenied):
        view.perform_destroy(member)
    member.delete.assert_not_called()


@pytest.mark.parametrize("operation", ["update", "destroy"])
def test_organization_owner_membership_cannot_be_changed(monkeypatch, api_request, organization, operation):
    monkeypatch.setattr(views, "_membership", lambda *args: SimpleNamespace(role="admin"))
    view = views.MembershipViewSet()
    view.request = api_request
    instance = Mock(organization=organization, user_id=organization.owner_id)
    serializer = Mock(instance=instance)
    with pytest.raises(PermissionDenied, match="owner"):
        getattr(view, f"perform_{operation}")(instance if operation == "destroy" else serializer)
    instance.delete.assert_not_called()
    serializer.save.assert_not_called()


@pytest.mark.parametrize("changed", ["organization", "user", "role"])
def test_admin_cannot_reassign_membership_identity_or_promote_to_owner(monkeypatch, api_request, organization, changed):
    monkeypatch.setattr(views, "_membership", lambda *args: SimpleNamespace(role="admin"))
    api_request.user.id = 3
    member = Mock(
        organization=organization,
        organization_id=organization.id,
        user=SimpleNamespace(id=2),
        user_id=2,
    )
    updates = {"role": "owner"} if changed == "role" else {changed: SimpleNamespace(id="other")}
    serializer = Mock(instance=member, validated_data=updates)
    view = views.MembershipViewSet()
    view.request = api_request
    with pytest.raises(PermissionDenied if changed == "role" else ValidationError):
        view.perform_update(serializer)
    serializer.save.assert_not_called()


@pytest.mark.parametrize("operation", ["update", "destroy"])
def test_admin_can_manage_nonowner_membership(monkeypatch, api_request, organization, operation):
    monkeypatch.setattr(views, "_membership", lambda *args: SimpleNamespace(role="admin"))
    member = Mock(
        organization=organization,
        organization_id=organization.id,
        user=SimpleNamespace(id=2),
        user_id=2,
    )
    serializer = Mock(instance=member, validated_data={"role": "viewer"})
    view = views.MembershipViewSet()
    view.request = api_request
    getattr(view, f"perform_{operation}")(member if operation == "destroy" else serializer)
    if operation == "destroy":
        member.delete.assert_called_once()
    else:
        serializer.save.assert_called_once()


@pytest.mark.parametrize("paths", ["/*", [], ["/api?token=synthetic"], ["/api#fragment"], ["/api/*"], [None]])
def test_authorization_scope_rejects_nonliteral_paths(paths):
    with pytest.raises(ValueError):
        application_views._scope_paths(paths, ["/"])


def test_authorization_scope_normalizes_and_deduplicates_literal_prefixes():
    assert application_views._scope_paths(["/api/", "/api", "/"], []) == ["/api", "/"]
    assert application_views._scope_paths([], [], allow_empty=True) == []


@pytest.mark.parametrize(
    ("data", "verified", "message"),
    [
        ({}, False, "Verify current ownership"),
        ({}, True, "Explicit testing authorization"),
        ({"explicit_authorization": True}, True, "testing environment"),
        ({"explicit_authorization": True, "testing_environment": "test", "expires_at": "bad"}, True, "ISO-8601"),
        (
            {"explicit_authorization": True, "testing_environment": "test", "expires_at": "2000-01-01T00:00:00+00:00"},
            True,
            "next 30 days",
        ),
    ],
)
def test_authorization_requires_verified_ownership_explicit_consent_and_bounded_expiry(
    api_request, data, verified, message
):
    target = SimpleNamespace(verified_at="verified" if verified else None, ownership_revoked_at=None)
    api_request.data = data
    result = application_views.ApplicationTargetActionView()._authorize(api_request, target)
    assert result.status_code == 400
    assert message in result.data["detail"]


@pytest.mark.parametrize(
    ("allowed", "excluded"),
    [(["/api/*"], []), (["/different"], []), (["/api"], ["/api"])],
)
def test_authorization_cannot_expand_or_exclude_registered_target_path(api_request, allowed, excluded):
    target = SimpleNamespace(verified_at=timezone.now(), ownership_revoked_at=None, base_path="/api")
    api_request.data = {
        "explicit_authorization": True,
        "testing_environment": "test",
        "expires_at": (timezone.now() + timedelta(hours=1)).isoformat(),
        "allowed_paths": allowed,
        "excluded_paths": excluded,
    }
    result = application_views.ApplicationTargetActionView()._authorize(api_request, target)
    assert result.status_code == 400
    assert "scope" in result.data["detail"].lower() or "literal" in result.data["detail"].lower()


def test_ownership_verification_does_not_accept_unknown_challenge_methods():
    with pytest.raises(ValueError, match="dns_txt or https_well_known"):
        application_views._create_challenge(Mock(), "http-unrestricted")
