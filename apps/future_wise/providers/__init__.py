"""
FutureWise reminder channel providers.

All providers implement IReminderProvider from base.py.
The provider registry maps channel codes to provider classes.

Usage (via ReminderDispatcher — do not call providers directly):
    from apps.future_wise.providers import PROVIDER_REGISTRY
    provider = PROVIDER_REGISTRY["sms"]()
    result = provider.send(reminder, recipient_context)
"""

from .base import DeliveryResult, IReminderProvider
from .email_provider import EmailReminderProvider
from .sms_provider import SmsReminderProvider
from .telegram_provider import TelegramReminderProvider
from .voice_provider import VoiceCallReminderProvider
from .whatsapp_provider import WhatsAppReminderProvider

PROVIDER_REGISTRY: dict[str, type[IReminderProvider]] = {
    "email": EmailReminderProvider,
    "sms": SmsReminderProvider,
    "voice": VoiceCallReminderProvider,
    "whatsapp": WhatsAppReminderProvider,
    "telegram": TelegramReminderProvider,
}

__all__ = [
    "IReminderProvider",
    "DeliveryResult",
    "EmailReminderProvider",
    "SmsReminderProvider",
    "VoiceCallReminderProvider",
    "WhatsAppReminderProvider",
    "TelegramReminderProvider",
    "PROVIDER_REGISTRY",
]
