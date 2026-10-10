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
import json
import re
import shutil
import subprocess
import uuid
from pathlib import Path

from ..discovery.health import candidate_health_endpoints

logger = logging.getLogger(__name__)

_DOCKER_AVAILABILITY_TIMEOUT = 5
_BUILD_TIMEOUT = 240
_RUN_STARTUP_TIMEOUT = 5
_STOP_TIMEOUT = 15
_HEALTH_PROBE_IMAGE = "python:3.11-slim"
_HEALTH_PROBE_SCRIPT = """import sys
from urllib.error import HTTPError
from urllib.request import urlopen
try:
    response = urlopen(sys.argv[1], timeout=2)
    status = response.status
except HTTPError as error:
    status = error.code
print(status)
"""

# Conservative resource limits for auto-started scan targets.
_MEMORY_LIMIT = "512m"
_CPU_LIMIT = "1.0"

_DEFAULT_RUNTIME_TAGS = {
    "python": "3-slim",
    "node": "lts-slim",
    "go": "latest",
    "php": "cli",
    "ruby": "slim",
}


def _version_from_repo(repo_path: Path, language: str) -> str:
    """Read a runtime version from standard project metadata without executing it."""
    candidates = {
        "python": (".python-version", "runtime.txt"),
        "node": (".nvmrc", ".node-version"),
        "php": (".php-version",),
        "ruby": (".ruby-version",),
    }.get(language, ())
    for name in candidates:
        try:
            text = (repo_path / name).read_text(encoding="utf-8").strip()
        except OSError:
            continue
        match = re.search(r"\d+(?:\.\d+){0,2}", text)
        if match:
            return match.group(0)

    if language == "python":
        try:
            pyproject = (repo_path / "pyproject.toml").read_text(encoding="utf-8")
        except OSError:
            pyproject = ""
        match = re.search(r"requires-python\s*=\s*[\"']([^\"']+)", pyproject)
        if match:
            version = re.search(r"\d+\.\d+", match.group(1))
            if version:
                return version.group(0)
    elif language == "node":
        try:
            package = json.loads((repo_path / "package.json").read_text(encoding="utf-8"))
            version = package.get("engines", {}).get("node", "")
        except (OSError, ValueError, AttributeError):
            version = ""
        match = re.search(r"\d+(?:\.\d+){0,2}", str(version))
        if match:
            return match.group(0)
    elif language == "go":
        try:
            go_mod = (repo_path / "go.mod").read_text(encoding="utf-8")
        except OSError:
            go_mod = ""
        match = re.search(r"(?m)^go\s+(\d+\.\d+(?:\.\d+)?)", go_mod)
        if match:
            return match.group(1)
    elif language == "ruby":
        try:
            gemfile_lock = (repo_path / "Gemfile.lock").read_text(encoding="utf-8")
        except OSError:
            gemfile_lock = ""
        match = re.search(r"(?m)^   ruby ([\d.]+)", gemfile_lock)
        if match:
            return match.group(1)
    elif language == "php":
        try:
            composer = json.loads((repo_path / "composer.json").read_text(encoding="utf-8"))
            version = composer.get("require", {}).get("php", "")
        except (OSError, ValueError, AttributeError):
            version = ""
        match = re.search(r"\d+\.\d+(?:\.\d+)?", str(version))
        if match:
            return match.group(0)
    return ""


def _package_install_command(repo_path: Path, language: str, package_managers: tuple[str, ...]) -> str:
    managers = set(package_managers)
    if language == "python":
        if "poetry" in managers:
            return "RUN pip install --no-cache-dir poetry && poetry config virtualenvs.create false && poetry install --only main --no-interaction"
        if "pipenv" in managers:
            return "RUN pip install --no-cache-dir pipenv && pipenv install --system --deploy"
        if (repo_path / "requirements.txt").is_file():
            return "RUN pip install --no-cache-dir -r requirements.txt"
        if (repo_path / "pyproject.toml").is_file() or (repo_path / "setup.py").is_file():
            return "RUN pip install --no-cache-dir ."
    elif language == "node":
        if (repo_path / "pnpm-lock.yaml").is_file():
            return "RUN corepack enable && pnpm install --frozen-lockfile"
        if (repo_path / "yarn.lock").is_file():
            return "RUN corepack enable && yarn install --frozen-lockfile"
        if (repo_path / "package-lock.json").is_file() or (repo_path / "npm-shrinkwrap.json").is_file():
            return "RUN npm ci"
        if (repo_path / "package.json").is_file():
            return "RUN npm install"
    elif language == "go" and (repo_path / "go.mod").is_file():
        return "RUN go mod download"
    elif language == "php" and (repo_path / "composer.json").is_file():
        return (
            "COPY --from=composer:2 /usr/bin/composer /usr/bin/composer\n"
            "RUN composer install --no-dev --no-interaction --prefer-dist"
        )
    elif language == "ruby" and (repo_path / "Gemfile").is_file():
        return "RUN bundle install"
    return ""


def is_docker_cli_available() -> tuple[bool, str]:
    """Check whether the Docker CLI exists, without implying a daemon is running."""
    if not shutil.which("docker"):
        return False, "Docker CLI is not installed in this environment"
    return True, ""


def is_docker_daemon_available() -> tuple[bool, str]:
    """Check daemon reachability separately from Docker CLI availability."""
    cli_available, reason = is_docker_cli_available()
    if not cli_available:
        return False, reason

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


def is_docker_available() -> tuple[bool, str]:
    """Compatibility helper returning true only when both CLI and daemon work."""
    return is_docker_daemon_available()


def build_dockerfile_command(dockerfile_shell_command: str) -> list[str]:
    """Split a plain-text start command into a Docker CMD-friendly shell form."""
    return ["sh", "-c", dockerfile_shell_command]


def generate_dockerfile_content(
    language: str,
    start_command: str,
    port: int,
    repo_path: Path | None = None,
    package_managers: tuple[str, ...] = (),
) -> str | None:
    if language not in _DEFAULT_RUNTIME_TAGS:
        return None
    repo_path = repo_path or Path(".")
    version = _version_from_repo(repo_path, language)
    runtime_tag = version or _DEFAULT_RUNTIME_TAGS[language]
    base_image = {
        "python": f"python:{runtime_tag}-slim",
        "node": f"node:{runtime_tag}" if runtime_tag.endswith("-slim") else f"node:{runtime_tag}-slim",
        "go": f"golang:{runtime_tag}",
        "php": f"php:{runtime_tag}",
        "ruby": f"ruby:{runtime_tag}-slim",
    }[language]
    install_command = _package_install_command(repo_path, language, package_managers)
    command = f'CMD {json.dumps(["sh", "-c", start_command])}' if start_command else ""
    lines = [f"FROM {base_image}", "WORKDIR /app", "COPY . /app"]
    if install_command:
        lines.extend(install_command.splitlines())
    lines.extend((f"EXPOSE {port}", command))
    return "\n".join(line for line in lines if line) + "\n"


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


def create_isolated_network(network_name: str) -> tuple[bool, str]:
    try:
        proc = subprocess.run(
            ["docker", "network", "create", "--internal", network_name],
            capture_output=True,
            timeout=_DOCKER_AVAILABILITY_TIMEOUT,
            text=True,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return False, f"Docker network creation failed: {exc}"
    if proc.returncode != 0:
        return False, (proc.stderr or proc.stdout or "Docker network creation failed").strip()[-2000:]
    return True, ""


def probe_network_url(network_name: str, url: str) -> int | None:
    """Probe an isolated runtime from its Docker network, not from the host."""
    try:
        proc = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--memory",
                "64m",
                "--cpus",
                "0.25",
                "--pids-limit",
                "16",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges",
                "--network",
                network_name,
                "--entrypoint",
                "python",
                _HEALTH_PROBE_IMAGE,
                "-c",
                _HEALTH_PROBE_SCRIPT,
                url,
            ],
            capture_output=True,
            timeout=10,
            text=True,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None

    if proc.returncode != 0:
        return None
    try:
        return int(proc.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return None


def probe_health(network_name: str, base_url: str, preferred_endpoint: str = "") -> dict:
    """Check discovered health endpoints from a temporary container on the isolated network."""
    base = base_url.rstrip("/")
    root_status = None
    for path in candidate_health_endpoints(preferred_endpoint):
        url = base + path if path != "/" else base + "/"
        status = probe_network_url(network_name, url)
        if path == "/":
            root_status = status
        elif status in (200, 204):
            return {
                "reachable": True,
                "selected_endpoint": path,
                "has_dedicated_health_endpoint": True,
                "status_code": status,
            }

    if root_status is not None and (200 <= root_status < 400 or root_status in (401, 403)):
        return {
            "reachable": True,
            "selected_endpoint": "/",
            "has_dedicated_health_endpoint": False,
            "status_code": root_status,
        }
    return {
        "reachable": False,
        "selected_endpoint": "",
        "has_dedicated_health_endpoint": False,
        "status_code": root_status,
    }


def run_container(
    image: str,
    host_port: int,
    container_port: int,
    env_vars: dict[str, str] | None = None,
    network_name: str = "",
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
        "--pids-limit",
        "128",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--read-only",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=64m",
        "-p",
        f"127.0.0.1:{host_port}:{container_port}",
    ]
    if network_name:
        cmd.extend(["--network", network_name, "--network-alias", container_name])
    else:
        cmd.extend(["--network", "bridge"])
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


def remove_network(network_name: str) -> None:
    try:
        subprocess.run(["docker", "network", "rm", network_name], capture_output=True, timeout=_STOP_TIMEOUT)
    except (subprocess.TimeoutExpired, OSError):  # pragma: no cover - best-effort cleanup
        logger.warning("Failed to remove temporary Docker network: %s", network_name)


def remove_image(image_tag: str) -> None:
    """Best-effort removal of a temporary build image so scan hosts don't accumulate disk usage."""
    try:
        subprocess.run(["docker", "rmi", "-f", image_tag], capture_output=True, timeout=_STOP_TIMEOUT)
    except (subprocess.TimeoutExpired, OSError):  # pragma: no cover - best-effort cleanup
        logger.warning("Failed to remove temporary image: %s", image_tag)
