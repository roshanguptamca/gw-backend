from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.securewise.models import (
    SecureWiseApplicationTarget,
    SecureWiseMembership,
    SecureWiseOrganization,
    SecureWiseProject,
    SecureWiseTestingAuthorization,
    SecureWiseWorkerRegistration,
    securewise_encryption_key_fingerprint,
)


@pytest.fixture
def env(django_user_model):
    user = django_user_model.objects.create_user(username="web_admin")
    org = SecureWiseOrganization.objects.create(name="Web", slug="web", owner=user)
    SecureWiseMembership.objects.create(organization=org, user=user, role="owner")
    project = SecureWiseProject.objects.create(organization=org, name="P", slug="p", created_by=user)
    return user, org, project


def _worker(capabilities, profile="standard"):
    return SecureWiseWorkerRegistration.objects.create(
        worker_id="w1",
        capabilities=capabilities,
        metrics={"worker_profile": profile, "encryption_key_fingerprint": securewise_encryption_key_fingerprint()},
        status="online",
        last_seen_at=timezone.now(),
    )


def _authorize(env, *, verified=True, methods=("passive_http",)):
    user, org, project = env
    target = SecureWiseApplicationTarget.objects.create(
        organization=org,
        project=project,
        hostname="guidewisey.com",
        verified_at=timezone.now() if verified else None,
        created_by=user,
    )
    now = timezone.now()
    SecureWiseTestingAuthorization.objects.create(
        organization=org,
        target=target,
        authorized_hosts=["guidewisey.com"],
        allowed_ports=[443],
        allowed_paths=["/"],
        approved_scan_methods=list(methods),
        testing_environment="production",
        starts_at=now - timedelta(hours=1),
        expires_at=now + timedelta(hours=1),
        approved_by=user,
    )


def _status(user):
    client = APIClient()
    client.force_authenticate(user)
    return client.get("/api/securewise/scans/worker-status/").json()["website_readiness"]


def _codes(result):
    return {b["code"] for b in result["blockers"]}


def test_no_worker_and_no_target_report_exact_blockers(env):
    result = _status(env[0])
    assert result["ready"] is False
    assert {"no_worker", "no_verified_target"} <= _codes(result)


def test_lightweight_worker_is_not_website_capable(env):
    _worker(["sast", "sca", "secrets", "iac", "api"], profile="lightweight")
    _authorize(env)
    result = _status(env[0])
    assert result["ready"] is False
    assert _codes(result) == {"worker_profile"}


def test_dast_worker_without_egress_proof_is_blocked(env):
    _worker(["dast", "docker_daemon"])
    _authorize(env)
    assert "egress_unproven" in _codes(_status(env[0]))


def test_unverified_target_or_missing_method_blocks(env):
    _worker(["dast", "url_egress_restricted"])
    _authorize(env, verified=False)
    assert "no_verified_target" in _codes(_status(env[0]))


def test_wrong_scan_method_blocks(env):
    _worker(["dast", "url_egress_restricted"])
    _authorize(env, methods=("something_else",))
    assert _codes(_status(env[0])) == {"no_active_authorization"}


def test_ready_only_with_worker_egress_verified_target_and_authorization(env):
    _worker(["dast", "url_egress_restricted"])
    _authorize(env)
    result = _status(env[0])
    assert result == {"ready": True, "worker_ready": True, "blockers": []}


@pytest.mark.django_db
def test_control_plane_uses_registered_worker_egress_not_local_proof(monkeypatch):
    from apps.securewise.services import url_security

    monkeypatch.setattr(url_security, "url_egress_enforced", lambda: False)
    assert url_security.worker_has_url_egress() is False  # no registered worker
    _worker(["dast", "url_egress_restricted"])
    assert url_security.worker_has_url_egress() is True
    # The worker process itself still requires its own fresh proof.
    assert url_security.worker_has_url_egress("w1") is False


@pytest.mark.django_db
def test_control_plane_ignores_workers_without_egress_capability(monkeypatch):
    from apps.securewise.services import url_security

    monkeypatch.setattr(url_security, "url_egress_enforced", lambda: False)
    _worker(["dast"])
    assert url_security.worker_has_url_egress() is False


def test_passive_website_readiness_does_not_require_credential_key_match(env):
    SecureWiseWorkerRegistration.objects.create(
        worker_id="w-other-key",
        capabilities=["dast", "url_egress_restricted"],
        metrics={"worker_profile": "website_passive", "encryption_key_fingerprint": "0" * 64},
        status="online",
        last_seen_at=timezone.now(),
    )
    _authorize(env)
    result = _status(env[0])
    assert result["ready"] is True
    assert result["worker_ready"] is True
    assert "encryption_key" not in _codes(result)


def test_website_readiness_only_counts_the_users_own_organizations(env, django_user_model):
    _worker(["dast", "url_egress_restricted"])
    _authorize(env)
    outsider = django_user_model.objects.create_user(username="outsider")
    other = SecureWiseOrganization.objects.create(name="Other", slug="other", owner=outsider)
    SecureWiseMembership.objects.create(organization=other, user=outsider, role="owner")
    result = _status(outsider)
    assert "no_verified_target" in _codes(result)
    assert result["ready"] is False
