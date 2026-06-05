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
    cleanup_unverified_reminders() — every hour
"""

import logging

from django.conf import settings
from django.utils import timezone

from .dispatcher import ReminderDispatcher
from .models import EmailReminder
from .storage import AttachmentStorage, StorageError

logger = logging.getLogger(__name__)

_MAX_RETRIES = getattr(settings, "FUTUREWAVE_MAX_RETRIES", 3)
_RETRY_BASE_DELAY = getattr(settings, "FUTUREWAVE_RETRY_BASE_DELAY_SECONDS", 300)

# Thread-local attachment store: tasks.py loads attachments then passes them
# to the EmailReminderProvider via this dict keyed by reminder_id (str).
# This avoids changing the IReminderProvider.send() signature.
_attachment_context: dict = {}


# ── Periodic jobs ─────────────────────────────────────────────────────────────


def dispatch_due_reminders():
    """
    Called every minute by APScheduler.
    Finds SCHEDULED reminders that are due and delivers each one inline.
    Also recovers reminders stuck in QUEUED (e.g. from a previous crashed delivery).
    """
    now = timezone.now()

    # Recover reminders stuck in QUEUED for more than 5 minutes —
    # this happens when a previous delivery attempt timed out or crashed
    # before it could update the status to SENT/FAILED.
    stuck_cutoff = now - timezone.timedelta(minutes=5)
    stuck_count = EmailReminder.objects.filter(
        status=EmailReminder.Status.QUEUED,
        updated_at__lt=stuck_cutoff,
    ).update(
        status=EmailReminder.Status.SCHEDULED,
        updated_at=now,
    )
    if stuck_count:
        logger.warning("FutureWise: recovered %d stuck QUEUED reminder(s) → SCHEDULED", stuck_count)

    total_scheduled = EmailReminder.objects.filter(
        status=EmailReminder.Status.SCHEDULED,
        email_verified=True,
    ).count()
    due_ids = list(
        EmailReminder.objects.filter(
            status=EmailReminder.Status.SCHEDULED,
            scheduled_at__lte=now,
            email_verified=True,
        ).values_list("id", flat=True)
    )

    logger.info(
        "FutureWise dispatch tick | now=%s | verified+scheduled=%d | due now=%d",
        now.strftime("%Y-%m-%d %H:%M:%S UTC"),
        total_scheduled,
        len(due_ids),
    )

    if not due_ids:
        # Log the soonest upcoming reminder so we can see when next delivery fires
        next_reminder = (
            EmailReminder.objects.filter(
                status=EmailReminder.Status.SCHEDULED,
                email_verified=True,
                scheduled_at__gt=now,
            )
            .order_by("scheduled_at")
            .values("id", "email", "scheduled_at")
            .first()
        )
        if next_reminder:
            logger.info(
                "FutureWise: next reminder due at %s for %s",
                next_reminder["scheduled_at"].strftime("%Y-%m-%d %H:%M UTC"),
                next_reminder["email"],
            )
        return 0

    dispatched = 0
    for reminder_id in due_ids:
        logger.info("FutureWise: attempting to queue reminder %s", reminder_id)
        # Atomic transition: only proceed if still SCHEDULED
        updated = EmailReminder.objects.filter(id=reminder_id, status=EmailReminder.Status.SCHEDULED).update(
            status=EmailReminder.Status.QUEUED, updated_at=timezone.now()
        )
        if updated:
            logger.info("FutureWise: reminder %s → QUEUED, starting delivery", reminder_id)
            _deliver_reminder(str(reminder_id))
            dispatched += 1
        else:
            logger.warning("FutureWise: reminder %s already claimed by another process — skipping", reminder_id)

    logger.info("FutureWise: dispatch tick complete — delivered %d reminder(s)", dispatched)
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
    else:
        logger.debug("FutureWise: no unverified reminders to expire")
    return count


def cleanup_unverified_reminders() -> int:
    """
    Delete anonymous PENDING_VERIFICATION reminders older than EMAIL_VERIFICATION_EXPIRY_HOURS.

    Safe to call repeatedly (idempotent). Only removes reminders that are:
    - anonymous (user=None)
    - status=PENDING_VERIFICATION
    - created_at older than the configured expiry window

    Returns the number of deleted reminders.
    """
    expiry_hours = getattr(settings, "EMAIL_VERIFICATION_EXPIRY_HOURS", 24)
    cutoff = timezone.now() - timezone.timedelta(hours=expiry_hours)
    deleted_count, _ = EmailReminder.objects.filter(
        user=None,
        status=EmailReminder.Status.PENDING_VERIFICATION,
        created_at__lt=cutoff,
    ).delete()
    if deleted_count:
        logger.info("FutureWise: deleted %d expired anonymous unverified reminder(s)", deleted_count)
    else:
        logger.debug("FutureWise: no expired anonymous unverified reminders to delete")
    return deleted_count


# ── Delivery (inline, with retry counter in DB) ───────────────────────────────


def _deliver_reminder(reminder_id: str):
    """
    Deliver a single reminder across all requested channels via ReminderDispatcher.

    On partial or full failure, increments retry_count in DB.
    After _MAX_RETRIES failures, moves to DEAD_LETTER.

    Attachments are loaded here (before dispatch) so the email provider
    can access them via recipient_context["attachment_data"].
    """
    logger.info("FutureWise: _deliver_reminder START id=%s", reminder_id)

    try:
        reminder = EmailReminder.objects.prefetch_related("attachments").get(
            id=reminder_id, status=EmailReminder.Status.QUEUED
        )
        logger.info(
            "FutureWise: reminder loaded | id=%s email=%s retry_count=%d",
            reminder_id,
            reminder.email,
            reminder.retry_count,
        )
    except EmailReminder.DoesNotExist:
        logger.warning("FutureWise: reminder %s not found or not QUEUED — skipping", reminder_id)
        return

    # Load attachments once so the email provider can access them
    attachment_data = []
    storage = AttachmentStorage()
    for att in reminder.attachments.all():
        try:
            content_bytes = storage.download_bytes(att.storage_key, attachment_instance=att)
            attachment_data.append(
                {
                    "filename": att.original_filename,
                    "content_bytes": content_bytes,
                    "content_type": att.content_type,
                }
            )
            logger.debug(
                "FutureWise: loaded attachment %s (%d bytes)",
                att.original_filename,
                len(content_bytes),
            )
        except StorageError as exc:
            logger.error(
                "FutureWise: attachment %s unavailable for reminder %s: %s",
                att.id,
                reminder_id,
                exc,
            )

    dispatcher = ReminderDispatcher()
    _attachment_context[reminder_id] = attachment_data or None
    try:
        any_success = dispatcher.dispatch(reminder)
    finally:
        _attachment_context.pop(reminder_id, None)

    if any_success:
        reminder.status = EmailReminder.Status.SENT
        reminder.sent_at = timezone.now()
        reminder.save(update_fields=["status", "sent_at", "updated_at"])
        logger.info("FutureWise: ✅ SENT reminder %s (status=SENT, sent_at=%s)", reminder_id, reminder.sent_at)

        # Purge attachments after successful delivery
        if getattr(settings, "FUTUREWAVE_ATTACHMENT_PURGE_AFTER_SEND", True) and attachment_data:
            keys = list(reminder.attachments.values_list("storage_key", flat=True))
            if keys:
                storage.delete_many(keys)
                logger.info("FutureWise: purged %d attachment file(s) for reminder %s", len(keys), reminder_id)
            reminder.attachments.all().delete()
    else:
        reminder.retry_count = getattr(reminder, "retry_count", 0) + 1
        if reminder.retry_count < _MAX_RETRIES:
            reminder.status = EmailReminder.Status.SCHEDULED
            reminder.save(update_fields=["status", "retry_count", "updated_at"])
            logger.warning(
                "FutureWise: ⚠️  reminder %s will retry (attempt %d/%d)",
                reminder_id,
                reminder.retry_count,
                _MAX_RETRIES,
            )
        else:
            reminder.status = EmailReminder.Status.DEAD_LETTER
            reminder.save(update_fields=["status", "retry_count", "updated_at"])
            logger.error(
                "FutureWise: ❌ reminder %s DEAD_LETTER after %d retries",
                reminder_id,
                _MAX_RETRIES,
            )
