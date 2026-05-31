"""
EmailReminderProvider — wraps the existing BrevoEmailService.

This provider preserves 100% backward compatibility with the current
email delivery path. The only change is that delivery is now invoked
through IReminderProvider.send() instead of directly in tasks.py.
"""

import logging

from ..email_service import BrevoDeliveryError, BrevoEmailService
from .base import DeliveryResult, IReminderProvider

logger = logging.getLogger(__name__)


class EmailReminderProvider(IReminderProvider):
    channel_code = "email"

    def is_available(self, recipient_context: dict) -> bool:
        return bool(recipient_context.get("email"))

    def send(self, reminder, recipient_context: dict) -> DeliveryResult:
        try:
            service = BrevoEmailService()
            # Attachment data is passed via recipient_context (loaded in tasks.py)
            attachment_data = recipient_context.get("attachment_data") or None
            service.send_reminder_email(reminder, attachment_data)
            msg_id = getattr(reminder, "brevo_message_id", "")
            logger.info(
                "EmailReminderProvider: delivered reminder=%s to=%s msg_id=%s",
                reminder.id,
                reminder.email,
                msg_id,
            )
            return DeliveryResult(success=True, provider_message_id=msg_id)
        except BrevoDeliveryError as exc:
            logger.warning(
                "EmailReminderProvider: BrevoDeliveryError reminder=%s error=%s",
                reminder.id,
                exc,
            )
            return DeliveryResult(success=False, error_message=str(exc)[:1000])
        except Exception as exc:
            logger.error(
                "EmailReminderProvider: unexpected error reminder=%s error=%s",
                reminder.id,
                exc,
            )
            return DeliveryResult(success=False, error_message=f"Unexpected: {exc}"[:1000])
