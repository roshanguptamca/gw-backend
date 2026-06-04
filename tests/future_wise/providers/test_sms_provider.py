"""
Unit tests for SmsReminderProvider.
"""

from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from apps.future_wise.providers.sms_provider import SmsReminderProvider


def _make_reminder(**kwargs):
    r = MagicMock()
    r.id = "test-uuid-sms"
    r.email = "user@example.com"
    r.subject = kwargs.get("subject", "Hey future me")
    r.brand_name = "FutureWise"
    return r


@override_settings(
    TWILIO_ACCOUNT_SID="ACtest",
    TWILIO_AUTH_TOKEN="authtoken",
    TWILIO_PHONE_NUMBER="+15005550006",
)
class SmsReminderProviderTest(TestCase):

    def test_channel_code(self):
        self.assertEqual(SmsReminderProvider.channel_code, "sms")

    def test_is_available_with_phone(self):
        provider = SmsReminderProvider()
        self.assertTrue(provider.is_available({"phone_number": "+447700900123"}))

    def test_is_available_without_phone(self):
        provider = SmsReminderProvider()
        self.assertFalse(provider.is_available({"phone_number": ""}))

    @patch("twilio.rest.Client")
    def test_send_success(self, mock_client_cls):
        mock_msg = MagicMock(sid="SM123", status="queued")
        mock_client_cls.return_value.messages.create.return_value = mock_msg
        provider = SmsReminderProvider()
        result = provider.send(_make_reminder(), {"phone_number": "+447700900123"})
        self.assertTrue(result.success)
        self.assertEqual(result.provider_message_id, "SM123")
        self.assertFalse(result.is_permanent_failure)

    @patch("twilio.rest.Client")
    def test_send_body_truncated_to_160(self, mock_client_cls):
        mock_msg = MagicMock(sid="SM_trunc", status="queued")
        mock_client_cls.return_value.messages.create.return_value = mock_msg
        provider = SmsReminderProvider()
        long_subject = "A" * 200
        result = provider.send(_make_reminder(subject=long_subject), {"phone_number": "+447700900123"})
        self.assertTrue(result.success)
        call_kwargs = mock_client_cls.return_value.messages.create.call_args
        body = call_kwargs[1]["body"] if call_kwargs[1] else call_kwargs[0][0]
        self.assertLessEqual(len(body), 160)

    @patch("twilio.rest.Client")
    def test_send_invalid_number_permanent_failure(self, mock_client_cls):
        from twilio.base.exceptions import TwilioRestException

        exc = TwilioRestException(status=400, uri="", msg="Invalid 'To' number", code=21211)
        mock_client_cls.return_value.messages.create.side_effect = exc
        provider = SmsReminderProvider()
        result = provider.send(_make_reminder(), {"phone_number": "+44invalid"})
        self.assertFalse(result.success)
        self.assertTrue(result.is_permanent_failure)

    @patch("twilio.rest.Client")
    def test_send_transient_twilio_error_not_permanent(self, mock_client_cls):
        from twilio.base.exceptions import TwilioRestException

        exc = TwilioRestException(status=500, uri="", msg="Service unavailable", code=20500)
        mock_client_cls.return_value.messages.create.side_effect = exc
        provider = SmsReminderProvider()
        result = provider.send(_make_reminder(), {"phone_number": "+447700900123"})
        self.assertFalse(result.success)
        self.assertFalse(result.is_permanent_failure)

    @patch("twilio.rest.Client")
    def test_send_unexpected_exception(self, mock_client_cls):
        mock_client_cls.return_value.messages.create.side_effect = RuntimeError("boom")
        provider = SmsReminderProvider()
        result = provider.send(_make_reminder(), {"phone_number": "+447700900123"})
        self.assertFalse(result.success)
        self.assertIn("boom", result.error_message)
