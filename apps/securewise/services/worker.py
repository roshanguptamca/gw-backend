from __future__ import annotations

import os
import shutil
import socket
import uuid
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from apps.securewise.models import PentestSession, SecureWiseScan, SecureWiseWorkerRegistration

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
)
STALE_CLAIM_AFTER = timedelta(minutes=30)


def register_worker(worker_id: str) -> SecureWiseWorkerRegistration:
    from apps.securewise.runtime.docker_runner import is_docker_available

    capabilities = list(WORKER_CAPABILITIES)
    capabilities.extend(tool for tool in ("semgrep", "trivy", "gitleaks") if shutil.which(tool))
    if is_docker_available()[0]:
        capabilities.append("docker_daemon")
    registration, _ = SecureWiseWorkerRegistration.objects.update_or_create(
        worker_id=worker_id,
        defaults={"capabilities": capabilities, "status": "online", "last_seen_at": timezone.now()},
    )
    return registration


def default_worker_id() -> str:
    return f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:8]}"


def claim_next_scan() -> str | None:
    """Claim one queued scan with a compare-and-set update safe for concurrent workers."""
    now = timezone.now()
    stale_before = now - STALE_CLAIM_AFTER
    candidate = (
        SecureWiseScan.objects.filter(Q(status="queued") | Q(status="worker_claimed", worker_claimed_at__lt=stale_before))
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


def claim_next_job() -> tuple[str, str] | None:
    """Claim the oldest queued scan or AutoPentest session."""
    now = timezone.now()
    stale_before = now - STALE_CLAIM_AFTER
    candidates = []
    for job_type, model in (("scan", SecureWiseScan), ("pentest", PentestSession)):
        candidate = (
            model.objects.filter(
                Q(status="queued") | Q(status="worker_claimed", worker_claimed_at__lt=stale_before)
            )
            .order_by("created_at")
            .values_list("id", "status", "created_at")
            .first()
        )
        if candidate:
            candidates.append((candidate[2], job_type, candidate[0], candidate[1]))
    if not candidates:
        return None

    _, job_type, job_id, old_status = min(candidates)
    model = SecureWiseScan if job_type == "scan" else PentestSession
    claim_filter = Q(status="queued")
    if old_status == "worker_claimed":
        claim_filter = Q(status="worker_claimed", worker_claimed_at__lt=stale_before)
    claimed = model.objects.filter(Q(id=job_id) & claim_filter).update(status="worker_claimed", worker_claimed_at=now)
    return (job_type, str(job_id)) if claimed == 1 else None


def process_next_job() -> tuple[str, str] | None:
    claimed = claim_next_job()
    if claimed is None:
        return None
    job_type, job_id = claimed
    if job_type == "scan":
        from apps.securewise.services.scanner import ScannerRunner

        ScannerRunner().run_scan(job_id)
    else:
        from apps.securewise.services.autopentest import PentestRunner

        PentestRunner().run_session(job_id)
    return claimed
