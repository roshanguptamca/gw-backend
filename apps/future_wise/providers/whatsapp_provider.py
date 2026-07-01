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

import json
import logging

from django.conf import settings

from .base import DeliveryResult, IReminderProvider
from .twilio_client import get_twilio_client

logger = logging.getLogger(__name__)

# WhatsApp-specific permanent error codes
_PERMANENT_ERROR_CODES = {
    63003,
    63016,
    63024,  # Invalid message recipient / recipient-side WhatsApp restriction.
    63032,
}


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
        except ImportError:
            logger.error("WhatsAppReminderProvider: twilio package not installed.")
            return DeliveryResult(success=False, error_message="twilio package not installed")

        phone = recipient_context["phone_number"]
        from_number = getattr(settings, "TWILIO_WHATSAPP_FROM", "") or settings.TWILIO_WHATSAPP_NUMBER
        content_sid = self._resolve_content_sid(reminder, recipient_context)
        content_variables = recipient_context.get("content_variables")

        try:
            client = get_twilio_client()
            create_kwargs = {
                "from_": f"whatsapp:{from_number}",
                "to": f"whatsapp:{phone}",
            }
            if content_sid:
                create_kwargs["content_sid"] = content_sid
                create_kwargs["content_variables"] = (
                    content_variables if isinstance(content_variables, str) else json.dumps(content_variables or {})
                )
            else:
                create_kwargs["body"] = self._build_body(reminder)

            message = client.messages.create(**create_kwargs)
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

    def _resolve_content_sid(self, reminder, recipient_context: dict) -> str:
        reminder_content_sid = self._text_value(getattr(reminder, "whatsapp_content_sid", "")) or self._text_value(
            getattr(reminder, "content_sid", "")
        )
        context_content_sid = self._text_value(recipient_context.get("content_sid", ""))
        settings_content_sid = ""
        if getattr(settings, "TWILIO_WHATSAPP_USE_TEMPLATE", False):
            settings_content_sid = self._text_value(getattr(settings, "TWILIO_WHATSAPP_CONTENT_SID", ""))
        return reminder_content_sid or context_content_sid or settings_content_sid

    def _build_body(self, reminder) -> str:
        brand = reminder.brand_name
        subject = (
            self._text_value(getattr(reminder, "subject", ""))
            or self._text_value(getattr(reminder, "short_message", ""))
            or self._text_value(getattr(reminder, "message", ""))
        )[:150]
        return (
            f"*{brand}* 📬\n\n"
            f"You have a letter from your past self:\n"
            f"_{subject}_\n\n"
            f"Log in to GuideWisey to read the full letter: https://www.guidewisey.com"
        )

    @staticmethod
    def _text_value(value) -> str:
        return value.strip() if isinstance(value, str) else ""
