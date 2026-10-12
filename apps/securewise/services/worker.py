from __future__ import annotations

import os
import secrets
import shutil
import socket
import tempfile
import threading
import uuid
from datetime import timedelta
from pathlib import Path

from django.db import close_old_connections
from django.db.models import Q
from django.utils import timezone

from apps.securewise.models import (
    PentestSession,
    SecureWiseScan,
    SecureWiseWorkerRegistration,
    securewise_encryption_key_fingerprint,
)
from apps.securewise.services.worker_profile import (
    LIGHTWEIGHT_CAPABILITIES,
    LIGHTWEIGHT_SCAN_TYPES,
    is_lightweight_worker,
)

WORKER_CAPABILITIES = (
    "sast",
    "sca",
    "secrets",
    "iac",
    "api",
    "dast",
    "container",
    "docker_runtime",
    "autopentest_openapi_contract",
    "autopentest_authenticated_api",
)
STALE_CLAIM_AFTER = timedelta(minutes=30)
WORKER_HEARTBEAT_SECONDS = 15
PLAYWRIGHT_RUNNER_IMAGE = "securewise-playwright:1.57.0"
_SCAN_ACTIVE_STATUSES = (
    "worker_claimed",
    "running",
    "cloning",
    "running_sast",
    "running_sca",
    "running_secrets",
    "running_iac",
    "running_container",
    "running_api",
    "running_dast",
    "normalizing",
)


def register_worker(worker_id: str, *, status: str = "online") -> SecureWiseWorkerRegistration:
    from .runners import discover_runner_capabilities
    from .url_security import url_egress_enforced

    runner_type = os.environ.get("SECUREWISE_RUNNER_TYPE", "linux_worker")
    if runner_type not in {"local", "linux_worker", "github_actions"}:
        runner_type = "linux_worker"
    discovered = discover_runner_capabilities(runner_type=runner_type)
    capabilities = list(discovered.capabilities)
    if is_lightweight_worker():
        capabilities = list(LIGHTWEIGHT_CAPABILITIES)
    if not is_lightweight_worker() and url_egress_enforced():
        capabilities.append("url_egress_restricted")
    metrics = worker_resource_metrics()
    metrics.update(discovered.as_dict())
    metrics["encryption_key_fingerprint"] = securewise_encryption_key_fingerprint()
    metrics["provider"] = os.environ.get("SECUREWISE_RUNNER_PROVIDER", "self_hosted")[:40]
    metrics["worker_profile"] = "lightweight" if is_lightweight_worker() else "standard"
    registration, _ = SecureWiseWorkerRegistration.objects.update_or_create(
        worker_id=worker_id,
        defaults={
            "capabilities": capabilities,
            "metrics": metrics,
            "status": status,
            "last_seen_at": timezone.now(),
        },
    )
    return registration


def worker_resource_metrics() -> dict:
    """Collect best-effort host metrics without requiring an additional dependency."""
    metrics = {}
    try:
        for line in Path("/proc/self/status").read_text(encoding="utf-8").splitlines():
            if line.startswith(("VmRSS:", "VmHWM:")):
                name, value, *_ = line.split()
                metrics[name.rstrip(":").lower() + "_kb"] = int(value)
    except OSError:
        pass
    try:
        disk = shutil.disk_usage(tempfile.gettempdir())
        metrics["temp_disk_free_bytes"] = disk.free
        metrics["temp_disk_total_bytes"] = disk.total
    except OSError:
        pass
    try:
        metrics["load_average_1m"] = round(os.getloadavg()[0], 2)
    except (AttributeError, OSError):
        pass
    return metrics


def heartbeat_worker(worker_id: str, *, include_offline: bool = False) -> None:
    statuses = ("online", "offline") if include_offline else ("online",)
    registration = SecureWiseWorkerRegistration.objects.filter(
        worker_id=worker_id,
        status__in=statuses,
    ).first()
    if registration is None:
        return
    metrics = registration.metrics if isinstance(registration.metrics, dict) else {}
    registration.last_seen_at = timezone.now()
    registration.metrics = {**metrics, **worker_resource_metrics()}
    registration.save(update_fields=["last_seen_at", "metrics"])


def default_worker_id() -> str:
    return f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:8]}"


def claim_next_scan() -> str | None:
    """Claim one queued scan with a compare-and-set update safe for concurrent workers."""
    now = timezone.now()
    stale_before = now - STALE_CLAIM_AFTER
    candidate = (
        SecureWiseScan.objects.filter(target_url="")
        .filter(Q(status="queued") | Q(status="worker_claimed", worker_claimed_at__lt=stale_before))
        .order_by("created_at")
        .values_list("id", "status")
        .first()
    )
    if candidate is None:
        return None

    scan_id, old_status = candidate
    claim_filter = Q(status="queued")
    if old_status == "worker_claimed":
        claim_filter = Q(status="worker_claimed", worker_claimed_at__lt=stale_before)
    claimed = SecureWiseScan.objects.filter(Q(id=scan_id) & claim_filter).update(
        status="worker_claimed",
        worker_claimed_at=now,
    )
    return str(scan_id) if claimed == 1 else None


def process_next_scan() -> str | None:
    scan_id = claim_next_scan()
    if scan_id is None:
        return None

    from apps.securewise.services.scanner import ScannerRunner

    ScannerRunner().run_scan(scan_id)
    return scan_id


def _worker_can_run_url_scan(worker_id: str) -> bool:
    if not worker_id:
        return False
    from .url_security import url_egress_enforced

    if not url_egress_enforced():
        return False
    registration = SecureWiseWorkerRegistration.objects.filter(
        worker_id=worker_id,
        status="online",
        last_seen_at__gte=timezone.now() - timedelta(seconds=45),
    ).first()
    return bool(registration and "url_egress_restricted" in (registration.capabilities or []))


def _worker_supports_pentest(registration: SecureWiseWorkerRegistration, session: PentestSession) -> bool:
    capabilities = set(registration.capabilities or ())
    if session.mode != "passive":
        metrics = registration.metrics if isinstance(registration.metrics, dict) else {}
        reported_fingerprint = metrics.get("encryption_key_fingerprint")
        if (
            not isinstance(reported_fingerprint, str)
            or len(reported_fingerprint) != 64
            or not reported_fingerprint.isascii()
            or not secrets.compare_digest(
                reported_fingerprint,
                securewise_encryption_key_fingerprint(),
            )
        ):
            return False
    if session.mode == "approved_tests":
        config = session.get_auth_config()
        if config.get("type") != "planner":
            return False
        execution_mode = config.get("execution_mode")
        if execution_mode == "authenticated_api":
            required = {"autopentest_authenticated_api", "docker_daemon"}
        elif execution_mode == "authenticated_browser":
            required = {"playwright", "docker_daemon"}
        else:
            return False
    elif session.mode == "authenticated_api":
        required = {"autopentest_authenticated_api", "docker_daemon"}
    elif session.mode == "authenticated_browser":
        required = {"playwright", "docker_daemon"}
    elif session.mode in {"passive", "security_planning"}:
        required = {"autopentest_openapi_contract"}
    else:
        return False
    return required.issubset(capabilities)


def claim_next_job(worker_id: str = "") -> tuple[str, str] | None:
    """Claim the oldest queued scan or AutoPentest session."""
    now = timezone.now()
    stale_before = now - STALE_CLAIM_AFTER
    registration = None
    if worker_id:
        registration = SecureWiseWorkerRegistration.objects.filter(worker_id=worker_id, status="online").first()
        if registration is None or registration.last_seen_at < now - timedelta(seconds=45):
            return None
        if registration.active_job_id:
            if registration.active_job_started_at and registration.active_job_started_at < stale_before:
                SecureWiseWorkerRegistration.objects.filter(
                    worker_id=worker_id,
                    active_job_id=registration.active_job_id,
                    active_job_started_at=registration.active_job_started_at,
                ).update(active_job_id="", active_job_type="", active_job_started_at=None)
                registration.refresh_from_db()
            if registration.active_job_id:
                return None

    candidates = []
    for job_type, model in (("scan", SecureWiseScan), ("pentest", PentestSession)):
        if is_lightweight_worker() and job_type == "pentest":
            continue
        eligible = model.objects.filter(
            Q(status="queued")
            | (
                Q(status__in=_SCAN_ACTIVE_STATUSES if job_type == "scan" else ("worker_claimed", "running"))
                & Q(worker_claimed_at__lt=stale_before)
            )
        )
        if job_type == "scan" and not _worker_can_run_url_scan(worker_id):
            eligible = eligible.filter(target_url="")
        if is_lightweight_worker() and job_type == "scan":
            eligible = eligible.filter(
                scan_type__in=tuple(sorted(LIGHTWEIGHT_SCAN_TYPES)),
                target_url="",
                docker_image="",
                api_spec_url="",
            )
        for candidate in eligible.order_by("created_at").values_list("id", "status", "created_at")[:50]:
            if worker_id and job_type == "scan":
                from apps.securewise.services.runners import worker_supports_scan

                scan = SecureWiseScan.objects.get(id=candidate[0])
                supported, _ = worker_supports_scan(registration, scan, now=now)
                if not supported:
                    continue
            elif worker_id and job_type == "pentest":
                session = PentestSession.objects.get(id=candidate[0])
                if not _worker_supports_pentest(registration, session):
                    continue
            candidates.append((candidate[2], job_type, candidate[0], candidate[1]))
            break
    if not candidates:
        return None

    _, job_type, job_id, old_status = min(candidates)
    model = SecureWiseScan if job_type == "scan" else PentestSession
    if registration:
        reserved = SecureWiseWorkerRegistration.objects.filter(worker_id=worker_id, active_job_id="").update(
            active_job_id=str(job_id),
            active_job_type=job_type,
            active_job_started_at=now,
        )
        if reserved != 1:
            return None
    claim_filter = Q(status="queued")
    if old_status != "queued":
        active_statuses = _SCAN_ACTIVE_STATUSES if job_type == "scan" else ("worker_claimed", "running")
        claim_filter = Q(status=old_status, status__in=active_statuses, worker_claimed_at__lt=stale_before)
    claimed = model.objects.filter(Q(id=job_id) & claim_filter).update(status="worker_claimed", worker_claimed_at=now)
    if claimed != 1 and registration:
        release_worker_job(worker_id, str(job_id))
    return (job_type, str(job_id)) if claimed == 1 else None


def release_worker_job(worker_id: str, job_id: str) -> None:
    SecureWiseWorkerRegistration.objects.filter(worker_id=worker_id, active_job_id=job_id).update(
        active_job_id="",
        active_job_type="",
        active_job_started_at=None,
    )


def process_next_job(worker_id: str = "") -> tuple[str, str] | None:
    claimed = claim_next_job(worker_id)
    if claimed is None:
        return None
    job_type, job_id = claimed
    stop_heartbeat = threading.Event()
    heartbeat = threading.Thread(
        target=_refresh_job_lease,
        args=(stop_heartbeat, job_type, job_id, worker_id),
        daemon=True,
    )
    heartbeat.start()
    try:
        if job_type == "scan":
            from apps.securewise.services.scanner import ScannerRunner

            ScannerRunner().run_scan(job_id, worker_id=worker_id)
        else:
            from apps.securewise.services.autopentest import PentestRunner

            PentestRunner().run_session(job_id)
        return claimed
    finally:
        stop_heartbeat.set()
        heartbeat.join(timeout=WORKER_HEARTBEAT_SECONDS + 1)
        if worker_id:
            release_worker_job(worker_id, job_id)


def _refresh_job_lease(stop: threading.Event, job_type: str, job_id: str, worker_id: str) -> None:
    model = SecureWiseScan if job_type == "scan" else PentestSession
    active_statuses = _SCAN_ACTIVE_STATUSES if job_type == "scan" else ("worker_claimed", "running")
    while not stop.wait(WORKER_HEARTBEAT_SECONDS):
        close_old_connections()
        now = timezone.now()
        model.objects.filter(id=job_id, status__in=active_statuses).update(worker_claimed_at=now)
        if worker_id:
            SecureWiseWorkerRegistration.objects.filter(worker_id=worker_id, active_job_id=job_id).update(
                last_seen_at=now,
                active_job_started_at=now,
            )
