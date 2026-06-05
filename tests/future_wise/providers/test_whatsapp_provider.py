"""
Unit tests for WhatsAppReminderProvider.
"""

from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from apps.future_wise.providers.whatsapp_provider import WhatsAppReminderProvider


def _make_reminder(**kwargs):
    r = MagicMock()
    r.id = "test-uuid-whatsapp"
    r.email = "user@example.com"
    r.subject = kwargs.get("subject", "Hey future me")
    r.brand_name = "FutureWise"
    return r


@override_settings(
    TWILIO_ACCOUNT_SID="ACtest",
    TWILIO_AUTH_TOKEN="authtoken",
    TWILIO_WHATSAPP_NUMBER="+14155238886",
)
class WhatsAppReminderProviderTest(TestCase):

    def test_channel_code(self):
        self.assertEqual(WhatsAppReminderProvider.channel_code, "whatsapp")

    def test_is_available_opted_in_with_phone(self):
        provider = WhatsAppReminderProvider()
        self.assertTrue(provider.is_available({"phone_number": "+447700900123", "whatsapp_opted_in": True}))

    def test_is_available_not_opted_in(self):
        provider = WhatsAppReminderProvider()
        self.assertFalse(provider.is_available({"phone_number": "+447700900123", "whatsapp_opted_in": False}))

    def test_is_available_no_phone(self):
        provider = WhatsAppReminderProvider()
        self.assertFalse(provider.is_available({"phone_number": "", "whatsapp_opted_in": True}))

    @patch("twilio.rest.Client")
    def test_send_success(self, mock_client_cls):
        mock_msg = MagicMock(sid="WA123", status="queued")
        mock_client_cls.return_value.messages.create.return_value = mock_msg
        provider = WhatsAppReminderProvider()
        ctx = {"phone_number": "+447700900123", "whatsapp_opted_in": True}
        result = provider.send(_make_reminder(), ctx)
        self.assertTrue(result.success)
        self.assertEqual(result.provider_message_id, "WA123")

    @patch("twilio.rest.Client")
    def test_send_uses_whatsapp_prefix(self, mock_client_cls):
        mock_msg = MagicMock(sid="WA_prefix", status="queued")
        mock_client_cls.return_value.messages.create.return_value = mock_msg
        provider = WhatsAppReminderProvider()
        ctx = {"phone_number": "+447700900123", "whatsapp_opted_in": True}
        provider.send(_make_reminder(), ctx)
        call_kwargs = mock_client_cls.return_value.messages.create.call_args[1]
        self.assertTrue(call_kwargs["from_"].startswith("whatsapp:"))
        self.assertTrue(call_kwargs["to"].startswith("whatsapp:"))

    @patch("twilio.rest.Client")
    def test_send_permanent_failure(self, mock_client_cls):
        from twilio.base.exceptions import TwilioRestException

        exc = TwilioRestException(status=400, uri="", msg="User not opted in", code=63016)
        mock_client_cls.return_value.messages.create.side_effect = exc
        provider = WhatsAppReminderProvider()
        result = provider.send(_make_reminder(), {"phone_number": "+447700900123", "whatsapp_opted_in": True})
        self.assertFalse(result.success)
        self.assertTrue(result.is_permanent_failure)

    @patch("twilio.rest.Client")
    def test_send_transient_failure(self, mock_client_cls):
        from twilio.base.exceptions import TwilioRestException

        exc = TwilioRestException(status=500, uri="", msg="Service unavailable", code=20500)
        mock_client_cls.return_value.messages.create.side_effect = exc
        provider = WhatsAppReminderProvider()
        result = provider.send(_make_reminder(), {"phone_number": "+447700900123", "whatsapp_opted_in": True})
        self.assertFalse(result.success)
        self.assertFalse(result.is_permanent_failure)
