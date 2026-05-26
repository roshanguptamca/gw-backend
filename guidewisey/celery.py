"""
Celery application for GuideWisey backend.
Import this module in guidewisey/__init__.py so the app is always loaded.
"""

import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "guidewisey.settings")

app = Celery("guidewisey")

# Read config from Django settings, namespace=CELERY_
app.config_from_object("django.conf:settings", namespace="CELERY")

# Auto-discover tasks in all INSTALLED_APPS
app.autodiscover_tasks()


# ── Periodic Beat Schedule ────────────────────────────────────────────────────

app.conf.beat_schedule = {
    # Dispatch due reminders every minute
    "dispatch-due-reminders": {
        "task": "future_wise.dispatch_due_reminders",
        "schedule": 60.0,  # seconds
    },
    # Expire unverified reminders every 10 minutes
    "expire-unverified-reminders": {
        "task": "future_wise.expire_unverified_reminders",
        "schedule": crontab(minute="*/10"),
    },
}

app.conf.timezone = "UTC"
