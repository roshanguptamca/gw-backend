"""
RuntimeEnvironmentManager — attempts to auto-start a discovered application
in an isolated, resource-limited Docker container so SecureWise can run a
real DAST scan against it without the user providing a target URL.

Every failure mode here is designed to degrade gracefully: if anything is
unavailable or unsupported, `try_start()` returns a RuntimeResult with
`started=False` and a clear, human-readable `skip_reason` — it never raises
out of a scan.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path

from ..discovery.health import probe_health
from ..discovery.ports import find_free_host_port
from ..discovery.run_plan import ApplicationRunPlan
from . import docker_runner
from .logs import redact_secrets, tail_lines
from .sandbox import TemporaryWorkspace

logger = logging.getLogger(__name__)

_HEALTH_WAIT_TIMEOUT_SECONDS = 45
_HEALTH_POLL_INTERVAL_SECONDS = 2
_IMAGE_TAG_PREFIX = "securewise-scan-tmp"


@dataclass
class RuntimeResult:
    started: bool
    runtime_url: str = ""
    selected_health_endpoint: str = ""
    has_dedicated_health_endpoint: bool = False
    skip_reason: str = ""
    logs: str = ""
    container_name: str = ""


class RuntimeEnvironmentManager:
    """Owns the lifecycle of a single auto-started runtime container per scan."""

    def __init__(self):
        self._container_name: str | None = None
        self._image_tag: str | None = None

    def try_start(self, repo_path: Path, run_plan: ApplicationRunPlan) -> RuntimeResult:
        if not run_plan.requires_runtime:
            return RuntimeResult(started=False, skip_reason="application does not expose an HTTP runtime to scan")

        if not run_plan.can_auto_run:
            return RuntimeResult(
                started=False,
                skip_reason=(
                    "Application could not be auto-started because required runtime dependencies "
                    "were not available (no Dockerfile/docker-compose and no recognized start command)."
                ),
            )

        available, reason = docker_runner.is_docker_available()
        if not available:
            return RuntimeResult(started=False, skip_reason=f"Docker is not available in this environment: {reason}")

        if run_plan.external_services:
            logger.info(
                "Discovered external service dependencies (%s); auto-run will still be attempted "
                "but may fail if those services are required at startup.",
                ", ".join(run_plan.external_services),
            )

        dockerfile_path, workspace_ctx = self._resolve_dockerfile(repo_path, run_plan)
        if dockerfile_path is None:
            return RuntimeResult(
                started=False,
                skip_reason="Application could not be auto-started because no Dockerfile could be generated for this stack.",
            )

        container_port = (run_plan.exposed_ports or run_plan.candidate_ports or [8000])[0]
        host_port = find_free_host_port()
        image_tag = f"{_IMAGE_TAG_PREFIX}:{int(time.time())}"

        build_ok, build_error = docker_runner.build_image(repo_path, dockerfile_path, image_tag)
        if workspace_ctx is not None:
            workspace_ctx.__exit__(None, None, None)

        if not build_ok:
            return RuntimeResult(
                started=False,
                skip_reason="Application could not be auto-started because the Docker build failed.",
                logs=redact_secrets(tail_lines(build_error)),
            )

        self._image_tag = image_tag

        run_ok, container_name, run_error = docker_runner.run_container(image_tag, host_port, container_port)
        self._container_name = container_name
        if not run_ok:
            return RuntimeResult(
                started=False,
                skip_reason="Application could not be auto-started because the container failed to start.",
                logs=redact_secrets(tail_lines(run_error)),
                container_name=container_name,
            )

        runtime_url = f"http://127.0.0.1:{host_port}"
        health = self._wait_for_health(runtime_url, run_plan.selected_health_endpoint)

        if not health["reachable"]:
            logs = redact_secrets(tail_lines(docker_runner.get_logs(container_name)))
            return RuntimeResult(
                started=False,
                skip_reason=(
                    "Application could not be auto-started because it did not become reachable "
                    f"within {_HEALTH_WAIT_TIMEOUT_SECONDS} seconds."
                ),
                logs=logs,
                container_name=container_name,
            )

        return RuntimeResult(
            started=True,
            runtime_url=runtime_url,
            selected_health_endpoint=health["selected_endpoint"],
            has_dedicated_health_endpoint=health["has_dedicated_health_endpoint"],
            container_name=container_name,
        )

    def stop(self) -> None:
        if self._container_name:
            docker_runner.stop_and_remove(self._container_name)
            self._container_name = None
        if self._image_tag:
            docker_runner.remove_image(self._image_tag)
            self._image_tag = None

    # ------------------------------------------------------------------
    def _resolve_dockerfile(self, repo_path: Path, run_plan: ApplicationRunPlan):
        if run_plan.has_dockerfile:
            return repo_path / run_plan.dockerfile_path, None

        language = run_plan.detected_languages[0] if run_plan.detected_languages else ""
        port = (run_plan.exposed_ports or run_plan.candidate_ports or [8000])[0]
        content = docker_runner.generate_dockerfile_content(language, run_plan.start_command, port)
        if not content or not run_plan.start_command:
            return None, None

        workspace = TemporaryWorkspace()
        workspace_path = workspace.__enter__()
        generated_path = workspace_path / "Dockerfile.securewise-generated"
        generated_path.write_text(content, encoding="utf-8")
        return generated_path, workspace

    def _wait_for_health(self, runtime_url: str, preferred_endpoint: str) -> dict:
        deadline = time.time() + _HEALTH_WAIT_TIMEOUT_SECONDS
        last_result = {
            "reachable": False,
            "selected_endpoint": "",
            "has_dedicated_health_endpoint": False,
            "status_code": None,
        }
        while time.time() < deadline:
            last_result = probe_health(runtime_url, preferred_endpoint)
            if last_result["reachable"]:
                return last_result
            time.sleep(_HEALTH_POLL_INTERVAL_SECONDS)
        return last_result
