from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.securewise.models import (
    SecureWiseApplicationTarget,
    SecureWiseMembership,
    SecureWiseOrganization,
    SecureWiseProject,
    SecureWiseRepository,
    SecureWiseScan,
    SecureWiseTestingAuthorization,
    SecureWiseWorkerRegistration,
)
from apps.securewise.services import runners, worker
from apps.securewise.services.worker import claim_next_job, register_worker

pytestmark = pytest.mark.django_db


@pytest.fixture
def env(django_user_model):
    user = django_user_model.objects.create_user(username="web_owner")
    org = SecureWiseOrganization.objects.create(name="W", slug="w", owner=user)
    SecureWiseMembership.objects.create(organization=org, user=user, role="owner")
    project = SecureWiseProject.objects.create(organization=org, name="P", slug="p", created_by=user)
    target = SecureWiseApplicationTarget.objects.create(
        organization=org, project=project, hostname="guidewisey.com", verified_at=timezone.now(), created_by=user
    )
    now = timezone.now()
    authorization = SecureWiseTestingAuthorization.objects.create(
        organization=org,
        target=target,
        authorized_hosts=["guidewisey.com"],
        allowed_ports=[443],
        allowed_paths=["/"],
        approved_scan_methods=["passive_http"],
        testing_environment="production",
        starts_at=now - timedelta(minutes=1),
        expires_at=now + timedelta(hours=1),
        approved_by=user,
    )
    return org, project, authorization


def _scan(env, **extra):
    org, project, authorization = env
    return SecureWiseScan.objects.create(
        organization=org,
        project=project,
        scan_type="dast",
        target_url="https://guidewisey.com/",
        testing_authorization=authorization,
        status="queued",
        **extra,
    )


def _register(monkeypatch, *, egress: bool):
    monkeypatch.setenv("SECUREWISE_WORKER_PROFILE", "website_passive")
    monkeypatch.setattr("apps.securewise.services.url_security.url_egress_enforced", lambda: egress)
    monkeypatch.setattr(worker, "worker_resource_metrics", lambda: {})
    monkeypatch.setattr(runners, "_available_worker_memory_bytes", lambda: 400 * 1024 * 1024)
    return register_worker("website-1")


def test_capabilities_follow_actual_egress_proof(monkeypatch):
    proven = _register(monkeypatch, egress=True)
    assert set(proven.capabilities) == {"dast", "url_egress_restricted"}
    assert proven.metrics["worker_profile"] == "website_passive"
    assert "docker_daemon" not in proven.capabilities

    unproven = _register(monkeypatch, egress=False)
    assert unproven.capabilities == []


def test_website_worker_claims_only_authorized_url_scans(monkeypatch, env):
    org, project, _ = env
    scan = _scan(env)
    SecureWiseScan.objects.create(organization=org, project=project, scan_type="sast", status="queued")
    _register(monkeypatch, egress=True)

    assert claim_next_job("website-1") == ("scan", str(scan.id))


def test_website_worker_never_claims_repository_or_unauthorized_scans(monkeypatch, env, tmp_path):
    org, project, authorization = env
    repo = SecureWiseRepository.objects.create(
        organization=org, project=project, name="r", access_mode="local_path", local_path=str(tmp_path)
    )
    _scan(env, repository=repo)
    SecureWiseScan.objects.create(
        organization=org, project=project, scan_type="dast", target_url="https://guidewisey.com/", status="queued"
    )
    _register(monkeypatch, egress=True)

    assert claim_next_job("website-1") is None


def test_website_worker_without_egress_proof_claims_nothing(monkeypatch, env):
    _scan(env)
    _register(monkeypatch, egress=False)
    assert claim_next_job("website-1") is None


def test_website_worker_requires_registered_identity(monkeypatch, env):
    _scan(env)
    monkeypatch.setenv("SECUREWISE_WORKER_PROFILE", "website_passive")
    assert claim_next_job("") is None


def test_lightweight_worker_still_ignores_url_scans(monkeypatch, env):
    _scan(env)
    monkeypatch.setenv("SECUREWISE_WORKER_PROFILE", "lightweight")
    SecureWiseWorkerRegistration.objects.create(
        worker_id="light-1",
        capabilities=["sast", "sca", "secrets", "iac", "api"],
        metrics={"architecture": "amd64", "worker_profile": "lightweight"},
        status="online",
        last_seen_at=timezone.now(),
    )
    assert claim_next_job("light-1") is None


def test_claimed_scan_keeps_a_durable_worker_execution_record(monkeypatch, env):
    from apps.securewise.models import SecureWiseAuditLog
    from apps.securewise.services.scanner import ScannerOrchestrator, ScannerRunner

    scan = _scan(env)
    _register(monkeypatch, egress=True)
    assert claim_next_job("website-1") == ("scan", str(scan.id))
    scan.refresh_from_db()
    assert scan.status == "worker_claimed" and scan.worker_claimed_at is not None
    monkeypatch.setattr(ScannerOrchestrator, "run", lambda self, s, p: ([], {}, False, False))

    ScannerRunner().run_scan(str(scan.id), worker_id="website-1")

    scan.refresh_from_db()
    execution = scan.scanner_metadata["execution"]
    assert scan.worker_claimed_at is None  # lease cleared; the record below is the audit trail
    assert execution["worker_id"] == "website-1"
    assert execution["claimed_at"] and execution["started_at"] and execution["completed_at"]
    started = SecureWiseAuditLog.objects.get(event="scan_started", target_id=str(scan.id))
    assert started.detail["worker_id"] == "website-1"
    finished = SecureWiseAuditLog.objects.get(event="scan_completed", target_id=str(scan.id))
    assert finished.detail["worker_id"] == "website-1"


def test_retest_keeps_findings_visible_on_the_original_scan(env):
    from rest_framework.test import APIRequestFactory, force_authenticate

    from apps.securewise.models import SecureWiseFinding
    from apps.securewise.serializers import SecureWiseScanSerializer
    from apps.securewise.services.scanner import ScannerRunner

    org, project, _ = env
    first, second = _scan(env), _scan(env)
    finding = type(
        "F", (), dict(
            title="Missing CSP", description="d", severity="medium", confidence="high",
            scanner_type="dast", file_path="", line_number=None, endpoint="https://guidewisey.com/",
            cwe_id="CWE-693", owasp_category="A05:2021", risk="", impact="", recommendation="",
            bad_code_example="", fixed_code_example="", code_snippet="", evidence="e", fingerprint="fp-csp",
        ),
    )()
    runner = ScannerRunner()
    runner._persist_findings(first, [finding])
    runner._persist_findings(second, [finding])

    assert SecureWiseFinding.objects.filter(project=project).count() == 1
    for scan in (first, second):
        assert SecureWiseFinding.objects.filter(SecureWiseFinding.for_scan_q(scan.id)).count() == 1
        counts = SecureWiseScanSerializer().get_finding_counts(scan)
        assert counts["medium"] == 1
