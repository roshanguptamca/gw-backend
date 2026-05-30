import logging
import os
import sys

from django.apps import AppConfig

logger = logging.getLogger(__name__)

# Management commands that must NOT start the background scheduler
_NO_SCHEDULER_COMMANDS = frozenset({
    "migrate", "makemigrations", "collectstatic", "runapscheduler",
    "test", "shell", "createsuperuser", "check", "inspectdb",
    "showmigrations", "sqlmigrate", "dbshell",
})


class FutureWiseConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.future_wise"
    verbose_name = "FutureWise / DearTomorrow Reminders"

    def ready(self):
        # Skip scheduler for management commands that don't need it
        if len(sys.argv) >= 2 and sys.argv[1] in _NO_SCHEDULER_COMMANDS:
            return

        from django.conf import settings

        # In production the dedicated `scheduler` docker service runs
        # `python manage.py runapscheduler` — don't also start a per-worker
        # BackgroundScheduler inside every gunicorn worker.
        if not settings.DEBUG:
            return

        # Django dev runserver forks an autoreload watcher + a live worker process.
        # RUN_MAIN=true is set only in the live worker — skip the watcher fork.
        if os.environ.get("RUN_MAIN") != "true":
            return

        _start_background_scheduler()


def _start_background_scheduler():
    """Start APScheduler as a background thread (dev only)."""
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.interval import IntervalTrigger
        from django.conf import settings
        from django_apscheduler.jobstores import DjangoJobStore

        from apps.future_wise.tasks import dispatch_due_reminders, expire_unverified_reminders

        scheduler = BackgroundScheduler(timezone=getattr(settings, "TIME_ZONE", "UTC"))
        scheduler.add_jobstore(DjangoJobStore(), "default")

        scheduler.add_job(
            dispatch_due_reminders,
            trigger=IntervalTrigger(seconds=60),
            id="dispatch_due_reminders",
            name="Dispatch due FutureWise reminders",
            jobstore="default",
            replace_existing=True,
            max_instances=1,
        )

        scheduler.add_job(
            expire_unverified_reminders,
            trigger=IntervalTrigger(minutes=10),
            id="expire_unverified_reminders",
            name="Expire unverified FutureWise reminders",
            jobstore="default",
            replace_existing=True,
            max_instances=1,
        )

        scheduler.start()
        logger.info("FutureWise BackgroundScheduler started (DB-backed, no Redis)")

    except Exception as exc:
        logger.error("FutureWise scheduler failed to start: %s", exc)
