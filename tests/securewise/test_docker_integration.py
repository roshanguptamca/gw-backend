from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from django.contrib.auth import get_user_model

import pytest

from apps.securewise.models import (
    SecureWiseMembership,
    SecureWiseOrganization,
    SecureWiseProject,
    SecureWiseRepository,
    SecureWiseScan,
)
from apps.securewise.runtime.docker_runner import is_docker_available
from apps.securewise.services.worker import process_next_job

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.skipif(
        os.getenv("SECUREWISE_RUN_DOCKER_INTEGRATION") != "1",
        reason="Set SECUREWISE_RUN_DOCKER_INTEGRATION=1 to run the controlled Docker fixture.",
    ),
]


def test_worker_runs_real_trivy_and_zap_against_controlled_fixture(monkeypatch):
    docker_available, reason = is_docker_available()
    if not docker_available:
        pytest.skip(reason)

    zap_available = subprocess.run(
        [
            "docker",
            "image",
            "inspect",
            "ghcr.io/zaproxy/zaproxy@sha256:7aaa659b0d43078febd82e29bad112285c370727e86ab8340444220e17d9f0d2",
        ],
        capture_output=True,
        timeout=20,
    ).returncode == 0
    if not zap_available:
        pytest.skip("Pull the digest-pinned OWASP ZAP image before running this integration test.")

    user = get_user_model().objects.create_user(
        username="docker-fixture",
        email="docker-fixture@example.test",
        password="securewise-test-only-password",
    )
    organization = SecureWiseOrganization.objects.create(name="Docker Fixture Org", slug="docker-fixture", owner=user)
    SecureWiseMembership.objects.create(organization=organization, user=user, role="owner")
    project = SecureWiseProject.objects.create(
        organization=organization,
        name="Controlled API Fixture",
        slug="controlled-api-fixture",
        created_by=user,
    )
    fixture_path = Path(__file__).parents[1] / "fixtures" / "securewise-autopentest-api"
    repository = SecureWiseRepository.objects.create(
        organization=organization,
        project=project,
        name="securewise-autopentest-api-fixture",
        access_mode="local_path",
        local_path=str(fixture_path),
        repository_url="",
        created_by=user,
    )
    scan = SecureWiseScan.objects.create(
        organization=organization,
        project=project,
        repository=repository,
        scan_type="full",
        status="queued",
        triggered_by=user,
    )
    from apps.securewise.runtime.trust import repository_tree_sha256

    monkeypatch.setenv(
        "SECUREWISE_TRUSTED_RUNTIME_CONTENT",
        f"{repository.id}={repository_tree_sha256(repository.local_path)}",
    )
    monkeypatch.setenv("SECUREWISE_RUNTIME_BUILDS_ENABLED", "true")
    existing_runtime_containers = set(
        subprocess.run(
            ["docker", "ps", "-aq", "--filter", "name=securewise-runtime-"],
            capture_output=True,
            text=True,
            timeout=20,
            check=True,
        ).stdout.split()
    )
    # The fixture scan is synchronous and runs in pytest's SQLite test
    # database; avoid concurrent heartbeat writes while Docker tools execute.
    monkeypatch.setattr("apps.securewise.services.worker.WORKER_HEARTBEAT_SECONDS", 3600)

    assert process_next_job() == ("scan", str(scan.id))
    scan.refresh_from_db()
    engine_results = {result.engine: result for result in scan.engine_results.all()}
    container = engine_results["container"]
    dast = engine_results["dast"]
    assert scan.status in ("completed", "completed_with_warnings")
    assert container.status == "completed", container.raw_summary
    assert container.raw_summary["raw_tool"] == "trivy"
    assert container.raw_summary["image_source"] == "runtime_build"
    assert dast.status == "completed"
    assert dast.raw_summary["execution_mode"] == "zap_baseline"
    assert dast.raw_summary["runner"] == "docker-zap-baseline"
    assert scan.findings.filter(scanner_type="dast").exists()

    image = container.raw_summary["image"]
    assert subprocess.run(
        ["docker", "image", "inspect", image],
        capture_output=True,
        timeout=20,
    ).returncode != 0
    remaining_runtime_containers = set(
        subprocess.run(
            ["docker", "ps", "-aq", "--filter", "name=securewise-runtime-"],
            capture_output=True,
            text=True,
            timeout=20,
            check=True,
        ).stdout.split()
    )
    assert not (
        remaining_runtime_containers - existing_runtime_containers
    ), "the scan left a new runtime container behind"

    evidence = {
        "scan_id": str(scan.id),
        "status": scan.status,
        "engines": {
            "container": {
                "status": container.status,
                "tool": container.raw_summary["raw_tool"],
                "image_source": container.raw_summary["image_source"],
                "findings": container.findings_count,
            },
            "dast": {
                "status": dast.status,
                "execution_mode": dast.raw_summary["execution_mode"],
                "runner": dast.raw_summary["runner"],
                "findings": dast.findings_count,
            },
        },
        "persisted_findings": scan.findings.count(),
        "temporary_image_removed": True,
        "runtime_container_removed": True,
    }
    print(json.dumps(evidence, sort_keys=True))
