"""
Unit tests for EmailReminderProvider.
"""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from apps.future_wise.providers.email_provider import EmailReminderProvider


def _make_reminder(**kwargs):
    r = MagicMock()
    r.id = "test-uuid-email"
    r.email = kwargs.get("email", "user@example.com")
    r.subject = kwargs.get("subject", "Hey future me")
    r.brand_name = "FutureWise"
    r.brevo_message_id = kwargs.get("brevo_message_id", "brevo_123")
    return r


class EmailReminderProviderTest(TestCase):

    def test_channel_code(self):
        self.assertEqual(EmailReminderProvider.channel_code, "email")

    def test_is_available_with_email(self):
        provider = EmailReminderProvider()
        self.assertTrue(provider.is_available({"email": "a@b.com"}))

    def test_is_available_without_email(self):
        provider = EmailReminderProvider()
        self.assertFalse(provider.is_available({"email": ""}))

    @patch("apps.future_wise.providers.email_provider.BrevoEmailService")
    def test_send_success(self, mock_cls):
        mock_cls.return_value.send_reminder_email.return_value = None
        provider = EmailReminderProvider()
        reminder = _make_reminder()
        result = provider.send(reminder, {"email": reminder.email})
        self.assertTrue(result.success)
        self.assertFalse(result.is_permanent_failure)
        mock_cls.return_value.send_reminder_email.assert_called_once_with(reminder, None)

    @patch("apps.future_wise.providers.email_provider.BrevoEmailService")
    def test_send_passes_attachment_data(self, mock_cls):
        mock_cls.return_value.send_reminder_email.return_value = None
        provider = EmailReminderProvider()
        reminder = _make_reminder()
        att_data = [{"filename": "doc.pdf", "content_bytes": b"data", "content_type": "application/pdf"}]
        ctx = {"email": reminder.email, "attachment_data": att_data}
        result = provider.send(reminder, ctx)
        self.assertTrue(result.success)
        mock_cls.return_value.send_reminder_email.assert_called_once_with(reminder, att_data)

    @patch("apps.future_wise.providers.email_provider.BrevoEmailService")
    def test_send_brevo_error_returns_failure(self, mock_cls):
        from apps.future_wise.email_service import BrevoDeliveryError

        mock_cls.return_value.send_reminder_email.side_effect = BrevoDeliveryError("SMTP down")
        provider = EmailReminderProvider()
        result = provider.send(_make_reminder(), {"email": "user@example.com"})
        self.assertFalse(result.success)
        self.assertIn("SMTP down", result.error_message)
        self.assertFalse(result.is_permanent_failure)

    @patch("apps.future_wise.providers.email_provider.BrevoEmailService")
    def test_send_unexpected_exception_returns_failure(self, mock_cls):
        mock_cls.return_value.send_reminder_email.side_effect = RuntimeError("unexpected")
        provider = EmailReminderProvider()
        result = provider.send(_make_reminder(), {"email": "user@example.com"})
        self.assertFalse(result.success)
        self.assertIn("unexpected", result.error_message)
