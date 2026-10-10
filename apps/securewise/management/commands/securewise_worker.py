from __future__ import annotations

import time

from django.core.management.base import BaseCommand, CommandError

from apps.securewise.services.worker import default_worker_id, heartbeat_worker, process_next_job, register_worker


class Command(BaseCommand):
    help = "Run queued SecureWise scans in a dedicated worker process."

    def add_arguments(self, parser):
        parser.add_argument("--poll-interval", type=float, default=2.0)
        parser.add_argument("--once", action="store_true", help="Process at most one queued scan and exit.")
        parser.add_argument("--worker-id", default="")

    def handle(self, *args, **options):
        poll_interval = options["poll_interval"]
        if poll_interval <= 0:
            raise CommandError("--poll-interval must be greater than zero")

        worker_id = options["worker_id"] or default_worker_id()
        registration = register_worker(worker_id)
        capabilities = ", ".join(registration.capabilities) or "none"
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
