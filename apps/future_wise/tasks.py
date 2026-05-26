"""
FutureWise scheduled job functions.

These are plain Python functions — no Celery. They are registered with
APScheduler via the `runapscheduler` management command and run inside
that process on a cron/interval schedule.

To start the scheduler:
    python manage.py runapscheduler

Two periodic jobs:
    dispatch_due_reminders()      — every 60 s
    expire_unverified_reminders() — every 10 min
"""

import logging

from django.conf import settings
from django.utils import timezone

from .email_service import BrevoDeliveryError, BrevoEmailService
from .models import EmailReminder, ReminderAttachment
from .storage import AttachmentStorage, StorageError

logger = logging.getLogger(__name__)

_MAX_RETRIES = getattr(settings, "FUTUREWAVE_MAX_RETRIES", 3)
_RETRY_BASE_DELAY = getattr(settings, "FUTUREWAVE_RETRY_BASE_DELAY_SECONDS", 300)


# ── Periodic jobs ─────────────────────────────────────────────────────────────


def dispatch_due_reminders():
    """
    Called every minute by APScheduler.
    Finds SCHEDULED reminders that are due and delivers each one inline.
    """
    now = timezone.now()
    due_ids = list(
        EmailReminder.objects.filter(
            status=EmailReminder.Status.SCHEDULED,
            scheduled_at__lte=now,
            email_verified=True,
        ).values_list("id", flat=True)
    )

    dispatched = 0
    for reminder_id in due_ids:
        # Atomic transition: only proceed if still SCHEDULED
        updated = EmailReminder.objects.filter(
            id=reminder_id, status=EmailReminder.Status.SCHEDULED
        ).update(status=EmailReminder.Status.QUEUED, updated_at=timezone.now())
        if updated:
            _deliver_reminder(str(reminder_id))
            dispatched += 1

    if dispatched:
        logger.info("FutureWise: dispatched %d reminder(s)", dispatched)
    return dispatched


def expire_unverified_reminders():
    """
    Called every 10 minutes by APScheduler.
    Cancels PENDING_VERIFICATION reminders whose token has expired.
    """
    count = EmailReminder.objects.filter(
        status=EmailReminder.Status.PENDING_VERIFICATION,
        verification_token_expires_at__lt=timezone.now(),
    ).update(status=EmailReminder.Status.CANCELLED, updated_at=timezone.now())
    if count:
        logger.info("FutureWise: expired %d unverified reminder(s)", count)
    return count


# ── Delivery (inline, with retry counter in DB) ───────────────────────────────


def _deliver_reminder(reminder_id: str):
    """
    Deliver a single reminder. On failure, increments retry_count in DB.
    After _MAX_RETRIES failures, moves to DEAD_LETTER.
    The next dispatch_due_reminders() call will retry FAILED reminders
    that are still overdue (their status is reset to SCHEDULED for retry).
    """
    try:
        reminder = EmailReminder.objects.prefetch_related("attachments").get(
            id=reminder_id, status=EmailReminder.Status.QUEUED
        )
    except EmailReminder.DoesNotExist:
        logger.warning("FutureWise: reminder %s not found or not QUEUED — skipping", reminder_id)
        return

    # Fetch attachments via storage abstraction (DB or S3)
    attachment_data = []
    storage = AttachmentStorage()
    for att in reminder.attachments.all():
        try:
            content_bytes = storage.download_bytes(att.storage_key)
            attachment_data.append({
                "filename": att.original_filename,
                "content_bytes": content_bytes,
                "content_type": att.content_type,
            })
        except StorageError as exc:
            logger.error("FutureWise: attachment %s unavailable for reminder %s: %s", att.id, reminder_id, exc)

    # Send email
    try:
        service = BrevoEmailService()
        service.send_reminder_email(reminder, attachment_data or None)

        reminder.status = EmailReminder.Status.SENT
        reminder.sent_at = timezone.now()
        reminder.save(update_fields=["status", "sent_at", "updated_at"])
        logger.info("FutureWise: sent reminder %s → %s", reminder_id, reminder.email)

        # Purge attachments after delivery if configured
        if getattr(settings, "FUTUREWAVE_ATTACHMENT_PURGE_AFTER_SEND", True):
            keys = list(reminder.attachments.values_list("storage_key", flat=True))
            if keys:
                storage.delete_many(keys)

    except (BrevoDeliveryError, Exception) as exc:
        reminder.retry_count = getattr(reminder, "retry_count", 0) + 1
        reminder.last_error = str(exc)[:1000]

        if reminder.retry_count < _MAX_RETRIES:
            # Reset to SCHEDULED so dispatch loop picks it up again
            reminder.status = EmailReminder.Status.SCHEDULED
            reminder.save(update_fields=["status", "retry_count", "last_error", "updated_at"])
            logger.warning(
                "FutureWise: reminder %s will retry (attempt %d/%d): %s",
                reminder_id, reminder.retry_count, _MAX_RETRIES, exc,
            )
        else:
            reminder.status = EmailReminder.Status.DEAD_LETTER
            reminder.save(update_fields=["status", "retry_count", "last_error", "updated_at"])
            logger.error(
                "FutureWise: reminder %s dead-lettered after %d retries: %s",
                reminder_id, _MAX_RETRIES, exc,
            )

