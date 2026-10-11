from __future__ import annotations

import time
import uuid

from django.core.management.base import BaseCommand, CommandError

from apps.securewise.services.worker import default_worker_id, heartbeat_worker, process_next_job, register_worker


class Command(BaseCommand):
    help = "Run queued SecureWise scans in a dedicated worker process."

    def add_arguments(self, parser):
        parser.add_argument("--poll-interval", type=float, default=2.0)
        parser.add_argument("--once", action="store_true", help="Process at most one queued scan and exit.")
        parser.add_argument("--worker-id", default="")
        parser.add_argument(
            "--check-connectivity",
            action="store_true",
            help="Register and heartbeat without claiming or executing any queued job.",
        )

    def handle(self, *args, **options):
        poll_interval = options["poll_interval"]
        if poll_interval <= 0:
            raise CommandError("--poll-interval must be greater than zero")

        check_connectivity = options["check_connectivity"]
        worker_id = options["worker_id"] or default_worker_id()
        if check_connectivity:
            worker_id = f"{worker_id[:160]}-probe-{uuid.uuid4().hex[:12]}"
        registration = register_worker(worker_id, status="offline" if check_connectivity else "online")
        capabilities = ", ".join(registration.capabilities) or "none"
        if check_connectivity:
            heartbeat_worker(worker_id, include_offline=True)
            self.stdout.write(
                self.style.SUCCESS("Database registration and heartbeat succeeded; no jobs were claimed.")
            )
            return
        self.stdout.write(self.style.SUCCESS(f"SecureWise worker {worker_id} ready; capabilities: {capabilities}"))

        while True:
            heartbeat_worker(worker_id)
            job = process_next_job(worker_id=worker_id)
            if job:
                self.stdout.write(f"Processed {job[0]} job {job[1]}")
            elif options["once"]:
                return
            else:
                time.sleep(poll_interval)
