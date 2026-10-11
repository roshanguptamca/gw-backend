"""Provider-neutral runner capability discovery and fail-closed selection."""

from __future__ import annotations

import platform
import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import timedelta

from django.utils import timezone

from apps.securewise.models import SecureWiseScan, SecureWiseWorkerRegistration

ENGINE_CAPABILITIES = {
    "sast": "sast",
    "sca": "sca",
    "secrets": "secrets",
    "iac": "iac",
    "container": "container",
    "dast": "dast",
    "api": "api",
}

SCANNER_COMMANDS = {
    "semgrep": ("semgrep", "--version"),
    "trivy": ("trivy", "--version"),
    "gitleaks": ("gitleaks", "version"),
    "zap": ("zap-baseline.py", "-version"),
}


@dataclass(frozen=True)
class RunnerCapabilities:
    runner_type: str
    architecture: str
    available_memory_bytes: int
    scanner_versions: dict[str, str]
    capabilities: tuple[str, ...]
    docker_available: bool
    isolation_capabilities: tuple[str, ...] = ()
    host_egress_proof_fresh: bool = False

    def as_dict(self) -> dict:
        return {
            "runner_type": self.runner_type,
            "architecture": self.architecture,
            "available_memory_bytes": self.available_memory_bytes,
            "scanner_versions": self.scanner_versions,
            "capabilities": list(self.capabilities),
            "docker_available": self.docker_available,
            "isolation_capabilities": list(self.isolation_capabilities),
            "host_egress_proof_fresh": self.host_egress_proof_fresh,
        }


@dataclass(frozen=True)
class RunnerSelection:
    worker_id: str | None
    blocked_reason: str

    @property
    def available(self) -> bool:
        return self.worker_id is not None


def _memory_bytes() -> int:
    try:
        pages = int(os.sysconf("SC_AVPHYS_PAGES"))
        page_size = int(os.sysconf("SC_PAGE_SIZE"))
        return pages * page_size
    except (OSError, ValueError, AttributeError):
        try:
            return int(os.sysconf("SC_PHYS_PAGES")) * int(os.sysconf("SC_PAGE_SIZE"))
        except (OSError, ValueError, AttributeError):
            return 0


def _tool_version(executable: str, arguments: tuple[str, ...]) -> str:
    path = shutil.which(executable)
    if not path:
        return ""
    try:
        result = subprocess.run(
            [path, *arguments[1:]],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    output = (result.stdout or result.stderr).strip()
    return output.splitlines()[0][:120] if result.returncode == 0 and output else ""


def discover_runner_capabilities(*, runner_type: str = "linux_worker") -> RunnerCapabilities:
    """Inspect installed tools and host properties without assuming a cloud provider."""
    from apps.securewise.runtime.docker_runner import is_docker_available, is_docker_image_available
    from apps.securewise.services.worker import PLAYWRIGHT_RUNNER_IMAGE, WORKER_CAPABILITIES

    versions = {
        name: version for name, command in SCANNER_COMMANDS.items() if (version := _tool_version(command[0], command))
    }
    docker_available = is_docker_available()[0]
    capabilities = list(WORKER_CAPABILITIES)
    if docker_available:
        capabilities.append("docker_daemon")
        if is_docker_image_available(PLAYWRIGHT_RUNNER_IMAGE):
            capabilities.append("playwright")
        capabilities.append("zap_baseline_docker")
    if shutil.which("zap-baseline.py"):
        capabilities.append("zap_baseline_cli")
    architecture = platform.machine().lower()
    if architecture in {"aarch64", "arm64"}:
        architecture = "arm64"
    elif architecture in {"x86_64", "amd64"}:
        architecture = "amd64"
    else:
        architecture = f"unsupported:{architecture or 'unknown'}"
    from apps.securewise.services.url_security import url_egress_enforced

    return RunnerCapabilities(
        runner_type=runner_type,
        architecture=architecture,
        available_memory_bytes=_memory_bytes(),
        scanner_versions=versions,
        capabilities=tuple(sorted(set(capabilities))),
        docker_available=docker_available,
        host_egress_proof_fresh=url_egress_enforced(),
    )


def required_capabilities(scan: SecureWiseScan) -> set[str]:
    scan_type = scan.scan_type
    required = {ENGINE_CAPABILITIES[scan_type]} if scan_type in ENGINE_CAPABILITIES else set()
    if scan_type == "full":
        required.update(("sast", "sca", "secrets", "iac"))
        if scan.target_url:
            required.add("dast")
        if scan.docker_image:
            required.update(("container", "docker_daemon"))
    if scan.target_url:
        required.update(("dast", "url_egress_restricted"))
    if scan_type == "container" and scan.docker_image:
        required.add("docker_daemon")
    return required


def worker_supports_scan(
    registration: SecureWiseWorkerRegistration,
    scan: SecureWiseScan,
    *,
    now=None,
    max_age: timedelta = timedelta(seconds=45),
) -> tuple[bool, str]:
    now = now or timezone.now()
    if registration.status != "online" or registration.last_seen_at < now - max_age:
        return False, "Runner heartbeat is stale or offline."
    if registration.active_job_id:
        return False, "Runner already has an active job."
    capabilities = set(registration.capabilities or ())
    missing = sorted(required_capabilities(scan) - capabilities)
    if missing:
        return False, f"Runner lacks required capabilities: {', '.join(missing)}."
    metrics = registration.metrics if isinstance(registration.metrics, dict) else {}
    architecture = metrics.get("architecture", "")
    if architecture not in {"arm64", "amd64"}:
        return False, f"Unsupported or unknown runner architecture: {architecture or 'unknown'}."
    if scan.target_url:
        from apps.securewise.services.url_security import url_egress_enforced

        if not url_egress_enforced():
            return False, "URL scan blocked: host egress verification is unavailable."
    return True, ""


def select_runner(scan: SecureWiseScan, *, now=None) -> RunnerSelection:
    """Select only a fresh, idle runner with every capability this job requires."""
    now = now or timezone.now()
    registrations = SecureWiseWorkerRegistration.objects.filter(
        status="online",
        last_seen_at__gte=now - timedelta(seconds=45),
        active_job_id="",
    ).order_by("worker_id")
    rejected: list[str] = []
    for registration in registrations:
        supported, reason = worker_supports_scan(registration, scan, now=now)
        if supported:
            return RunnerSelection(registration.worker_id, "")
        rejected.append(reason)
    reason = "; ".join(dict.fromkeys(rejected))
    if not reason:
        reason = "No online idle runner is registered."
    return RunnerSelection(None, reason)


def runner_fleet_summary(*, now=None) -> list[dict]:
    """Return aggregate readiness without disclosing worker IDs or hostnames."""
    now = now or timezone.now()
    registrations = SecureWiseWorkerRegistration.objects.filter(
        status="online",
        last_seen_at__gte=now - timedelta(seconds=45),
    )
    summary: dict[tuple[str, str], dict] = {}
    for registration in registrations:
        metrics = registration.metrics if isinstance(registration.metrics, dict) else {}
        runner_type = metrics.get("runner_type", "linux_worker")
        architecture = metrics.get("architecture", "unknown")
        key = (runner_type, architecture)
        row = summary.setdefault(
            key,
            {
                "runner_type": runner_type,
                "architecture": architecture,
                "online": 0,
                "idle": 0,
                "capabilities": set(),
                "scanner_versions": {},
            },
        )
        row["online"] += 1
        row["idle"] += not bool(registration.active_job_id)
        row["capabilities"].update(registration.capabilities or ())
        for name, version in (metrics.get("scanner_versions", {}) or {}).items():
            row["scanner_versions"].setdefault(name, set()).add(version)
    return [
        {
            **row,
            "capabilities": sorted(row["capabilities"]),
            "scanner_versions": {name: sorted(versions) for name, versions in sorted(row["scanner_versions"].items())},
        }
        for _, row in sorted(summary.items())
    ]
