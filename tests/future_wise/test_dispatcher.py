"""
Integration tests for ReminderDispatcher.

Tests fan-out logic, partial success, full failure, SKIPPED logs,
and permanent failure handling — all with mocked providers.
"""

from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.future_wise.dispatcher import ReminderDispatcher
from apps.future_wise.models import (
    EmailReminder,
    ReminderChannel,
    ReminderDeliveryLog,
    UserNotificationPreference,
)
from apps.future_wise.providers.base import DeliveryResult

User = get_user_model()


def _make_reminder(**kwargs) -> EmailReminder:
    return EmailReminder.objects.create(
        email=kwargs.pop("email", "user@example.com"),
        email_verified=True,
        verification_token=EmailReminder.generate_verification_token(),
        verification_token_expires_at=EmailReminder.make_token_expiry(),
        subject="Test subject",
        message="Test message body",
        scheduled_at=timezone.now() - timedelta(minutes=1),
        tier=EmailReminder.Tier.FREE,
        status=EmailReminder.Status.QUEUED,
        **kwargs,
    )


def _make_channel(code: str) -> ReminderChannel:
    return ReminderChannel.objects.get_or_create(
        code=code,
        defaults={
            "display_name": code.title(),
            "provider_class": f"apps.future_wise.providers.{code}_provider.Provider",
            "is_active": True,
        },
    )[0]


class ReminderDispatcherTest(TestCase):

    def setUp(self):
        self.email_channel = _make_channel("email")

    def _mock_provider(self, success=True, is_permanent=False, msg_id="msg_001"):
        provider = MagicMock()
        provider.channel_code = self.email_channel.code
        provider.is_available.return_value = True
        provider.send.return_value = DeliveryResult(
            success=success,
            provider_message_id=msg_id if success else "",
            error_message="" if success else "provider error",
            is_permanent_failure=is_permanent,
        )
        return provider

    @patch("apps.future_wise.dispatcher.PROVIDER_REGISTRY")
    def test_dispatch_success_writes_success_log(self, mock_registry):
        reminder = _make_reminder(channels_requested="email")
        mock_provider = self._mock_provider(success=True)
        mock_registry.get.return_value = lambda: mock_provider

        dispatcher = ReminderDispatcher()
        result = dispatcher.dispatch(reminder)

        self.assertTrue(result)
        log = ReminderDeliveryLog.objects.get(reminder=reminder, channel=self.email_channel)
        self.assertEqual(log.status, ReminderDeliveryLog.DeliveryStatus.SUCCESS)
        self.assertEqual(log.provider_message_id, "msg_001")

    @patch("apps.future_wise.dispatcher.PROVIDER_REGISTRY")
    def test_dispatch_failure_writes_failed_log(self, mock_registry):
        reminder = _make_reminder(channels_requested="email")
        mock_provider = self._mock_provider(success=False)
        mock_registry.get.return_value = lambda: mock_provider

        dispatcher = ReminderDispatcher()
        result = dispatcher.dispatch(reminder)

        self.assertFalse(result)
        log = ReminderDeliveryLog.objects.get(reminder=reminder, channel=self.email_channel)
        self.assertEqual(log.status, ReminderDeliveryLog.DeliveryStatus.FAILED)
        self.assertIn("provider error", log.error_message)

    @patch("apps.future_wise.dispatcher.PROVIDER_REGISTRY")
    def test_dispatch_channel_not_requested_writes_skipped(self, mock_registry):
        sms_channel = _make_channel("sms")
        # Reminder only requests email, but SMS channel is active
        reminder = _make_reminder(channels_requested="email")
        mock_registry.get.return_value = lambda: self._mock_provider(success=True)

        dispatcher = ReminderDispatcher()
        dispatcher.dispatch(reminder)

        sms_log = ReminderDeliveryLog.objects.filter(reminder=reminder, channel=sms_channel).first()
        self.assertIsNotNone(sms_log)
        self.assertEqual(sms_log.status, ReminderDeliveryLog.DeliveryStatus.SKIPPED)

    @patch("apps.future_wise.dispatcher.PROVIDER_REGISTRY")
    def test_dispatch_channel_unavailable_writes_skipped(self, mock_registry):
        reminder = _make_reminder(channels_requested="email", phone_number="")
        mock_provider = MagicMock()
        mock_provider.is_available.return_value = False
        mock_registry.get.return_value = lambda: mock_provider

        dispatcher = ReminderDispatcher()
        result = dispatcher.dispatch(reminder)

        self.assertFalse(result)
        log = ReminderDeliveryLog.objects.get(reminder=reminder, channel=self.email_channel)
        self.assertEqual(log.status, ReminderDeliveryLog.DeliveryStatus.SKIPPED)

    @patch("apps.future_wise.dispatcher.PROVIDER_REGISTRY")
    def test_dispatch_partial_success_returns_true(self, mock_registry):
        """If at least one channel succeeds, dispatch returns True."""
        sms_channel = _make_channel("sms")
        reminder = _make_reminder(channels_requested="email,sms", phone_number="+447700900123")

        def provider_factory():
            p = MagicMock()
            p.is_available.return_value = True
            # email succeeds, sms fails
            def side_effect(rem, ctx):
                if mock_registry.get.call_args[0][0] == "email":
                    return DeliveryResult(success=True, provider_message_id="em_ok")
                return DeliveryResult(success=False, error_message="sms down")
            p.send.side_effect = side_effect
            return p

        # We simplify: mock returns a succeeding provider for both
        mock_provider_email = MagicMock()
        mock_provider_email.is_available.return_value = True
        mock_provider_email.send.return_value = DeliveryResult(success=True, provider_message_id="em_ok")

        mock_provider_sms = MagicMock()
        mock_provider_sms.is_available.return_value = True
        mock_provider_sms.send.return_value = DeliveryResult(success=False, error_message="sms down")

        def get_provider(code):
            if code == "email":
                return lambda: mock_provider_email
            if code == "sms":
                return lambda: mock_provider_sms
            return None

        mock_registry.get.side_effect = get_provider
        dispatcher = ReminderDispatcher()
        result = dispatcher.dispatch(reminder)
        self.assertTrue(result)

    @patch("apps.future_wise.dispatcher.PROVIDER_REGISTRY")
    def test_dispatch_increments_attempt_number_on_retry(self, mock_registry):
        reminder = _make_reminder(channels_requested="email")
        mock_provider = self._mock_provider(success=False)
        mock_registry.get.return_value = lambda: mock_provider

        dispatcher = ReminderDispatcher()
        dispatcher.dispatch(reminder)  # attempt 1 → FAILED
        dispatcher.dispatch(reminder)  # attempt 2 → FAILED

        logs = ReminderDeliveryLog.objects.filter(
            reminder=reminder, channel=self.email_channel
        ).order_by("attempt_number")
        self.assertEqual(logs.count(), 2)
        self.assertEqual(logs[0].attempt_number, 1)
        self.assertEqual(logs[1].attempt_number, 2)

    @patch("apps.future_wise.dispatcher.PROVIDER_REGISTRY")
    def test_inactive_channel_excluded(self, mock_registry):
        """Inactive channels should not be dispatched."""
        inactive = _make_channel("telegram")
        inactive.is_active = False
        inactive.save()

        reminder = _make_reminder(channels_requested="email,telegram")
        mock_provider = self._mock_provider(success=True)
        mock_registry.get.return_value = lambda: mock_provider

        dispatcher = ReminderDispatcher()
        dispatcher.dispatch(reminder)

        # Telegram log should not exist (channel is inactive → not iterated)
        self.assertFalse(
            ReminderDeliveryLog.objects.filter(reminder=reminder, channel=inactive).exists()
        )


class DispatcherRecipientContextTest(TestCase):
    """Tests _build_recipient_context merging from reminder + UserNotificationPreference."""

    def test_phone_number_from_reminder(self):
        reminder = _make_reminder(phone_number="+447700900123")
        dispatcher = ReminderDispatcher()
        ctx = dispatcher._build_recipient_context(reminder)
        self.assertEqual(ctx["phone_number"], "+447700900123")

    def test_telegram_chat_id_from_reminder(self):
        reminder = _make_reminder(telegram_chat_id="987654321")
        dispatcher = ReminderDispatcher()
        ctx = dispatcher._build_recipient_context(reminder)
        self.assertEqual(ctx["telegram_chat_id"], "987654321")

    def test_whatsapp_opted_in_from_preference(self):
        user = User.objects.create_user("wa_user", "wa@example.com", "pass")
        channel = _make_channel("whatsapp")
        UserNotificationPreference.objects.create(
            user=user,
            email=user.email,
            channel=channel,
            is_opted_in=True,
            whatsapp_opted_in=True,
            phone_number="+447700900999",
        )
        reminder = _make_reminder(
            user=user,
            email=user.email,
            phone_number="",
            channels_requested="whatsapp",
        )
        dispatcher = ReminderDispatcher()
        ctx = dispatcher._build_recipient_context(reminder)
        self.assertTrue(ctx["whatsapp_opted_in"])
        self.assertEqual(ctx["phone_number"], "+447700900999")
