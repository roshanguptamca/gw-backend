from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.securewise.models import (
    SecureWiseMembership,
    SecureWiseOrganization,
    SecureWiseProject,
    SecureWiseScan,
    SecureWiseWorkerRegistration,
)
from apps.securewise.services.runners import (
    discover_runner_capabilities,
    runner_fleet_summary,
    select_runner,
    worker_supports_scan,
)
from apps.securewise.services.worker import claim_next_job, heartbeat_worker, release_worker_job
from apps.securewise.services import url_security

pytestmark = pytest.mark.django_db


@pytest.fixture
def queued_scan(django_user_model):
    user = django_user_model.objects.create_user(username="runner_owner")
    organization = SecureWiseOrganization.objects.create(name="Runner Org", slug="runner-org", owner=user)
    SecureWiseMembership.objects.create(organization=organization, user=user, role="owner")
    project = SecureWiseProject.objects.create(
        organization=organization,
        name="Runner Project",
        slug="runner-project",
        created_by=user,
    )
    return SecureWiseScan.objects.create(
        organization=organization,
        project=project,
        scan_type="sast",
        status="queued",
        triggered_by=user,
    )


@pytest.mark.parametrize("architecture", ["arm64", "amd64"])
def test_runner_selection_is_provider_neutral_and_architecture_aware(queued_scan, architecture):
    registration = SecureWiseWorkerRegistration.objects.create(
        worker_id=f"provider-{architecture}",
        capabilities=["sast"],
        metrics={"runner_type": "linux_worker", "provider": "self_hosted", "architecture": architecture},
        status="online",
        last_seen_at=timezone.now(),
    )

    selection = select_runner(queued_scan)

    assert selection.available
    assert selection.worker_id == registration.worker_id
    assert worker_supports_scan(registration, queued_scan)[0]


def test_runner_selection_never_falls_back_when_capability_is_missing(queued_scan):
    SecureWiseWorkerRegistration.objects.create(
        worker_id="secrets-only",
        capabilities=["secrets"],
        metrics={"architecture": "amd64"},
        status="online",
        last_seen_at=timezone.now(),
    )

    selection = select_runner(queued_scan)

    assert not selection.available
    assert "lacks required capabilities: sast" in selection.blocked_reason


def test_url_selection_requires_registered_egress_capability(queued_scan, monkeypatch):
    queued_scan.scan_type = "dast"
    queued_scan.target_url = "https://authorized.example/"
    SecureWiseWorkerRegistration.objects.create(
        worker_id="no-egress-capability",
        capabilities=["dast"],
        metrics={"architecture": "amd64"},
        status="online",
        last_seen_at=timezone.now(),
    )

    selection = select_runner(queued_scan)

    assert not selection.available
    assert "url_egress_restricted" in selection.blocked_reason


def test_control_plane_selection_trusts_registration_but_worker_claim_needs_local_proof(queued_scan, monkeypatch):
    queued_scan.scan_type = "dast"
    queued_scan.target_url = "https://authorized.example/"
    registration = SecureWiseWorkerRegistration.objects.create(
        worker_id="declared-egress",
        capabilities=["dast", "url_egress_restricted"],
        metrics={"architecture": "amd64"},
        status="online",
        last_seen_at=timezone.now(),
    )
    monkeypatch.setattr(url_security, "url_egress_enforced", lambda: False)

    assert select_runner(queued_scan).available
    supported, reason = worker_supports_scan(registration, queued_scan)
    assert not supported
    assert "host egress verification is unavailable" in reason


def test_worker_slot_allows_only_one_active_job(queued_scan):
    registration = SecureWiseWorkerRegistration.objects.create(
        worker_id="single-slot",
        capabilities=["sast"],
        metrics={"architecture": "amd64"},
        status="online",
        last_seen_at=timezone.now(),
    )

    assert claim_next_job("single-slot") == ("scan", str(queued_scan.id))
    registration.refresh_from_db()
    assert registration.active_job_id == str(queued_scan.id)
    assert claim_next_job("single-slot") is None

    release_worker_job("single-slot", str(queued_scan.id))
    registration.refresh_from_db()
    assert registration.active_job_id == ""


def test_worker_heartbeat_preserves_discovered_capabilities(monkeypatch):
    registration = SecureWiseWorkerRegistration.objects.create(
        worker_id="heartbeat-worker",
        capabilities=["sast", "url_egress_restricted"],
        metrics={
            "runner_type": "linux_worker",
            "architecture": "arm64",
            "scanner_versions": {"semgrep": "1.2.3"},
        },
        status="online",
        last_seen_at=timezone.now() - timedelta(minutes=1),
    )
    monkeypatch.setattr(
        "apps.securewise.services.worker.worker_resource_metrics",
        lambda: {"temp_disk_free_bytes": 100},
    )

    heartbeat_worker(registration.worker_id)

    registration.refresh_from_db()
    assert registration.capabilities == ["sast", "url_egress_restricted"]
    assert registration.metrics["runner_type"] == "linux_worker"
    assert registration.metrics["architecture"] == "arm64"
    assert registration.metrics["scanner_versions"] == {"semgrep": "1.2.3"}
    assert registration.metrics["temp_disk_free_bytes"] == 100
    assert registration.last_seen_at > timezone.now() - timedelta(seconds=5)


def test_stale_worker_lease_is_recovered(queued_scan):
    stale_at = timezone.now() - timedelta(minutes=35)
    queued_scan.status = "worker_claimed"
    queued_scan.worker_claimed_at = stale_at
    queued_scan.save(update_fields=["status", "worker_claimed_at"])
    SecureWiseWorkerRegistration.objects.create(
        worker_id="restarted-worker",
        capabilities=["sast"],
        metrics={"architecture": "amd64"},
        status="online",
        last_seen_at=timezone.now(),
        active_job_id=str(queued_scan.id),
        active_job_type="scan",
        active_job_started_at=stale_at,
    )

    assert claim_next_job("restarted-worker") == ("scan", str(queued_scan.id))


def test_fleet_summary_never_exposes_worker_ids_or_hostnames():
    SecureWiseWorkerRegistration.objects.create(
        worker_id="sensitive-hostname.example.internal",
        capabilities=["sast", "sca"],
        metrics={
            "runner_type": "linux_worker",
            "provider": "oracle",
            "architecture": "arm64",
            "scanner_versions": {"semgrep": "1.2.3"},
        },
        status="online",
        last_seen_at=timezone.now(),
    )

    summary = runner_fleet_summary()

    assert len(summary) == 1
    assert summary[0]["runner_type"] == "linux_worker"
    assert summary[0]["architecture"] == "arm64"
    assert summary[0]["scanner_versions"] == {"semgrep": ["1.2.3"]}
    assert "sensitive-hostname.example.internal" not in str(summary)


@pytest.mark.parametrize(("machine", "architecture"), [("aarch64", "arm64"), ("x86_64", "amd64")])
def test_runner_capability_discovery_normalizes_supported_architectures(monkeypatch, machine, architecture):
    from apps.securewise.runtime import docker_runner
    from apps.securewise.services import runners

    monkeypatch.setattr(runners.platform, "machine", lambda: machine)
    monkeypatch.setattr(runners, "_memory_bytes", lambda: 12 * 1024**3)
    monkeypatch.setattr(runners, "_tool_version", lambda executable, arguments: "tool 1.0")
    monkeypatch.setattr(docker_runner, "is_docker_available", lambda: (False, "not installed"))

    capabilities = discover_runner_capabilities(runner_type="linux_worker")

    assert capabilities.architecture == architecture
    assert capabilities.available_memory_bytes == 12 * 1024**3
    assert capabilities.scanner_versions == {
        "semgrep": "tool 1.0",
        "trivy": "tool 1.0",
        "gitleaks": "tool 1.0",
        "zap": "tool 1.0",
    }
    assert not capabilities.docker_available
    assert "playwright" not in capabilities.capabilities


def test_worker_selection_ignores_cloud_provider_label(queued_scan):
    for worker_id, provider in (("a-oracle", "oracle"), ("b-aws", "aws")):
        SecureWiseWorkerRegistration.objects.create(
            worker_id=worker_id,
            capabilities=["sast"],
            metrics={"runner_type": "linux_worker", "provider": provider, "architecture": "amd64"},
            status="online",
            last_seen_at=timezone.now(),
        )

    selection = select_runner(queued_scan)

    assert selection.worker_id == "a-oracle"
