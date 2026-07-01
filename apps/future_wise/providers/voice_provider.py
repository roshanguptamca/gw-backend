"""
VoiceCallReminderProvider — delivers reminder via a Twilio outbound call.

A TwiML <Say> script reads the reminder subject aloud using Twilio's
Alice voice. The call is initiated from TWILIO_PHONE_NUMBER.

POC: uses a Twilio trial account. Only verified numbers can be called.

Required settings:
    TWILIO_ACCOUNT_SID   — Twilio account SID
    TWILIO_AUTH_TOKEN    — Twilio auth token
    TWILIO_PHONE_NUMBER  — Twilio phone number in E.164

Permanent failure error codes (no retry):
    13224 — Invalid phone number (could not be parsed)
    13225 — Dial: Forbidden region
    21217 — Phone number is not valid
"""

import logging

from django.conf import settings

from .base import DeliveryResult, IReminderProvider
from .twilio_client import get_twilio_client

logger = logging.getLogger(__name__)

_PERMANENT_ERROR_CODES = {13224, 13225, 21217, 21401}


class VoiceCallReminderProvider(IReminderProvider):
    channel_code = "voice"

    def is_available(self, recipient_context: dict) -> bool:
        return bool(recipient_context.get("phone_number"))

    def send(self, reminder, recipient_context: dict) -> DeliveryResult:
        try:
            from twilio.base.exceptions import TwilioRestException
        except ImportError:
            logger.error("VoiceCallReminderProvider: twilio package not installed.")
            return DeliveryResult(success=False, error_message="twilio package not installed")

        phone = recipient_context["phone_number"]
        twiml = self._build_twiml(reminder)

        try:
            client = get_twilio_client()
            call = client.calls.create(
                twiml=twiml,
                from_=settings.TWILIO_PHONE_NUMBER,
                to=phone,
            )
            logger.info(
                "VoiceCallReminderProvider: call initiated reminder=%s to=%s sid=%s status=%s",
                reminder.id,
                phone,
                call.sid,
                call.status,
            )
            return DeliveryResult(
                success=True,
                provider_message_id=call.sid,
                provider_response=f"status={call.status}",
            )
        except TwilioRestException as exc:
            is_permanent = exc.code in _PERMANENT_ERROR_CODES
            logger.warning(
                "VoiceCallReminderProvider: TwilioRestException reminder=%s code=%s permanent=%s error=%s",
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
                "VoiceCallReminderProvider: unexpected error reminder=%s error=%s",
                reminder.id,
                exc,
            )
            return DeliveryResult(success=False, error_message=f"Unexpected: {exc}"[:1000])

    def _build_twiml(self, reminder) -> str:
        brand = reminder.brand_name
        # Escape XML special characters in user content
        subject = (
            reminder.subject[:200]
            .replace("&", "and")
            .replace("<", "")
            .replace(">", "")
            .replace('"', "")
            .replace("'", "")
        )
        return (
            "<Response>"
            '<Say voice="alice" language="en-GB">'
            f"Hello. This is a reminder from {brand} on GuideWisey. "
            f"You have a letter from your past self. "
            f"The subject is: {subject}. "
            "Please log in to GuideWisey dot com to read your full letter. Goodbye."
            "</Say>"
            "</Response>"
        )
