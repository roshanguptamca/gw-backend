from __future__ import annotations

import hashlib
from datetime import timedelta
from pathlib import Path
import shutil

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.securewise.models import (
    SecureWiseApplicationTarget,
    SecureWiseAuditLog,
    SecureWiseMembership,
    SecureWiseOrganization,
    SecureWiseOwnershipChallenge,
    SecureWiseProject,
    SecureWiseScan,
    SecureWiseTestingAuthorization,
    SecureWiseWorkerRegistration,
)
from apps.securewise.scanners.dast import DastScanner
from apps.securewise.scanners.sast import SastScanner
from apps.securewise.services.scanner import ScannerRunner
from apps.securewise.services import url_security
from apps.securewise.services.worker import claim_next_job

pytestmark = pytest.mark.django_db


@pytest.fixture
def target_workspace(django_user_model):
    owner = django_user_model.objects.create_user(username="target_owner")
    outsider = django_user_model.objects.create_user(username="target_outsider")
    organization = SecureWiseOrganization.objects.create(name="Target Org", slug="target-org", owner=owner)
    SecureWiseMembership.objects.create(organization=organization, user=owner, role="owner")
    project = SecureWiseProject.objects.create(
        organization=organization,
        name="Web App",
        slug="web-app",
        created_by=owner,
    )
    client = APIClient()
    client.force_authenticate(user=owner)
    return owner, outsider, organization, project, client


def register_and_verify(client, project, monkeypatch, method="dns_txt"):
    monkeypatch.setattr(url_security, "resolve_public_addresses", lambda host: ("203.0.113.10",))
    monkeypatch.setattr(url_security, "verify_dns_txt", lambda host, digest: True)
    monkeypatch.setattr(url_security, "verify_https_well_known", lambda host, digest, port=443: True)
    response = client.post(
        "/api/securewise/application-targets/",
        {"project": str(project.id), "url": "https://app.customer.example/shop", "verification_method": method},
        format="json",
    )
    assert response.status_code == 201
    target_id = response.json()["target"]["id"]
    challenge_id = response.json()["challenge"]["id"]
    verified = client.post(
        f"/api/securewise/application-targets/{target_id}/verify/",
        {"challenge": challenge_id},
        format="json",
    )
    assert verified.status_code == 200
    assert verified.json()["verified"] is True
    return target_id


def authorize_target(client, target_id, *, expires_at=None, allowed_paths=None):
    response = client.post(
        f"/api/securewise/application-targets/{target_id}/authorize/",
        {
            "explicit_authorization": True,
            "testing_environment": "staging",
            "expires_at": (expires_at or timezone.now() + timedelta(days=2)).isoformat(),
            "allowed_paths": allowed_paths or ["/shop"],
            "excluded_paths": ["/shop/admin"],
        },
        format="json",
    )
    return response


def test_target_registration_verification_and_expiry(target_workspace, monkeypatch):
    _, _, _, project, client = target_workspace
    target_id = register_and_verify(client, project, monkeypatch)
    authorization_response = authorize_target(client, target_id)
    assert authorization_response.status_code == 201
    authorization_id = authorization_response.json()["id"]
    authorization = SecureWiseTestingAuthorization.objects.get(id=authorization_id)
    assert authorization.approved_by_id == client.handler._force_user.id
    assert authorization.authorized_hosts == ["app.customer.example"]
    assert authorization.allowed_ports == [443]
    assert authorization.approved_scan_methods == ["passive_http"]
    assert url_security.authorization_is_active(authorization)

    authorization.expires_at = timezone.now() - timedelta(seconds=1)
    authorization.save(update_fields=["expires_at"])
    assert not url_security.authorization_is_active(authorization)


def test_authorization_requires_explicit_approval_and_verified_ownership(target_workspace, monkeypatch):
    _, _, _, project, client = target_workspace
    response = client.post(
        "/api/securewise/application-targets/",
        {"project": str(project.id), "url": "https://app.customer.example/"},
        format="json",
    )
    target_id = response.json()["target"]["id"]
    assert authorize_target(client, target_id).status_code == 400

    monkeypatch.setattr(url_security, "resolve_public_addresses", lambda host: ("203.0.113.10",))
    monkeypatch.setattr(url_security, "verify_dns_txt", lambda host, digest: True)
    client.post(
        f"/api/securewise/application-targets/{target_id}/verify/",
        {"challenge": response.json()["challenge"]["id"]},
        format="json",
    )
    missing_explicit = client.post(
        f"/api/securewise/application-targets/{target_id}/authorize/",
        {
            "testing_environment": "staging",
            "expires_at": (timezone.now() + timedelta(days=1)).isoformat(),
        },
        format="json",
    )
    assert missing_explicit.status_code == 400


def test_cross_tenant_target_and_authorization_are_hidden(target_workspace, django_user_model, monkeypatch):
    _, outsider, _, project, client = target_workspace
    target_id = register_and_verify(client, project, monkeypatch)
    authorization = authorize_target(client, target_id)
    target = SecureWiseApplicationTarget.objects.get(id=target_id)

    other_org = SecureWiseOrganization.objects.create(name="Other", slug="target-other", owner=outsider)
    other_project = SecureWiseProject.objects.create(
        organization=other_org,
        name="Other",
        slug="other",
        created_by=outsider,
    )
    SecureWiseMembership.objects.create(organization=other_org, user=outsider, role="owner")
    other_target = SecureWiseApplicationTarget.objects.create(
        organization=other_org,
        project=other_project,
        hostname="other.example",
        verified_at=timezone.now(),
    )
    outsider_client = APIClient()
    outsider_client.force_authenticate(user=outsider)
    assert (
        outsider_client.post(
            f"/api/securewise/application-targets/{target.id}/revoke-ownership/",
            {},
            format="json",
        ).status_code
        == 404
    )
    assert (
        outsider_client.post(
            f"/api/securewise/testing-authorizations/{authorization.json()['id']}/revoke/",
            {},
            format="json",
        ).status_code
        == 404
    )
    listed_targets = outsider_client.get("/api/securewise/application-targets/").json()
    assert [item["id"] for item in listed_targets] == [str(other_target.id)]
    assert other_target.organization_id == other_org.id


def test_ownership_challenge_expiry_and_revocation_disable_authorization(target_workspace, monkeypatch):
    _, _, _, project, client = target_workspace
    target_id = register_and_verify(client, project, monkeypatch)
    authorization_response = authorize_target(client, target_id)
    authorization_id = authorization_response.json()["id"]
    target = SecureWiseApplicationTarget.objects.get(id=target_id)
    authorization = SecureWiseTestingAuthorization.objects.get(id=authorization_id)
    assert url_security.authorization_is_active(authorization)

    response = client.post(
        f"/api/securewise/application-targets/{target_id}/revoke-ownership/",
        {},
        format="json",
    )
    assert response.json()["verified"] is False
    authorization.refresh_from_db()
    assert authorization.revoked_at is not None
    assert not url_security.authorization_is_active(authorization)


def test_https_well_known_challenge_expiry_and_single_use(target_workspace, monkeypatch):
    _, _, _, project, client = target_workspace
    monkeypatch.setattr(url_security, "resolve_public_addresses", lambda host: ("203.0.113.10",))
    verification_calls = []

    def verify_https(host, digest, *, port=443):
        verification_calls.append((host, digest, port))
        return True

    monkeypatch.setattr(url_security, "verify_https_well_known", verify_https)
    response = client.post(
        "/api/securewise/application-targets/",
        {
            "project": str(project.id),
            "url": "https://app.customer.example:8443/shop",
            "verification_method": "https_well_known",
        },
        format="json",
    )
    assert response.status_code == 201
    challenge = response.json()["challenge"]
    assert challenge["https_path"] == "/.well-known/securewise-verification.txt"
    audit_event = SecureWiseAuditLog.objects.get(event="application_target_challenge_created")
    assert challenge["token"] not in str(audit_event.detail)
    target_id = response.json()["target"]["id"]
    verified = client.post(
        f"/api/securewise/application-targets/{target_id}/verify/",
        {"challenge": challenge["id"]},
        format="json",
    )
    assert verified.status_code == 200
    assert verification_calls == [
        ("app.customer.example", hashlib.sha256(challenge["token"].encode()).hexdigest(), 8443)
    ]

    replay = client.post(
        f"/api/securewise/application-targets/{target_id}/verify/",
        {"challenge": challenge["id"]},
        format="json",
    )
    assert replay.status_code == 400

    expired_challenge = SecureWiseOwnershipChallenge.objects.create(
        target=SecureWiseApplicationTarget.objects.get(id=target_id),
        method="https_well_known",
        challenge_digest="expired-challenge-digest",
        expires_at=timezone.now() - timedelta(seconds=1),
    )
    expired = client.post(
        f"/api/securewise/application-targets/{target_id}/verify/",
        {"challenge": str(expired_challenge.id)},
        format="json",
    )
    assert expired.status_code == 400


def test_scan_creation_requires_scope_and_worker_capability(target_workspace, monkeypatch):
    _, _, organization, project, client = target_workspace
    target_id = register_and_verify(client, project, monkeypatch)
    authorization_response = authorize_target(client, target_id)
    authorization_id = authorization_response.json()["id"]
    target = SecureWiseApplicationTarget.objects.get(id=target_id)

    unauthorized = client.post(
        "/api/securewise/scans/",
        {
            "project": str(project.id),
            "scan_type": "dast",
            "target_url": f"https://{target.hostname}/outside",
        },
        format="json",
    )
    assert unauthorized.status_code == 400
    excluded_path = client.post(
        "/api/securewise/scans/",
        {
            "project": str(project.id),
            "scan_type": "dast",
            "target_url": f"https://{target.hostname}/shop/admin",
            "testing_authorization": authorization_id,
        },
        format="json",
    )
    assert excluded_path.status_code == 400

    scan_response = client.post(
        "/api/securewise/scans/",
        {
            "project": str(project.id),
            "scan_type": "dast",
            "target_url": f"https://{target.hostname}/shop",
            "testing_authorization": authorization_id,
        },
        format="json",
    )
    assert scan_response.status_code == 201, scan_response.content
    scan = SecureWiseScan.objects.get(id=scan_response.json()["id"])
    assert scan.organization_id == organization.id
    missing_project = client.post(
        "/api/securewise/scans/",
        {
            "scan_type": "dast",
            "target_url": f"https://{target.hostname}/shop",
            "testing_authorization": authorization_id,
        },
        format="json",
    )
    assert missing_project.status_code == 400

    monkeypatch.setenv("SECUREWISE_URL_EGRESS_ENFORCED", "true")
    monkeypatch.setattr(url_security, "url_egress_enforced", lambda: True)
    SecureWiseWorkerRegistration.objects.create(
        worker_id="url-worker",
        capabilities=["dast", "url_egress_restricted"],
        status="online",
        last_seen_at=timezone.now(),
        metrics={"architecture": "amd64"},
    )
    monkeypatch.setattr(url_security, "resolve_public_addresses", lambda host: ("203.0.113.10",))
    queued = client.post(f"/api/securewise/scans/{scan.id}/start/", {}, format="json")
    assert queued.status_code == 200
    assert queued.json()["status"] == "queued"


def test_scan_start_fails_closed_without_network_egress_capability(target_workspace, monkeypatch):
    _, _, _, project, client = target_workspace
    target_id = register_and_verify(client, project, monkeypatch)
    authorization_id = authorize_target(client, target_id).json()["id"]
    target = SecureWiseApplicationTarget.objects.get(id=target_id)
    scan = SecureWiseScan.objects.create(
        organization=target.organization,
        project=project,
        testing_authorization_id=authorization_id,
        scan_type="dast",
        target_url=f"https://{target.hostname}/shop",
        triggered_by=project.created_by,
    )
    result = client.post(f"/api/securewise/scans/{scan.id}/start/", {}, format="json")
    assert result.status_code == 409
    assert result.json()["status"] == "blocked"
    scan.refresh_from_db()
    assert scan.status == "pending"


def test_url_egress_env_flag_alone_does_not_enable_network_access(monkeypatch, tmp_path):
    monkeypatch.setenv("SECUREWISE_URL_EGRESS_ENFORCED", "true")
    monkeypatch.setenv("SECUREWISE_URL_EGRESS_PROOF_FILE", str(tmp_path / "missing-proof.json"))

    assert not url_security.url_egress_enforced()


def test_private_dns_and_redirect_destinations_are_rejected(monkeypatch):
    with pytest.raises(url_security.URLSecurityError, match="valid HTTPS"):
        url_security.parse_https_url(None)

    monkeypatch.setattr(url_security.socket, "getaddrinfo", lambda *args, **kwargs: [(2, 1, 6, "", ("127.0.0.1", 0))])
    with pytest.raises(url_security.URLSecurityError, match="forbidden"):
        url_security.resolve_public_addresses("attacker.example")

    monkeypatch.setattr(
        url_security.socket,
        "getaddrinfo",
        lambda host, *args, **kwargs: [
            (2, 1, 6, "", ("93.184.216.34", 0)) if host == "app.example" else (2, 1, 6, "", ("127.0.0.1", 0))
        ],
    )
    monkeypatch.setattr(
        url_security,
        "_pinned_get_once",
        lambda url, ip, **kwargs: (302, {"location": "https://redirect.example/private"}, b""),
    )
    with pytest.raises(url_security.URLSecurityError, match="forbidden"):
        url_security.safe_https_get(
            "https://app.example/",
            allowed_hosts={"app.example", "redirect.example"},
            allowed_ports={443},
            allowed_paths=["/"],
            excluded_paths=[],
        )


def test_authorized_dast_uses_only_scoped_passive_http(target_workspace, monkeypatch, tmp_path):
    _, _, _, project, client = target_workspace
    target_id = register_and_verify(client, project, monkeypatch)
    authorization_id = authorize_target(client, target_id).json()["id"]
    target = SecureWiseApplicationTarget.objects.get(id=target_id)
    monkeypatch.setattr(url_security, "worker_has_url_egress", lambda: True)
    monkeypatch.setattr(
        url_security,
        "authorize_request",
        lambda authorization, url, worker_id="": (
            200,
            {"content-type": "text/html", "x-powered-by": "fixture/1"},
            b"",
            url,
        ),
    )
    result = DastScanner().run(
        tmp_path,
        "authorized-passive",
        {
            "target_url": f"https://{target.hostname}/shop",
            "testing_authorization_id": authorization_id,
        },
    )
    assert result.success
    assert result.metadata["execution_mode"] == "authorized_passive_http"
    assert result.metadata["active_tests"] is False
    assert any(f.title.startswith("Verbose") for f in result.findings)


def test_authorized_dast_without_active_scope_is_skipped(monkeypatch, tmp_path):
    result = DastScanner().run(
        tmp_path,
        "unauthorized-url",
        {"target_url": "https://example.com/", "testing_authorization_id": "missing"},
    )
    assert result.status == "skipped"
    assert result.metadata["execution_mode"] == "authorization_blocked"


def test_url_jobs_are_claimed_only_by_workers_with_declared_egress_control(target_workspace, monkeypatch):
    owner, _, organization, project, _ = target_workspace
    target = SecureWiseApplicationTarget.objects.create(
        organization=organization,
        project=project,
        hostname="app.customer.example",
        verified_at=timezone.now(),
    )
    authorization = SecureWiseTestingAuthorization.objects.create(
        organization=organization,
        target=target,
        authorized_hosts=[target.hostname],
        allowed_ports=[443],
        allowed_paths=["/"],
        approved_scan_methods=["passive_http"],
        testing_environment="staging",
        starts_at=timezone.now(),
        expires_at=timezone.now() + timedelta(days=1),
        approved_by=owner,
    )
    scan = SecureWiseScan.objects.create(
        organization=organization,
        project=project,
        testing_authorization=authorization,
        scan_type="dast",
        target_url="https://app.customer.example/",
        status="queued",
        triggered_by=owner,
    )

    monkeypatch.setenv("SECUREWISE_URL_EGRESS_ENFORCED", "true")
    monkeypatch.setattr(url_security, "url_egress_enforced", lambda: True)
    SecureWiseWorkerRegistration.objects.create(
        worker_id="unsafe-worker",
        capabilities=["dast"],
        status="online",
        last_seen_at=timezone.now(),
        metrics={"architecture": "amd64"},
    )
    assert claim_next_job("unsafe-worker") is None

    SecureWiseWorkerRegistration.objects.create(
        worker_id="safe-worker",
        capabilities=["dast", "url_egress_restricted"],
        status="online",
        last_seen_at=timezone.now(),
        metrics={"architecture": "amd64"},
    )
    assert claim_next_job("safe-worker") == ("scan", str(scan.id))


def test_authorized_passive_scan_persists_findings_and_execution_mode(target_workspace, monkeypatch):
    owner, _, organization, project, _ = target_workspace
    target = SecureWiseApplicationTarget.objects.create(
        organization=organization,
        project=project,
        hostname="app.customer.example",
        verified_at=timezone.now(),
    )
    authorization = SecureWiseTestingAuthorization.objects.create(
        organization=organization,
        target=target,
        authorized_hosts=[target.hostname],
        allowed_ports=[443],
        allowed_paths=["/"],
        approved_scan_methods=["passive_http"],
        testing_environment="staging",
        starts_at=timezone.now(),
        expires_at=timezone.now() + timedelta(days=1),
        approved_by=owner,
    )
    scan = SecureWiseScan.objects.create(
        organization=organization,
        project=project,
        testing_authorization=authorization,
        scan_type="dast",
        target_url=f"https://{target.hostname}/",
        triggered_by=owner,
    )
    monkeypatch.setattr(
        url_security,
        "authorize_request",
        lambda auth, url, worker_id="": (
            200,
            {"content-type": "text/html", "x-powered-by": "fixture/1"},
            b"",
            url,
        ),
    )

    ScannerRunner().run_scan(str(scan.id), worker_id="fixture-url-worker")

    scan.refresh_from_db()
    engine_result = scan.engine_results.get(engine="dast")
    assert engine_result.raw_summary["execution_mode"] == "authorized_passive_http"
    assert engine_result.raw_summary["active_tests"] is False
    assert scan.findings.filter(title__startswith="Verbose").exists()


def test_real_semgrep_scans_controlled_fixture_without_running_repository_scripts(tmp_path):
    if not shutil.which("semgrep"):
        pytest.skip("Semgrep is unavailable in this environment.")
    fixture = Path(__file__).parents[1] / "fixtures" / "securewise-phase71-vulnerable"
    repo_path = tmp_path / "repo"
    shutil.copytree(fixture, repo_path)
    marker = tmp_path / "build-script-ran"
    (repo_path / "Dockerfile").write_text(f"FROM scratch\nRUN touch {marker}\n")
    (repo_path / "package.json").write_text('{"scripts":{"preinstall":"touch ' + str(marker) + '"}}')

    result = SastScanner().run(repo_path, "phase71-controlled-fixture", {})
    assert result.success
    assert result.metadata["raw_tool"] == "semgrep"
    assert result.metadata["files_scanned"] >= 1
    assert any("eval" in finding.title.lower() for finding in result.findings)
    assert not marker.exists()


def test_real_static_scan_persists_fixture_findings(target_workspace, tmp_path):
    if not shutil.which("semgrep"):
        pytest.skip("Semgrep is unavailable in this environment.")
    owner, _, organization, project, _ = target_workspace
    fixture = Path(__file__).parents[1] / "fixtures" / "securewise-phase71-vulnerable"
    repository_path = tmp_path / "repo"
    shutil.copytree(fixture, repository_path)
    from apps.securewise.models import SecureWiseRepository

    repository = SecureWiseRepository.objects.create(
        organization=organization,
        project=project,
        name="controlled-fixture",
        local_path=str(repository_path),
        access_mode="local_path",
        created_by=owner,
    )
    scan = SecureWiseScan.objects.create(
        organization=organization,
        project=project,
        repository=repository,
        scan_type="sast",
        triggered_by=owner,
    )

    ScannerRunner().run_scan(str(scan.id), worker_id="fixture-static-scanner")

    scan.refresh_from_db()
    assert scan.status in {"completed", "completed_partial"}
    assert scan.engine_results.get(engine="sast").raw_summary["raw_tool"] == "semgrep"
    assert scan.findings.filter(title__icontains="eval").exists()
