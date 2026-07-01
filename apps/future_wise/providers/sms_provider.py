"""
SmsReminderProvider — delivers reminder via Twilio SMS.

POC: uses a Twilio trial account. Only verified numbers can receive
messages on a trial account.

Required settings:
    TWILIO_ACCOUNT_SID   — Twilio account SID (ACxxxxxxxx...)
    TWILIO_AUTH_TOKEN    — Twilio auth token
    TWILIO_PHONE_NUMBER  — Twilio phone number in E.164 (+15005550006)

Permanent failure error codes (no retry):
    21211 — Invalid 'To' phone number
    21614 — 'To' number is not a valid mobile number
    21408 — Permission to send to this region is not enabled
    21610 — Message cannot be sent to the 'To' number (blacklisted)
"""

import logging

from django.conf import settings

from .base import DeliveryResult, IReminderProvider
from .twilio_client import get_twilio_client

logger = logging.getLogger(__name__)

# Twilio error codes that indicate a permanent, non-retryable failure.
_PERMANENT_ERROR_CODES = {21211, 21614, 21408, 21610, 21612}


class SmsReminderProvider(IReminderProvider):
    channel_code = "sms"

    def is_available(self, recipient_context: dict) -> bool:
        return bool(recipient_context.get("phone_number"))

    def send(self, reminder, recipient_context: dict) -> DeliveryResult:
        try:
            from twilio.base.exceptions import TwilioRestException
        except ImportError:
            logger.error("SmsReminderProvider: twilio package not installed. Run: pip install twilio")
            return DeliveryResult(success=False, error_message="twilio package not installed")

        phone = recipient_context["phone_number"]
        body = self._build_body(reminder)

        try:
            client = get_twilio_client()
            message = client.messages.create(
                body=body,
                from_=settings.TWILIO_PHONE_NUMBER,
                to=phone,
            )
            logger.info(
                "SmsReminderProvider: delivered reminder=%s to=%s sid=%s status=%s",
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
                "SmsReminderProvider: TwilioRestException reminder=%s code=%s permanent=%s error=%s",
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
                "SmsReminderProvider: unexpected error reminder=%s error=%s",
                reminder.id,
                exc,
            )
            return DeliveryResult(success=False, error_message=f"Unexpected: {exc}"[:1000])

    def _build_body(self, reminder) -> str:
        brand = reminder.brand_name
        subject = reminder.subject[:100]
        return (f'[{brand}] A letter from your past self: "{subject}" ' f"— Log in to GuideWisey to read it.")[:160]
