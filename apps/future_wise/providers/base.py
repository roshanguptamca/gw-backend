"""
IReminderProvider — abstract base for all delivery channel providers.

Each concrete provider must implement send() and optionally override
is_available() to gate delivery when required contact details are absent.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class DeliveryResult:
    """Returned by every provider after a single delivery attempt."""

    success: bool
    provider_message_id: str = ""
    provider_response: str = ""
    error_message: str = ""
    # When True the failure is permanent (e.g. invalid number) — no retry.
    is_permanent_failure: bool = False


class IReminderProvider(ABC):
    """
    Abstract base for all reminder delivery channels.

    Subclasses must set `channel_code` and implement `send()`.
    Optionally override `is_available()` to skip delivery gracefully
    when required contact details (phone, chat ID, opt-in flag) are absent.
    """

    channel_code: str = ""  # Must be overridden by each subclass.

    @abstractmethod
    def send(self, reminder, recipient_context: dict) -> DeliveryResult:
        """
        Attempt to deliver the reminder via this channel.

        Args:
            reminder: EmailReminder instance (do not save inside send()).
            recipient_context: dict with channel-relevant keys:
                email            (str)  — always present
                phone_number     (str)  — sms / voice / whatsapp
                telegram_chat_id (str)  — telegram
                whatsapp_opted_in (bool) — whatsapp

        Returns:
            DeliveryResult — never raises; all exceptions must be caught.
        """

    def is_available(self, recipient_context: dict) -> bool:
        """
        Return False to skip this channel without counting as a failure.
        The dispatcher will log a SKIPPED entry instead of a FAILED entry.
        """
        return True
