"""
Management command: cleanup_unverified_reminders

Deletes anonymous PENDING_VERIFICATION reminders that are older than
EMAIL_VERIFICATION_EXPIRY_HOURS (default: 24 h).

Usage:
    python manage.py cleanup_unverified_reminders

Safe to run repeatedly; add to a cron or APScheduler job for automation.
"""

from django.core.management.base import BaseCommand

from apps.future_wise.tasks import cleanup_unverified_reminders


class Command(BaseCommand):
    help = (
        "Delete anonymous PENDING_VERIFICATION reminders older than "
        "EMAIL_VERIFICATION_EXPIRY_HOURS hours."
    )

    def handle(self, *args, **options):
        count = cleanup_unverified_reminders()
        if count:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Deleted {count} expired anonymous unverified reminder(s)."
                )
            )
        else:
            self.stdout.write("No expired anonymous unverified reminders found.")
