"""
Management command: python manage.py runapscheduler

Starts APScheduler with the Django ORM job store — no Redis or Celery needed.
Runs until interrupted (Ctrl-C).

Jobs:
  dispatch_due_reminders        — every 60 seconds
  expire_unverified_reminders   — every 10 minutes
  cleanup_unverified_reminders  — every hour
"""

import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger
from django.conf import settings
from django.core.management.base import BaseCommand
from django_apscheduler.jobstores import DjangoJobStore
from django_apscheduler.models import DjangoJobExecution

from apps.future_wise.tasks import cleanup_unverified_reminders, dispatch_due_reminders, expire_unverified_reminders

logger = logging.getLogger(__name__)


def delete_old_job_executions(max_age: int = 604_800):
    """Prune job execution records older than max_age seconds (default: 7 days)."""
    DjangoJobExecution.objects.delete_old_job_executions(max_age)


class Command(BaseCommand):
    help = "Start APScheduler for FutureWise background jobs (no Redis required)"

    def handle(self, *args, **options):
        scheduler = BlockingScheduler(timezone=getattr(settings, "TIME_ZONE", "UTC"))
        scheduler.add_jobstore(DjangoJobStore(), "default")

        # Dispatch due reminders every minute
        scheduler.add_job(
            dispatch_due_reminders,
            trigger=IntervalTrigger(seconds=60),
            id="dispatch_due_reminders",
            name="Dispatch due FutureWise reminders",
            jobstore="default",
            replace_existing=True,
        )

        # Expire unverified reminders every 10 minutes
        scheduler.add_job(
            expire_unverified_reminders,
            trigger=IntervalTrigger(minutes=10),
            id="expire_unverified_reminders",
            name="Expire unverified FutureWise reminders",
            jobstore="default",
            replace_existing=True,
        )

        # Delete anonymous unverified reminders older than EMAIL_VERIFICATION_EXPIRY_HOURS
        scheduler.add_job(
            cleanup_unverified_reminders,
            trigger=IntervalTrigger(hours=1),
            id="cleanup_unverified_reminders",
            name="Clean up old anonymous unverified FutureWise reminders",
            jobstore="default",
            replace_existing=True,
        )

        # Weekly cleanup of old job execution records
        scheduler.add_job(
            delete_old_job_executions,
            trigger=IntervalTrigger(weeks=1),
            id="delete_old_job_executions",
            name="Prune old APScheduler job executions",
            jobstore="default",
            replace_existing=True,
        )

        self.stdout.write(self.style.SUCCESS("✅ FutureWise scheduler starting (DB-backed, no Redis)"))
        self.stdout.write("   Jobs registered:")
        self.stdout.write("   • dispatch_due_reminders          — every 60 s")
        self.stdout.write("   • expire_unverified_reminders     — every 10 min")
        self.stdout.write("   • cleanup_unverified_reminders    — every hour")
        self.stdout.write("   Press Ctrl-C to stop.\n")

        try:
            scheduler.start()
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("Scheduler stopped."))
            scheduler.shutdown()
