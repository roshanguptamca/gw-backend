"""
WhatsAppReminderProvider — delivers reminder via Twilio WhatsApp Sandbox.

The recipient must have already sent the Twilio Sandbox join phrase
(e.g. "join <word>-<word>") to the sandbox number. This is tracked
via UserNotificationPreference.whatsapp_opted_in.

Required settings:
    TWILIO_ACCOUNT_SID      — Twilio account SID
    TWILIO_AUTH_TOKEN       — Twilio auth token
    TWILIO_WHATSAPP_NUMBER  — Sandbox number e.g. +14155238886

For production: replace sandbox with Twilio WhatsApp Business API.
"""

import logging

from django.conf import settings

from .base import DeliveryResult, IReminderProvider

logger = logging.getLogger(__name__)

# WhatsApp-specific permanent error codes
_PERMANENT_ERROR_CODES = {63016, 63032, 63003}


class WhatsAppReminderProvider(IReminderProvider):
    channel_code = "whatsapp"

    def is_available(self, recipient_context: dict) -> bool:
        """Requires both a phone number AND explicit WhatsApp opt-in."""
        phone = recipient_context.get("phone_number", "")
        opted_in = recipient_context.get("whatsapp_opted_in", False)
        return bool(phone) and bool(opted_in)

    def send(self, reminder, recipient_context: dict) -> DeliveryResult:
        try:
            from twilio.base.exceptions import TwilioRestException
            from twilio.rest import Client
        except ImportError:
            logger.error("WhatsAppReminderProvider: twilio package not installed.")
            return DeliveryResult(success=False, error_message="twilio package not installed")

        phone = recipient_context["phone_number"]
        body = self._build_body(reminder)

        try:
            client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
            message = client.messages.create(
                body=body,
                from_=f"whatsapp:{settings.TWILIO_WHATSAPP_NUMBER}",
                to=f"whatsapp:{phone}",
            )
            logger.info(
                "WhatsAppReminderProvider: delivered reminder=%s to=whatsapp:%s sid=%s status=%s",
                reminder.id,
                phone,
                message.sid,
                message.status,
            )
            return DeliveryResult(
                success=True,
                provider_message_id=message.sid,
                provider_response=f"status={message.status}",
            )
        except TwilioRestException as exc:
            is_permanent = exc.code in _PERMANENT_ERROR_CODES
            logger.warning(
                "WhatsAppReminderProvider: TwilioRestException reminder=%s code=%s permanent=%s error=%s",
                reminder.id,
                exc.code,
                is_permanent,
                exc,
            )
            return DeliveryResult(
                success=False,
                error_message=str(exc)[:1000],
                is_permanent_failure=is_permanent,
            )
        except Exception as exc:
            logger.error(
                "WhatsAppReminderProvider: unexpected error reminder=%s error=%s",
                reminder.id,
                exc,
            )
            return DeliveryResult(success=False, error_message=f"Unexpected: {exc}"[:1000])

    def _build_body(self, reminder) -> str:
        brand = reminder.brand_name
        subject = reminder.subject[:150]
        return (
            f"*{brand}* 📬\n\n"
            f"You have a letter from your past self:\n"
            f"_{subject}_\n\n"
            f"Log in to GuideWisey to read the full letter: https://www.guidewisey.com"
        )
