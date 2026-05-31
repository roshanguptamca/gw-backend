"""
ReminderDispatcher — orchestrates multi-channel delivery for a single reminder.

Called by tasks._deliver_reminder() after the reminder is atomically
moved to QUEUED status by the APScheduler job.

Delivery logic:
  1. Load active ReminderChannel records from the DB (feature-flag driven).
  2. Build a recipient_context dict from the reminder + UserNotificationPreference.
  3. For each channel:
       a. Skip channels not in reminder.channels_requested.
       b. Load the provider class via PROVIDER_REGISTRY (fast; avoids import overhead).
       c. Call provider.is_available(ctx) — log SKIPPED if False.
       d. Call provider.send(reminder, ctx) — write a ReminderDeliveryLog row.
  4. Return True if at least one channel delivered successfully.

The caller (tasks._deliver_reminder) is responsible for updating
EmailReminder.status / retry_count based on the returned flag.
"""

import logging

from django.utils import timezone

from .models import (
    EmailReminder,
    ReminderChannel,
    ReminderDeliveryLog,
    UserNotificationPreference,
)
from .providers import PROVIDER_REGISTRY

logger = logging.getLogger(__name__)


class ReminderDispatcher:

    def dispatch(self, reminder: EmailReminder) -> bool:
        """
        Fan out delivery across all requested, active, available channels.

        Returns:
            True  — at least one channel delivered successfully.
            False — every channel failed or was skipped.
        """
        recipient_ctx = self._build_recipient_context(reminder)
        requested = self._requested_channels(reminder)
        active_channels = list(ReminderChannel.objects.filter(is_active=True))
        any_success = False

        for channel in active_channels:
            if channel.code not in requested:
                self._write_log(
                    reminder, channel,
                    attempt=1,
                    status=ReminderDeliveryLog.DeliveryStatus.SKIPPED,
                    error_message="Channel not requested for this reminder.",
                )
                continue

            provider_cls = PROVIDER_REGISTRY.get(channel.code)
            if provider_cls is None:
                logger.error(
                    "ReminderDispatcher: no provider registered for channel=%s reminder=%s",
                    channel.code,
                    reminder.id,
                )
                continue

            provider = provider_cls()

            if not provider.is_available(recipient_ctx):
                self._write_log(
                    reminder, channel,
                    attempt=self._next_attempt_number(reminder, channel),
                    status=ReminderDeliveryLog.DeliveryStatus.SKIPPED,
                    error_message=(
                        "Provider unavailable: missing contact details or opt-in consent."
                    ),
                )
                logger.info(
                    "ReminderDispatcher: skipping channel=%s reminder=%s (not available)",
                    channel.code,
                    reminder.id,
                )
                continue

            attempt_number = self._next_attempt_number(reminder, channel)
            log = self._write_log(
                reminder, channel,
                attempt=attempt_number,
                status=ReminderDeliveryLog.DeliveryStatus.PENDING,
            )

            logger.info(
                "ReminderDispatcher: sending via channel=%s reminder=%s attempt=%d",
                channel.code,
                reminder.id,
                attempt_number,
            )
            result = provider.send(reminder, recipient_ctx)

            if result.success:
                self._complete_log(
                    log,
                    status=ReminderDeliveryLog.DeliveryStatus.SUCCESS,
                    provider_message_id=result.provider_message_id,
                    provider_response=result.provider_response,
                )
                any_success = True
                logger.info(
                    "ReminderDispatcher: ✅ channel=%s reminder=%s msg_id=%s",
                    channel.code,
                    reminder.id,
                    result.provider_message_id,
                )
            else:
                self._complete_log(
                    log,
                    status=ReminderDeliveryLog.DeliveryStatus.FAILED,
                    error_message=result.error_message,
                    provider_response=result.provider_response,
                )
                if result.is_permanent_failure:
                    logger.warning(
                        "ReminderDispatcher: ❌ channel=%s reminder=%s PERMANENT FAILURE: %s",
                        channel.code,
                        reminder.id,
                        result.error_message,
                    )
                else:
                    logger.warning(
                        "ReminderDispatcher: ⚠️  channel=%s reminder=%s failed (retryable): %s",
                        channel.code,
                        reminder.id,
                        result.error_message,
                    )

        return any_success

    # ── Private helpers ───────────────────────────────────────────────────────

    def _build_recipient_context(self, reminder: EmailReminder) -> dict:
        """
        Merge contact details from the reminder itself and from
        UserNotificationPreference (for registered users).
        Reminder-level fields take precedence (set at creation time).
        """
        # Import lazily to avoid circular import (tasks imports dispatcher)
        from . import tasks as _tasks

        ctx: dict = {
            "email": reminder.email,
            "phone_number": getattr(reminder, "phone_number", "") or "",
            "telegram_chat_id": getattr(reminder, "telegram_chat_id", "") or "",
            "whatsapp_opted_in": False,
            # Attachment data pre-loaded by tasks._deliver_reminder
            "attachment_data": _tasks._attachment_context.get(str(reminder.id)),
        }

        if reminder.user_id:
            try:
                prefs = UserNotificationPreference.objects.select_related("channel").filter(
                    user_id=reminder.user_id,
                    is_opted_in=True,
                )
                for pref in prefs:
                    code = pref.channel.code
                    if code in ("sms", "voice", "whatsapp") and pref.phone_number:
                        ctx["phone_number"] = ctx["phone_number"] or pref.phone_number
                    if code == "telegram" and pref.telegram_chat_id:
                        ctx["telegram_chat_id"] = ctx["telegram_chat_id"] or pref.telegram_chat_id
                    if code == "whatsapp" and pref.whatsapp_opted_in:
                        ctx["whatsapp_opted_in"] = True
            except Exception as exc:
                logger.warning(
                    "ReminderDispatcher: could not load preferences for user=%s: %s",
                    reminder.user_id,
                    exc,
                )

        return ctx

    def _requested_channels(self, reminder: EmailReminder) -> list[str]:
        raw = getattr(reminder, "channels_requested", "email") or "email"
        return [ch.strip() for ch in raw.split(",") if ch.strip()]

    def _next_attempt_number(self, reminder: EmailReminder, channel: ReminderChannel) -> int:
        last = (
            ReminderDeliveryLog.objects
            .filter(reminder=reminder, channel=channel)
            .order_by("-attempt_number")
            .values_list("attempt_number", flat=True)
            .first()
        )
        return (last or 0) + 1

    def _write_log(
        self,
        reminder: EmailReminder,
        channel: ReminderChannel,
        attempt: int,
        status: str,
        error_message: str = "",
        provider_message_id: str = "",
        provider_response: str = "",
    ) -> ReminderDeliveryLog:
        return ReminderDeliveryLog.objects.create(
            reminder=reminder,
            channel=channel,
            attempt_number=attempt,
            status=status,
            error_message=error_message[:1000],
            provider_message_id=provider_message_id[:255],
            provider_response=provider_response[:2000],
        )

    def _complete_log(
        self,
        log: ReminderDeliveryLog,
        status: str,
        provider_message_id: str = "",
        provider_response: str = "",
        error_message: str = "",
    ) -> None:
        log.status = status
        log.provider_message_id = provider_message_id[:255]
        log.provider_response = provider_response[:2000]
        log.error_message = error_message[:1000]
        log.completed_at = timezone.now()
        log.save(update_fields=[
            "status",
            "provider_message_id",
            "provider_response",
            "error_message",
            "completed_at",
        ])
