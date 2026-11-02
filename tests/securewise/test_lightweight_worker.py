from __future__ import annotations

from datetime import timedelta
from io import StringIO
from types import SimpleNamespace

from django.core.management import call_command
from django.utils import timezone

import pytest

from apps.securewise.models import (
    PentestSession,
    SecureWiseMembership,
    SecureWiseOrganization,
    SecureWiseProject,
    SecureWiseScan,
    SecureWiseWorkerRegistration,
)
from apps.securewise.services.worker import claim_next_job, process_next_job, register_worker
from apps.securewise.services.worker_profile import lightweight_scan_allowed

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner_and_project(django_user_model):
    user = django_user_model.objects.create_user(username="lightweight_worker_owner")
    organization = SecureWiseOrganization.objects.create(name="Lightweight Org", slug="lightweight-org", owner=user)
    SecureWiseMembership.objects.create(organization=organization, user=user, role="owner")
    project = SecureWiseProject.objects.create(
        organization=organization,
        name="Lightweight Project",
        slug="lightweight-project",
        created_by=user,
    )
    return user, organization, project


def test_lightweight_registration_reports_only_static_capabilities(monkeypatch):
    monkeypatch.setenv("SECUREWISE_WORKER_PROFILE", "lightweight")
    monkeypatch.setattr(
        "apps.securewise.services.runners._tool_version",
        lambda *_: pytest.fail("lightweight registration must not invoke scanner binaries"),
    )
    monkeypatch.setattr(
        "apps.securewise.runtime.docker_runner.is_docker_available",
        lambda: pytest.fail("lightweight registration must not probe Docker"),
    )
    monkeypatch.setattr(
        "apps.securewise.services.url_security.url_egress_enforced",
        lambda: pytest.fail("lightweight registration must not advertise URL scanning"),
    )

    registration = register_worker("lightweight-profile-worker")

    assert set(registration.capabilities) == {"sast", "sca", "secrets", "iac", "api"}
    assert registration.metrics["worker_profile"] == "lightweight"
    assert registration.metrics["docker_available"] is False
    assert registration.metrics["host_egress_proof_fresh"] is False
    assert set(registration.metrics["scanner_availability"].values()) == {"disabled"}


def test_lightweight_profile_rejects_external_targets_and_runtime_inputs():
    scan = SimpleNamespace(scan_type="full", target_url="", docker_image="", api_spec_url="")
    assert lightweight_scan_allowed(scan)

    for field, value in (
        ("target_url", "https://outside.example/"),
        ("docker_image", "example/app:latest"),
        ("api_spec_url", "/etc/passwd"),
        ("scan_type", "container"),
        ("scan_type", "dast"),
    ):
        blocked = SimpleNamespace(scan_type="full", target_url="", docker_image="", api_spec_url="")
        setattr(blocked, field, value)
        assert not lightweight_scan_allowed(blocked)


def test_lightweight_claims_only_static_controlled_jobs(owner_and_project, monkeypatch):
    monkeypatch.setenv("SECUREWISE_WORKER_PROFILE", "lightweight")
    user, organization, project = owner_and_project
    static_scan = SecureWiseScan.objects.create(
        organization=organization,
        project=project,
        scan_type="sast",
        status="queued",
        triggered_by=user,
    )
    external_scan = SecureWiseScan.objects.create(
        organization=organization,
        project=project,
        scan_type="dast",
        target_url="https://unauthorized.example/",
        status="queued",
        triggered_by=user,
    )
    SecureWiseWorkerRegistration.objects.create(
        worker_id="lightweight-queue-worker",
        capabilities=["sast", "sca", "secrets", "iac", "api"],
        metrics={"architecture": "amd64", "worker_profile": "lightweight"},
        status="online",
        last_seen_at=timezone.now(),
    )
    monkeypatch.setattr(
        PentestSession.objects,
        "filter",
        lambda *_args, **_kwargs: pytest.fail("lightweight workers must not query or claim AutoPentest jobs"),
    )

    assert claim_next_job("lightweight-queue-worker") == ("scan", str(static_scan.id))
    assert claim_next_job() is None
    external_scan.refresh_from_db()
    assert external_scan.status == "queued"


def test_lightweight_worker_runs_a_synthetic_static_queue_job(owner_and_project, monkeypatch):
    monkeypatch.setenv("SECUREWISE_WORKER_PROFILE", "lightweight")
    user, organization, project = owner_and_project
    scan = SecureWiseScan.objects.create(
        organization=organization,
        project=project,
        scan_type="full",
        status="queued",
        triggered_by=user,
    )
    SecureWiseWorkerRegistration.objects.create(
        worker_id="synthetic-lightweight-job",
        capabilities=["sast", "sca", "secrets", "iac", "api"],
        metrics={"architecture": "amd64", "worker_profile": "lightweight"},
        status="online",
        last_seen_at=timezone.now(),
    )

    assert process_next_job("synthetic-lightweight-job") == ("scan", str(scan.id))

    scan.refresh_from_db()
    assert scan.status == "completed_partial"
    assert scan.selected_engines == ["sast", "sca", "secrets", "iac", "container", "dast"]
    result = scan.engine_results.get(engine="sast")
    assert result.status == "completed"
    assert result.raw_summary["mode"] == "fallback_heuristic"
    assert result.raw_summary["optional_scanner"]["status"] == "disabled"
    assert scan.engine_results.get(engine="container").status == "skipped"
    assert scan.engine_results.get(engine="dast").status == "skipped"


def test_lightweight_scan_fallbacks_report_external_tools_disabled(tmp_path, monkeypatch):
    monkeypatch.setenv("SECUREWISE_WORKER_PROFILE", "lightweight")
    from apps.securewise.scanners.iac import IacScanner
    from apps.securewise.scanners.sast import SastScanner
    from apps.securewise.scanners.sca import ScaScanner
    from apps.securewise.scanners.secrets import SecretsScanner

    for scanner in (SastScanner(), ScaScanner(), SecretsScanner(), IacScanner()):
        result = scanner.run(tmp_path, "fixture-scan", {})
        assert result.success
        assert result.metadata["optional_scanner"]["status"] == "disabled"
        assert result.metadata["optional_scanner"]["name"] in {"semgrep", "trivy", "gitleaks"}


def test_missing_external_scanners_are_reported_unavailable(tmp_path, monkeypatch):
    monkeypatch.delenv("SECUREWISE_WORKER_PROFILE", raising=False)
    monkeypatch.setattr("apps.securewise.scanners.sast.shutil.which", lambda _: None)
    monkeypatch.setattr("apps.securewise.scanners.sca.shutil.which", lambda _: None)
    monkeypatch.setattr("apps.securewise.scanners.secrets.shutil.which", lambda _: None)
    monkeypatch.setattr("apps.securewise.scanners.iac.shutil.which", lambda _: None)
    from apps.securewise.scanners.iac import IacScanner
    from apps.securewise.scanners.sast import SastScanner
    from apps.securewise.scanners.sca import ScaScanner
    from apps.securewise.scanners.secrets import SecretsScanner

    for scanner in (SastScanner(), ScaScanner(), SecretsScanner(), IacScanner()):
        result = scanner.run(tmp_path, "fixture-scan", {})
        assert result.metadata["optional_scanner"]["status"] == "unavailable"


def test_connectivity_check_does_not_claim_or_execute_jobs(monkeypatch):
    from apps.securewise.management.commands import securewise_worker

    monkeypatch.setenv("SECUREWISE_WORKER_PROFILE", "lightweight")
    monkeypatch.setattr(
        securewise_worker,
        "process_next_job",
        lambda **_: pytest.fail("connectivity check must never claim a queued job"),
    )

    output = StringIO()
    call_command(
        "securewise_worker",
        "--check-connectivity",
        "--skip-checks",
        "--worker-id",
        "connectivity-probe",
        stdout=output,
    )

    registration = SecureWiseWorkerRegistration.objects.get(worker_id__startswith="connectivity-probe-probe-")
    assert registration.status == "offline"
    assert registration.last_seen_at > timezone.now() - timedelta(seconds=5)
    assert "no jobs were claimed" in output.getvalue()
