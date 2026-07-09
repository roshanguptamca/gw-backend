"""
Tests for SecureWise Smart Repository Scan: ApplicationDiscoveryEngine,
RuntimeEnvironmentManager, and the orchestrator's smart DAST auto-discovery
wiring. All Docker/subprocess/network calls are mocked; no live containers
or network access are used except the real (offline) filesystem-based
discovery detectors run against real temp directories.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model

import pytest
from rest_framework.test import APIClient

from apps.securewise.discovery.detectors import detect_node, detect_python
from apps.securewise.discovery.engine import ApplicationDiscoveryEngine
from apps.securewise.discovery.health import probe_health
from apps.securewise.discovery.ports import (
    find_free_host_port,
    parse_compose_host_ports,
    parse_dockerfile_exposed_ports,
)
from apps.securewise.models import (
    SecureWiseMembership,
    SecureWiseOrganization,
    SecureWiseProject,
    SecureWiseRepository,
    SecureWiseScan,
    SecureWiseScanEngineResult,
)
from apps.securewise.runtime import docker_runner
from apps.securewise.runtime.manager import RuntimeEnvironmentManager
from apps.securewise.scanners.orchestrator import ScannerOrchestrator

User = get_user_model()
pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def org_project(db):
    owner = User.objects.create_user(username="smart_owner", email="smart@sw.test", password="testpass123")
    org = SecureWiseOrganization.objects.create(name="SmartOrg", slug="smartorg", owner=owner)
    SecureWiseMembership.objects.create(organization=org, user=owner, role="owner")
    project = SecureWiseProject.objects.create(organization=org, name="SmartProj", slug="smartproj", created_by=owner)
    return owner, org, project


@pytest.fixture
def repository(org_project):
    owner, org, project = org_project
    return SecureWiseRepository.objects.create(
        organization=org,
        project=project,
        name="smart-repo",
        repository_url="https://github.com/test/smart-repo",
        clone_url="https://github.com/test/smart-repo.git",
        access_mode="public",
        created_by=owner,
    )


def _make_django_repo(tmp_path: Path) -> Path:
    (tmp_path / "manage.py").write_text("#!/usr/bin/env python\n")
    (tmp_path / "requirements.txt").write_text("django\n")
    (tmp_path / "Dockerfile").write_text(
        "FROM python:3.11-slim\nEXPOSE 8000\nCMD python manage.py runserver 0.0.0.0:8000\n"
    )
    return tmp_path


def _make_scan_with_repo(org, project, owner, repository, scan_type="full", **kwargs):
    return SecureWiseScan.objects.create(
        organization=org,
        project=project,
        repository=repository,
        scan_type=scan_type,
        status="pending",
        triggered_by=owner,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Discovery detectors / ports / health — pure unit tests, no mocking needed.
# ---------------------------------------------------------------------------


class TestDiscoveryDetectors:
    def test_detect_python_django(self, tmp_path):
        _make_django_repo(tmp_path)
        result = detect_python(tmp_path)
        assert result is not None
        assert result["framework"] == "django"
        assert result["project_type"] == "web_app"
        assert result["default_port"] == 8000

    def test_detect_python_fastapi(self, tmp_path):
        (tmp_path / "requirements.txt").write_text("fastapi\nuvicorn\n")
        (tmp_path / "main.py").write_text("from fastapi import FastAPI\napp = FastAPI()\n")
        result = detect_python(tmp_path)
        assert result is not None
        assert result["framework"] == "fastapi"
        assert result["project_type"] == "api_service"
        assert "main:app" in result["start_command"]

    def test_detect_node_express(self, tmp_path):
        (tmp_path / "package.json").write_text(
            '{"dependencies": {"express": "^4.0.0"}, "scripts": {"start": "node index.js"}}'
        )
        result = detect_node(tmp_path)
        assert result is not None
        assert result["framework"] == "express"
        assert result["project_type"] == "api_service"

    def test_detect_python_returns_none_for_non_python_repo(self, tmp_path):
        (tmp_path / "package.json").write_text("{}")
        assert detect_python(tmp_path) is None

    def test_parse_dockerfile_exposed_ports(self):
        assert parse_dockerfile_exposed_ports("FROM python\nEXPOSE 8000\n") == [8000]
        assert parse_dockerfile_exposed_ports("EXPOSE 8000 9000/tcp\n") == [8000, 9000]
        assert parse_dockerfile_exposed_ports("FROM python\n") == []

    def test_parse_compose_host_ports(self):
        compose_text = 'services:\n  web:\n    ports:\n      - "8000:8000"\n'
        assert parse_compose_host_ports(compose_text) == [8000]

    def test_find_free_host_port_returns_usable_port(self):
        port = find_free_host_port()
        assert 1 <= port <= 65535


class TestHealthProbe:
    def test_probe_health_dedicated_endpoint_reachable(self):
        with patch("apps.securewise.discovery.health.requests.get") as mock_get:

            def side_effect(url, timeout=None, allow_redirects=True):
                resp = MagicMock()
                resp.status_code = 200 if url.endswith("/health") else 404
                return resp

            mock_get.side_effect = side_effect
            result = probe_health("http://127.0.0.1:8000")
        assert result["reachable"] is True
        assert result["selected_endpoint"] == "/health"
        assert result["has_dedicated_health_endpoint"] is True

    def test_probe_health_falls_back_to_root(self):
        with patch("apps.securewise.discovery.health.requests.get") as mock_get:

            def side_effect(url, timeout=None, allow_redirects=True):
                resp = MagicMock()
                resp.status_code = 200 if url.rstrip("/").endswith(":8000") or url.endswith("/") else 404
                return resp

            mock_get.side_effect = side_effect
            result = probe_health("http://127.0.0.1:8000")
        assert result["reachable"] is True
        assert result["selected_endpoint"] == "/"
        assert result["has_dedicated_health_endpoint"] is False

    def test_probe_health_unreachable(self):
        import requests

        with patch("apps.securewise.discovery.health.requests.get", side_effect=requests.RequestException("boom")):
            result = probe_health("http://127.0.0.1:9")
        assert result["reachable"] is False
        assert result["selected_endpoint"] == ""


# ---------------------------------------------------------------------------
# ApplicationDiscoveryEngine
# ---------------------------------------------------------------------------


class TestApplicationDiscoveryEngine:
    def test_discovers_django_app_with_dockerfile(self, tmp_path):
        _make_django_repo(tmp_path)
        plan = ApplicationDiscoveryEngine().discover(tmp_path)
        assert plan.project_type == "web_app"
        assert "django" in plan.detected_frameworks
        assert plan.has_dockerfile is True
        assert plan.can_auto_run is True
        assert plan.requires_runtime is True
        assert 8000 in plan.exposed_ports

    def test_unknown_project_type_for_unrecognized_repo(self, tmp_path):
        (tmp_path / "README.md").write_text("just docs")
        plan = ApplicationDiscoveryEngine().discover(tmp_path)
        assert plan.project_type == "unknown"
        assert plan.requires_runtime is False
        assert plan.can_auto_run is False
        assert plan.skip_reasons

    def test_library_project_type_does_not_require_runtime(self, tmp_path):
        (tmp_path / "requirements.txt").write_text("requests\n")
        (tmp_path / "setup.py").write_text("from setuptools import setup\nsetup(name='x')\n")
        (tmp_path / "mylib.py").write_text("def hello():\n    return 'hi'\n")
        plan = ApplicationDiscoveryEngine().discover(tmp_path)
        assert plan.project_type == "library"
        assert plan.requires_runtime is False
        assert plan.can_auto_run is False

    def test_nonexistent_path_returns_unknown_plan_without_crashing(self, tmp_path):
        plan = ApplicationDiscoveryEngine().discover(tmp_path / "does-not-exist")
        assert plan.project_type == "unknown"
        assert plan.skip_reasons

    def test_real_gw_backend_repo_detects_django(self):
        """Sanity check against the real, on-disk gw-backend repository itself."""
        repo_path = Path(__file__).resolve().parents[2]
        plan = ApplicationDiscoveryEngine().discover(repo_path)
        assert "django" in plan.detected_frameworks
        assert plan.project_type == "web_app"
        assert plan.has_dockerfile is True
        assert plan.can_auto_run is True


# ---------------------------------------------------------------------------
# RuntimeEnvironmentManager
# ---------------------------------------------------------------------------


class TestRuntimeEnvironmentManager:
    def test_try_start_skips_when_docker_unavailable(self, tmp_path):
        _make_django_repo(tmp_path)
        plan = ApplicationDiscoveryEngine().discover(tmp_path)
        with patch(
            "apps.securewise.runtime.manager.docker_runner.is_docker_available",
            return_value=(False, "daemon unreachable"),
        ):
            result = RuntimeEnvironmentManager().try_start(tmp_path, plan)
        assert result.started is False
        assert "Docker is not available" in result.skip_reason

    def test_try_start_skips_when_cannot_auto_run(self, tmp_path):
        (tmp_path / "README.md").write_text("docs only")
        plan = ApplicationDiscoveryEngine().discover(tmp_path)
        result = RuntimeEnvironmentManager().try_start(tmp_path, plan)
        assert result.started is False
        assert result.skip_reason

    def test_try_start_skips_when_no_runtime_required(self, tmp_path):
        (tmp_path / "requirements.txt").write_text("requests\n")
        (tmp_path / "setup.py").write_text("setup()\n")
        (tmp_path / "mylib.py").write_text("pass\n")
        plan = ApplicationDiscoveryEngine().discover(tmp_path)
        result = RuntimeEnvironmentManager().try_start(tmp_path, plan)
        assert result.started is False
        assert "does not expose an HTTP runtime" in result.skip_reason

    def test_try_start_succeeds_with_mocked_docker(self, tmp_path):
        _make_django_repo(tmp_path)
        plan = ApplicationDiscoveryEngine().discover(tmp_path)
        with (
            patch("apps.securewise.runtime.manager.docker_runner.is_docker_available", return_value=(True, "")),
            patch("apps.securewise.runtime.manager.docker_runner.build_image", return_value=(True, "")),
            patch(
                "apps.securewise.runtime.manager.docker_runner.run_container",
                return_value=(True, "securewise-runtime-test", ""),
            ),
            patch(
                "apps.securewise.runtime.manager.probe_health",
                return_value={
                    "reachable": True,
                    "selected_endpoint": "/health",
                    "has_dedicated_health_endpoint": True,
                    "status_code": 200,
                },
            ),
        ):
            result = RuntimeEnvironmentManager().try_start(tmp_path, plan)
        assert result.started is True
        assert result.runtime_url.startswith("http://127.0.0.1:")
        assert result.selected_health_endpoint == "/health"

    def test_try_start_reports_failure_when_container_never_becomes_reachable(self, tmp_path):
        _make_django_repo(tmp_path)
        plan = ApplicationDiscoveryEngine().discover(tmp_path)
        with (
            patch("apps.securewise.runtime.manager.docker_runner.is_docker_available", return_value=(True, "")),
            patch("apps.securewise.runtime.manager.docker_runner.build_image", return_value=(True, "")),
            patch(
                "apps.securewise.runtime.manager.docker_runner.run_container",
                return_value=(True, "securewise-runtime-test", ""),
            ),
            patch("apps.securewise.runtime.manager.docker_runner.get_logs", return_value="boot error"),
            patch(
                "apps.securewise.runtime.manager.probe_health",
                return_value={
                    "reachable": False,
                    "selected_endpoint": "",
                    "has_dedicated_health_endpoint": False,
                    "status_code": None,
                },
            ),
            patch("apps.securewise.runtime.manager._HEALTH_WAIT_TIMEOUT_SECONDS", 0),
        ):
            result = RuntimeEnvironmentManager().try_start(tmp_path, plan)
        assert result.started is False
        assert "did not become reachable" in result.skip_reason

    def test_stop_calls_docker_cleanup(self):
        manager = RuntimeEnvironmentManager()
        manager._container_name = "securewise-runtime-test"
        with patch("apps.securewise.runtime.manager.docker_runner.stop_and_remove") as mock_stop:
            manager.stop()
        mock_stop.assert_called_once_with("securewise-runtime-test")

    def test_stop_also_removes_temporary_build_image(self):
        """Regression test: build images must be cleaned up alongside containers so scan
        hosts don't accumulate disk usage over repeated scans (found via live Docker test)."""
        manager = RuntimeEnvironmentManager()
        manager._container_name = "securewise-runtime-test"
        manager._image_tag = "securewise-scan-tmp:12345"
        with (
            patch("apps.securewise.runtime.manager.docker_runner.stop_and_remove") as mock_stop,
            patch("apps.securewise.runtime.manager.docker_runner.remove_image") as mock_rmi,
        ):
            manager.stop()
        mock_stop.assert_called_once_with("securewise-runtime-test")
        mock_rmi.assert_called_once_with("securewise-scan-tmp:12345")
        assert manager._container_name is None
        assert manager._image_tag is None

    def test_stop_does_not_call_remove_image_when_no_image_was_built(self):
        manager = RuntimeEnvironmentManager()
        with patch("apps.securewise.runtime.manager.docker_runner.remove_image") as mock_rmi:
            manager.stop()
        mock_rmi.assert_not_called()

    def test_is_docker_available_detects_missing_daemon(self):
        """Real (not mocked) check — validates the actual subprocess wrapper logic."""
        with patch("apps.securewise.runtime.docker_runner.shutil.which", return_value="/usr/local/bin/docker"):
            with patch("apps.securewise.runtime.docker_runner.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=1, stderr="Cannot connect to the Docker daemon")
                available, reason = docker_runner.is_docker_available()
        assert available is False
        assert "daemon unreachable" in reason

    def test_is_docker_available_false_when_cli_missing(self):
        with patch("apps.securewise.runtime.docker_runner.shutil.which", return_value=None):
            available, reason = docker_runner.is_docker_available()
        assert available is False
        assert "not installed" in reason


# ---------------------------------------------------------------------------
# Orchestrator: smart DAST auto-discovery wiring
# ---------------------------------------------------------------------------


class TestOrchestratorSmartDast:
    def test_resolve_engines_includes_dast_when_repository_set_even_without_target_url(
        self, org_project, repository, tmp_path
    ):
        owner, org, project = org_project
        scan = _make_scan_with_repo(org, project, owner, repository, scan_type="full")
        engines = ScannerOrchestrator().resolve_engines(scan, tmp_path)
        assert "dast" in engines

    def test_resolve_engines_excludes_dast_without_repository_or_target_url(self, org_project, tmp_path):
        owner, org, project = org_project
        scan = SecureWiseScan.objects.create(
            organization=org, project=project, scan_type="full", status="pending", triggered_by=owner
        )
        engines = ScannerOrchestrator().resolve_engines(scan, tmp_path)
        assert "dast" not in engines
        assert engines == ["sast", "sca", "secrets", "iac"]

    def test_run_skips_dast_with_clear_reason_when_docker_unavailable(self, org_project, repository, tmp_path):
        owner, org, project = org_project
        _make_django_repo(tmp_path)
        scan = _make_scan_with_repo(org, project, owner, repository, scan_type="full")

        import contextlib

        with contextlib.ExitStack() as stack:
            for cls in ("SastScanner", "ScaScanner", "SecretsScanner", "IacScanner"):
                stack.enter_context(
                    patch(f"apps.securewise.scanners.orchestrator.{cls}.run", return_value=_ok_result())
                )
            stack.enter_context(
                patch(
                    "apps.securewise.runtime.manager.docker_runner.is_docker_available",
                    return_value=(False, "Cannot connect to the Docker daemon"),
                )
            )
            findings, engine_meta, any_failed, any_skipped = ScannerOrchestrator().run(scan, tmp_path)

        assert any_skipped is True
        assert any_failed is False
        dast_result = SecureWiseScanEngineResult.objects.get(scan=scan, engine="dast")
        assert dast_result.status == "skipped"
        assert "Docker is not available" in dast_result.skipped_reason

    def test_run_uses_discovered_runtime_url_for_dast_when_runtime_starts(self, org_project, repository, tmp_path):
        owner, org, project = org_project
        _make_django_repo(tmp_path)
        scan = _make_scan_with_repo(org, project, owner, repository, scan_type="full")

        captured_metadata = {}

        def _fake_dast_run(self, repo_path, scan_id, metadata):
            captured_metadata.update(metadata)
            return _ok_result()

        import contextlib

        with contextlib.ExitStack() as stack:
            for cls in ("SastScanner", "ScaScanner", "SecretsScanner", "IacScanner", "ContainerScanner"):
                stack.enter_context(
                    patch(f"apps.securewise.scanners.orchestrator.{cls}.run", return_value=_ok_result())
                )
            stack.enter_context(patch("apps.securewise.scanners.orchestrator.DastScanner.run", _fake_dast_run))
            stack.enter_context(
                patch("apps.securewise.runtime.manager.docker_runner.is_docker_available", return_value=(True, ""))
            )
            stack.enter_context(
                patch("apps.securewise.runtime.manager.docker_runner.build_image", return_value=(True, ""))
            )
            stack.enter_context(
                patch(
                    "apps.securewise.runtime.manager.docker_runner.run_container",
                    return_value=(True, "securewise-runtime-test", ""),
                )
            )
            stack.enter_context(
                patch(
                    "apps.securewise.runtime.manager.probe_health",
                    return_value={
                        "reachable": True,
                        "selected_endpoint": "/health",
                        "has_dedicated_health_endpoint": True,
                        "status_code": 200,
                    },
                )
            )
            mock_stop = stack.enter_context(patch("apps.securewise.runtime.manager.docker_runner.stop_and_remove"))
            stack.enter_context(patch("apps.securewise.runtime.manager.docker_runner.remove_image"))
            findings, engine_meta, any_failed, any_skipped = ScannerOrchestrator().run(scan, tmp_path)

        assert any_skipped is False
        assert captured_metadata["target_url"].startswith("http://127.0.0.1:")
        mock_stop.assert_called_once()

        scan.refresh_from_db()
        assert "discovery" in scan.scanner_metadata
        assert scan.scanner_metadata["discovery"]["project_type"] == "web_app"

    def test_run_adds_low_finding_when_no_dedicated_health_endpoint(self, org_project, repository, tmp_path):
        """Missing health endpoint/HEALTHCHECK is a LOW recommendation, never a scan failure."""
        owner, org, project = org_project
        _make_django_repo(tmp_path)
        scan = _make_scan_with_repo(org, project, owner, repository, scan_type="full")

        import contextlib

        with contextlib.ExitStack() as stack:
            for cls in ("SastScanner", "ScaScanner", "SecretsScanner", "IacScanner", "ContainerScanner"):
                stack.enter_context(
                    patch(f"apps.securewise.scanners.orchestrator.{cls}.run", return_value=_ok_result())
                )
            stack.enter_context(
                patch("apps.securewise.scanners.orchestrator.DastScanner.run", return_value=_ok_result())
            )
            stack.enter_context(
                patch("apps.securewise.runtime.manager.docker_runner.is_docker_available", return_value=(True, ""))
            )
            stack.enter_context(
                patch("apps.securewise.runtime.manager.docker_runner.build_image", return_value=(True, ""))
            )
            stack.enter_context(
                patch(
                    "apps.securewise.runtime.manager.docker_runner.run_container",
                    return_value=(True, "securewise-runtime-test", ""),
                )
            )
            stack.enter_context(
                patch(
                    "apps.securewise.runtime.manager.probe_health",
                    return_value={
                        "reachable": True,
                        "selected_endpoint": "/",
                        "has_dedicated_health_endpoint": False,
                        "status_code": 200,
                    },
                )
            )
            stack.enter_context(patch("apps.securewise.runtime.manager.docker_runner.stop_and_remove"))
            stack.enter_context(patch("apps.securewise.runtime.manager.docker_runner.remove_image"))
            findings, engine_meta, any_failed, any_skipped = ScannerOrchestrator().run(scan, tmp_path)

        titles = [f.title for f in findings]
        assert "Missing Docker HEALTHCHECK or application health endpoint" in titles
        health_finding = next(f for f in findings if f.title.startswith("Missing Docker HEALTHCHECK"))
        assert health_finding.severity == "low"
        assert health_finding.cwe_id == "CWE-703"

    def test_run_does_not_attempt_discovery_without_repository(self, org_project, tmp_path):
        """Existing behavior for bare tmp_path/no-repository scans must be unaffected."""
        owner, org, project = org_project
        scan = SecureWiseScan.objects.create(
            organization=org,
            project=project,
            scan_type="full",
            status="pending",
            triggered_by=owner,
            target_url="https://example.test",
        )
        with patch("apps.securewise.scanners.orchestrator.ApplicationDiscoveryEngine") as mock_engine_cls:
            findings, engine_meta, any_failed, any_skipped = ScannerOrchestrator().run(scan, tmp_path)
        mock_engine_cls.assert_not_called()


def _ok_result():
    from apps.securewise.scanners.base import ScannerResult

    return ScannerResult(success=True, findings=[], metadata={"raw_tool": "test"})


# ---------------------------------------------------------------------------
# Discovery preview API endpoint
# ---------------------------------------------------------------------------


class TestDiscoveryPreviewApi:
    def test_discovery_preview_returns_detected_stack(self, org_project, repository, tmp_path):
        owner, org, project = org_project
        client = APIClient()
        client.force_authenticate(user=owner)

        def _fake_clone(scan, repo_path, allowed_root=None, timeout=120):
            repo_path.mkdir(parents=True, exist_ok=True)
            _make_django_repo(repo_path)

        with patch("apps.securewise.scanners.repository.clone_repository", _fake_clone):
            resp = client.post(f"/api/securewise/repositories/{repository.id}/discovery-preview/")

        assert resp.status_code == 200
        data = resp.json()
        assert data["project_type"] == "web_app"
        assert "django" in data["detected_frameworks"]
        assert data["can_auto_run"] is True

    def test_discovery_preview_handles_clone_failure_gracefully(self, org_project, repository):
        owner, org, project = org_project
        client = APIClient()
        client.force_authenticate(user=owner)

        with patch("apps.securewise.scanners.repository.clone_repository", side_effect=RuntimeError("clone failed")):
            resp = client.post(f"/api/securewise/repositories/{repository.id}/discovery-preview/")

        assert resp.status_code == 422
        assert "error" in resp.json()
