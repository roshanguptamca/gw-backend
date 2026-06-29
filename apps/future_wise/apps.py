import logging
import os
import sys

from django.apps import AppConfig

logger = logging.getLogger(__name__)


def _enable_sqlite_wal(sender, connection, **kwargs):
    """Switch SQLite to WAL journal mode on every new connection.

    WAL (Write-Ahead Logging) allows readers and writers to proceed
    concurrently, which eliminates most "database is locked" errors when
    APScheduler's background thread and Django's request threads hit the DB
    at the same time.
    """
    if connection.vendor == "sqlite":
        connection.cursor().execute("PRAGMA journal_mode=WAL;")
        connection.cursor().execute("PRAGMA synchronous=NORMAL;")
        connection.cursor().execute("PRAGMA busy_timeout=20000;")


# Management commands that must NOT start the background scheduler
_NO_SCHEDULER_COMMANDS = frozenset(
    {
        "migrate",
        "makemigrations",
        "collectstatic",
        "runapscheduler",
        "test",
        "shell",
        "createsuperuser",
        "check",
        "inspectdb",
        "showmigrations",
        "sqlmigrate",
        "dbshell",
        "translate_questions_nl",
        "seed_nl_questions",
        "seed_driving_theory",
        "seed_v3_questions",
        "seed_nl_driving_content",
    }
)

# Process-level guard — ensures the scheduler starts exactly once per process
# even if AppConfig.ready() is somehow called more than once.
_scheduler_started = False


class FutureWiseConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.future_wise"
    verbose_name = "FutureWise / DearTomorrow Reminders"

    def ready(self):
        global _scheduler_started

        # Enable WAL mode for every new SQLite connection (dev + test).
        from django.db.backends.signals import connection_created

        connection_created.connect(_enable_sqlite_wal)

        # Never start inside management commands that don't need it
        if len(sys.argv) >= 2 and sys.argv[1] in _NO_SCHEDULER_COMMANDS:
            return

        # Guard: only start once per process
        if _scheduler_started:
            return
        _scheduler_started = True

        _start_background_scheduler()


def _start_background_scheduler():
    """Start APScheduler as a background thread."""
    try:
        from django.conf import settings

        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.interval import IntervalTrigger

        from apps.future_wise.tasks import dispatch_due_reminders, expire_unverified_reminders

        scheduler = BackgroundScheduler(timezone=getattr(settings, "TIME_ZONE", "UTC"))

        # In development use an in-memory job store to avoid APScheduler
        # hammering SQLite with job-state writes on every tick, which is the
        # primary cause of "database is locked" errors in dev.
        if getattr(settings, "IS_DEVELOPMENT", True):
            from apscheduler.jobstores.memory import MemoryJobStore

            scheduler.add_jobstore(MemoryJobStore(), "default")
        else:
            from django_apscheduler.jobstores import DjangoJobStore

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

        # Self-ping to prevent Render free tier from spinning down.
        # RENDER_EXTERNAL_URL is injected automatically by Render — only active in production.
        render_url = os.environ.get("RENDER_EXTERNAL_URL")
        if render_url:
            scheduler.add_job(
                _ping_self,
                trigger=IntervalTrigger(minutes=10),
                id="keep_alive_ping",
                name="Keep-alive ping (Render free tier)",
                jobstore="default",
                replace_existing=True,
                max_instances=1,
                args=[render_url],
            )
            logger.info("FutureWise: keep-alive ping enabled → %s", render_url)

        scheduler.start()
        logger.info("FutureWise BackgroundScheduler started (DB-backed, no Redis)")

    except Exception as exc:
        logger.error("FutureWise scheduler failed to start: %s", exc)


def _ping_self(base_url: str) -> None:
    """
    Ping the service's own health endpoint every 10 min to prevent
    Render free tier from spinning down the container.
    """
    import urllib.request

    url = base_url.rstrip("/") + "/api/accounts/session/"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            logger.info("Keep-alive ping → %s (%d)", url, resp.status)
    except Exception as exc:
        logger.warning("Keep-alive ping failed → %s : %s", url, exc)
