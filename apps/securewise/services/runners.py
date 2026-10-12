"""Provider-neutral runner capability discovery and fail-closed selection."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from django.utils import timezone

from apps.securewise.models import SecureWiseScan, SecureWiseWorkerRegistration
from apps.securewise.services.worker_profile import (
    EXPERIMENTAL_LOW_RESOURCE_CAPABILITY,
    autopentest_api_worker_configured,
    experimental_low_resource_allowed,
    is_autopentest_api_worker,
    is_lightweight_worker,
    is_website_passive_worker,
    website_passive_scan_allowed,
    lightweight_scan_allowed,
)

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
_AUTOPENTEST_API_MIN_MEMORY_BYTES = 8 * 1024**3
# Oracle Always Free A1 provides 2 OCPUs (2 physical Arm cores) / 12 GB in total. One job runs at a
# time and builds are capped at 2 CPUs / 2 GB, so 2 CPUs is the approved floor; memory stays at 8 GB.
_AUTOPENTEST_API_MIN_CPUS = 2


@dataclass(frozen=True)
class RunnerCapabilities:
    runner_type: str
    architecture: str
    available_memory_bytes: int
    scanner_versions: dict[str, str]
    capabilities: tuple[str, ...]
    docker_available: bool
    scanner_availability: dict[str, str]
    isolation_capabilities: tuple[str, ...] = ()
    host_egress_proof_fresh: bool = False
    cpu_count: int = 0
    resource_tier: str = ""

    def as_dict(self) -> dict:
        return {
            "runner_type": self.runner_type,
            "architecture": self.architecture,
            "available_memory_bytes": self.available_memory_bytes,
            "scanner_versions": self.scanner_versions,
            "scanner_availability": self.scanner_availability,
            "capabilities": list(self.capabilities),
            "docker_available": self.docker_available,
            "isolation_capabilities": list(self.isolation_capabilities),
            "host_egress_proof_fresh": self.host_egress_proof_fresh,
            "cpu_count": self.cpu_count,
            "resource_tier": self.resource_tier,
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


def _cgroup_paths(controller: str) -> list[Path]:
    paths = []
    try:
        cgroup_entries = Path("/proc/self/cgroup").read_text(encoding="ascii").splitlines()
    except OSError:
        cgroup_entries = []
    for entry in cgroup_entries:
        hierarchy, separator, remainder = entry.partition(":")
        if not separator:
            continue
        controllers, separator, relative = remainder.partition(":")
        if not separator:
            continue
        components = relative.strip("/").split("/") if relative.strip("/") else []
        if any(component in {".", ".."} for component in components):
            continue
        if hierarchy == "0" and not controllers:
            paths.append(Path("/sys/fs/cgroup").joinpath(*components))
        elif controller in controllers.split(","):
            paths.append(Path("/sys/fs/cgroup", controller).joinpath(*components))
    root = Path("/sys/fs/cgroup") if controller == "cpu" else Path("/sys/fs/cgroup", controller)
    paths.append(root)
    return paths


def _available_worker_memory_bytes() -> int:
    """Use the smaller host/cgroup budget so service limits cannot be over-advertised."""
    available = _memory_bytes()
    cgroup_files = []
    for path in _cgroup_paths("memory"):
        cgroup_files.extend(
            (
                (path / "memory.max", path / "memory.current"),
                (path / "memory.limit_in_bytes", path / "memory.usage_in_bytes"),
            )
        )
    for limit_path, usage_path in cgroup_files:
        try:
            limit_text = limit_path.read_text(encoding="ascii").strip()
            if limit_text == "max":
                continue
            limit = int(limit_text)
            usage = int(usage_path.read_text(encoding="ascii").strip())
        except (OSError, ValueError):
            continue
        if 0 < limit < 2**60 and usage >= 0:
            return min(available, max(0, limit - usage))
    return available


def _available_worker_cpu_count() -> int:
    """Respect cgroup CPU quotas as well as the host's logical CPU count."""
    available = os.cpu_count() or 0
    for path in _cgroup_paths("cpu"):
        try:
            quota, period = (path / "cpu.max").read_text(encoding="ascii").split()
            if quota != "max":
                available = min(available, int(int(quota) / int(period)))
                break
        except (OSError, ValueError, ZeroDivisionError):
            try:
                quota = int((path / "cpu.cfs_quota_us").read_text(encoding="ascii").strip())
                period = int((path / "cpu.cfs_period_us").read_text(encoding="ascii").strip())
            except (OSError, ValueError, ZeroDivisionError):
                continue
            if quota > 0:
                available = min(available, int(quota / period))
                break
    return available


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
    lightweight = is_lightweight_worker()
    autopentest_api = is_autopentest_api_worker()
    website_passive = is_website_passive_worker()
    resource_tier = ""
    from apps.securewise.runtime.docker_runner import (
        API_REQUEST_RUNNER_IMAGE,
        is_docker_available,
        is_docker_image_available,
        is_docker_rootless,
    )
    from apps.securewise.services.worker import PLAYWRIGHT_RUNNER_IMAGE, WORKER_CAPABILITIES

    restricted_profile = lightweight or autopentest_api or website_passive
    scanner_availability = {}
    versions = {}
    for name, command in SCANNER_COMMANDS.items():
        if restricted_profile:
            scanner_availability[name] = "disabled"
            continue
        version = _tool_version(command[0], command)
        scanner_availability[name] = "available" if version else "unavailable"
        if version:
            versions[name] = version
    docker_available = False if lightweight or website_passive else is_docker_available()[0]
    rootless_docker = bool(autopentest_api and docker_available and is_docker_rootless())
    available_memory_bytes = _available_worker_memory_bytes()
    cpu_count = _available_worker_cpu_count()
    architecture = platform.machine().lower()
    if architecture in {"aarch64", "arm64"}:
        architecture = "arm64"
    elif architecture in {"x86_64", "amd64"}:
        architecture = "amd64"
    else:
        architecture = f"unsupported:{architecture or 'unknown'}"
    if lightweight:
        capabilities = ["sast", "sca", "secrets", "iac", "api"]
    elif website_passive:
        # Capabilities come from checks made at registration time, never from a static list.
        from apps.securewise.services.url_security import url_egress_enforced as _egress_proven

        capabilities = ["dast", "url_egress_restricted"] if _egress_proven() else []
    elif autopentest_api:
        capabilities = []
        if rootless_docker:
            capabilities.append("docker_daemon")
            # Hard prerequisites: never relaxed by the experimental mode.
            hard_ready = (
                autopentest_api_worker_configured()
                and is_docker_image_available(API_REQUEST_RUNNER_IMAGE)
                and architecture in {"amd64", "arm64"}
            )
            sized = (
                available_memory_bytes >= _AUTOPENTEST_API_MIN_MEMORY_BYTES
                and cpu_count >= _AUTOPENTEST_API_MIN_CPUS
            )
            if hard_ready and sized:
                capabilities.append("autopentest_authenticated_api")
                resource_tier = "recommended"
            elif hard_ready and experimental_low_resource_allowed():
                # Separate capability: normal sessions cannot be scheduled onto an under-sized worker.
                capabilities.append(EXPERIMENTAL_LOW_RESOURCE_CAPABILITY)
                resource_tier = "experimental"
            elif hard_ready:
                resource_tier = "insufficient"
    else:
        capabilities = list(WORKER_CAPABILITIES)
    if docker_available and not autopentest_api:
        capabilities.append("docker_daemon")
        if is_docker_image_available(PLAYWRIGHT_RUNNER_IMAGE):
            capabilities.append("playwright")
        capabilities.append("zap_baseline_docker")
    if not restricted_profile and shutil.which("zap-baseline.py"):
        capabilities.append("zap_baseline_cli")
    from apps.securewise.services.url_security import url_egress_enforced

    return RunnerCapabilities(
        runner_type=runner_type,
        architecture=architecture,
        available_memory_bytes=available_memory_bytes,
        scanner_versions=versions,
        capabilities=tuple(sorted(set(capabilities))),
        docker_available=docker_available,
        scanner_availability=scanner_availability,
        isolation_capabilities=("docker_rootless",) if rootless_docker else (),
        host_egress_proof_fresh=False if restricted_profile else url_egress_enforced(),
        cpu_count=cpu_count,
        resource_tier=resource_tier,
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
    require_local_egress_proof: bool = True,
) -> tuple[bool, str]:
    """Check a registration against a scan.

    ``require_local_egress_proof`` must stay true in a worker process, which can verify its own
    egress proof file. The control-plane API has no such file; it relies on the fresh heartbeat's
    ``url_egress_restricted`` capability, which a worker advertises only after verifying its proof.
    """
    now = now or timezone.now()
    if registration.status != "online" or registration.last_seen_at < now - max_age:
        return False, "Runner heartbeat is stale or offline."
    if registration.active_job_id:
        return False, "Runner already has an active job."
    metrics = registration.metrics if isinstance(registration.metrics, dict) else {}
    if metrics.get("worker_profile") == "lightweight" and not lightweight_scan_allowed(scan):
        return (
            False,
            "Lightweight worker only accepts repository-static scans without URL, image, or external spec targets.",
        )
    if metrics.get("worker_profile") == "website_passive" and not website_passive_scan_allowed(scan):
        return False, "Website worker only accepts authorized passive URL scans without repository or runtime work."
    capabilities = set(registration.capabilities or ())
    missing = sorted(required_capabilities(scan) - capabilities)
    if missing:
        return False, f"Runner lacks required capabilities: {', '.join(missing)}."
    architecture = metrics.get("architecture", "")
    if architecture not in {"arm64", "amd64"}:
        return False, f"Unsupported or unknown runner architecture: {architecture or 'unknown'}."
    if scan.target_url and require_local_egress_proof:
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
        supported, reason = worker_supports_scan(
            registration, scan, now=now, require_local_egress_proof=False
        )
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
                "scanner_availability": {},
            },
        )
        row["online"] += 1
        row["idle"] += not bool(registration.active_job_id)
        row["capabilities"].update(registration.capabilities or ())
        for name, version in (metrics.get("scanner_versions", {}) or {}).items():
            row["scanner_versions"].setdefault(name, set()).add(version)
        for name, status in (metrics.get("scanner_availability", {}) or {}).items():
            row["scanner_availability"].setdefault(name, set()).add(status)
    return [
        {
            **row,
            "capabilities": sorted(row["capabilities"]),
            "scanner_versions": {name: sorted(versions) for name, versions in sorted(row["scanner_versions"].items())},
            "scanner_availability": {
                name: sorted(statuses) for name, statuses in sorted(row["scanner_availability"].items())
            },
        }
        for _, row in sorted(summary.items())
    ]
