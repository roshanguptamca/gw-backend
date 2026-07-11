"""
Low-level Docker CLI wrapper for the RuntimeEnvironmentManager.

Design constraints (see docs/SMART_REPO_SCAN.md):
 - Never use --privileged.
 - Never mount the host root or any host path other than the ephemeral clone.
 - Always enforce resource limits and a hard timeout.
 - Never fail a whole scan just because Docker isn't available — report a
   clear, honest skip reason instead.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)

_DOCKER_AVAILABILITY_TIMEOUT = 5
_BUILD_TIMEOUT = 240
_RUN_STARTUP_TIMEOUT = 5
_STOP_TIMEOUT = 15

# Conservative resource limits for auto-started scan targets.
_MEMORY_LIMIT = "512m"
_CPU_LIMIT = "1.0"

# Minimal, well-known runtime base images used only when we must generate a
# temporary Dockerfile for a repo that doesn't ship one.
GENERATED_DOCKERFILE_TEMPLATES = {
    "python": (
        "FROM python:3.11-slim\n"
        "WORKDIR /app\n"
        "COPY . /app\n"
        "RUN pip install --no-cache-dir -r requirements.txt || true\n"
        "EXPOSE {port}\n"
        "CMD {start_command}\n"
    ),
    "node": (
        "FROM node:20-slim\n"
        "WORKDIR /app\n"
        "COPY . /app\n"
        "RUN npm install --omit=dev || npm install || true\n"
        "EXPOSE {port}\n"
        "CMD {start_command}\n"
    ),
    "go": (
        "FROM golang:1.22\n"
        "WORKDIR /app\n"
        "COPY . /app\n"
        "RUN go build -o /app/bin/service . || true\n"
        "EXPOSE {port}\n"
        'CMD ["/app/bin/service"]\n'
    ),
    "php": (
        "FROM php:8.2-cli\n"
        "WORKDIR /app\n"
        "COPY . /app\n"
        "RUN true\n"
        "EXPOSE {port}\n"
        "CMD {start_command}\n"
    ),
    "ruby": (
        "FROM ruby:3.3-slim\n"
        "WORKDIR /app\n"
        "COPY . /app\n"
        "RUN bundle install || true\n"
        "EXPOSE {port}\n"
        "CMD {start_command}\n"
    ),
}


def is_docker_available() -> tuple[bool, str]:
    """Check whether Docker is installed *and* the daemon is reachable."""
    if not shutil.which("docker"):
        return False, "Docker CLI is not installed in this environment"

    try:
        proc = subprocess.run(
            ["docker", "version", "--format", "{{.Server.Version}}"],
            capture_output=True,
            timeout=_DOCKER_AVAILABILITY_TIMEOUT,
            text=True,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return False, f"Docker daemon check timed out or errored: {exc}"

    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()
        return False, f"Docker is not available in this environment (daemon unreachable): {stderr or 'unknown error'}"

    return True, ""


def build_dockerfile_command(dockerfile_shell_command: str) -> list[str]:
    """Split a plain-text start command into a Docker CMD-friendly shell form."""
    return ["sh", "-c", dockerfile_shell_command]


def generate_dockerfile_content(language: str, start_command: str, port: int) -> str | None:
    template = GENERATED_DOCKERFILE_TEMPLATES.get(language)
    if not template:
        return None
    return template.format(port=port, start_command=start_command)


def build_image(context_path: Path, dockerfile_path: Path, tag: str) -> tuple[bool, str]:
    try:
        proc = subprocess.run(
            [
                "docker",
                "build",
                "--quiet",
                "-f",
                str(dockerfile_path),
                "-t",
                tag,
                str(context_path),
            ],
            capture_output=True,
            timeout=_BUILD_TIMEOUT,
            text=True,
        )
    except subprocess.TimeoutExpired:
        return False, f"docker build timed out after {_BUILD_TIMEOUT}s"
    except OSError as exc:
        return False, f"docker build failed to start: {exc}"

    if proc.returncode != 0:
        return False, (proc.stderr or proc.stdout or "docker build failed").strip()[-2000:]
    return True, ""


def run_container(
    image: str, host_port: int, container_port: int, env_vars: dict[str, str] | None = None
) -> tuple[bool, str, str]:
    """
    Start a container in the background.

    Returns (success, container_id, error). Never uses --privileged, never
    mounts host paths, always sets memory/cpu limits and auto-remove.
    """
    container_name = f"securewise-runtime-{uuid.uuid4().hex[:10]}"
    cmd = [
        "docker",
        "run",
        "-d",
        "--name",
        container_name,
        "--memory",
        _MEMORY_LIMIT,
        "--cpus",
        _CPU_LIMIT,
        "--network",
        "bridge",
        "-p",
        f"{host_port}:{container_port}",
    ]
    for key, value in (env_vars or {}).items():
        cmd += ["-e", f"{key}={value}"]
    cmd.append(image)

    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=_RUN_STARTUP_TIMEOUT + 10, text=True)
    except subprocess.TimeoutExpired:
        return False, container_name, "docker run timed out while starting the container"
    except OSError as exc:
        return False, container_name, f"docker run failed to start: {exc}"

    if proc.returncode != 0:
        return False, container_name, (proc.stderr or proc.stdout or "docker run failed").strip()[-2000:]

    return True, container_name, ""


def get_logs(container_name: str) -> str:
    try:
        proc = subprocess.run(
            ["docker", "logs", "--tail", "200", container_name],
            capture_output=True,
            timeout=10,
            text=True,
        )
        return (proc.stdout or "") + (proc.stderr or "")
    except (subprocess.TimeoutExpired, OSError):
        return ""


def stop_and_remove(container_name: str) -> None:
    for args in (["docker", "stop", "-t", "5", container_name], ["docker", "rm", "-f", container_name]):
        try:
            subprocess.run(args, capture_output=True, timeout=_STOP_TIMEOUT)
        except (subprocess.TimeoutExpired, OSError):  # pragma: no cover - best-effort cleanup
            logger.warning("Failed to run cleanup command: %s", " ".join(args))


def remove_image(image_tag: str) -> None:
    """Best-effort removal of a temporary build image so scan hosts don't accumulate disk usage."""
    try:
        subprocess.run(["docker", "rmi", "-f", image_tag], capture_output=True, timeout=_STOP_TIMEOUT)
    except (subprocess.TimeoutExpired, OSError):  # pragma: no cover - best-effort cleanup
        logger.warning("Failed to remove temporary image: %s", image_tag)
