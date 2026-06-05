"""
Unit tests for VoiceCallReminderProvider.
"""

from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from apps.future_wise.providers.voice_provider import VoiceCallReminderProvider


def _make_reminder(**kwargs):
    r = MagicMock()
    r.id = "test-uuid-voice"
    r.email = "user@example.com"
    r.subject = kwargs.get("subject", "Hello future me")
    r.brand_name = "FutureWise"
    return r


@override_settings(
    TWILIO_ACCOUNT_SID="ACtest",
    TWILIO_AUTH_TOKEN="authtoken",
    TWILIO_PHONE_NUMBER="+15005550006",
)
class VoiceCallReminderProviderTest(TestCase):

    def test_channel_code(self):
        self.assertEqual(VoiceCallReminderProvider.channel_code, "voice")

    def test_is_available_with_phone(self):
        provider = VoiceCallReminderProvider()
        self.assertTrue(provider.is_available({"phone_number": "+447700900123"}))

    def test_is_available_without_phone(self):
        provider = VoiceCallReminderProvider()
        self.assertFalse(provider.is_available({"phone_number": ""}))

    @patch("twilio.rest.Client")
    def test_send_success(self, mock_client_cls):
        mock_call = MagicMock(sid="CA123", status="queued")
        mock_client_cls.return_value.calls.create.return_value = mock_call
        provider = VoiceCallReminderProvider()
        result = provider.send(_make_reminder(), {"phone_number": "+447700900123"})
        self.assertTrue(result.success)
        self.assertEqual(result.provider_message_id, "CA123")

    @patch("twilio.rest.Client")
    def test_twiml_contains_subject(self, mock_client_cls):
        mock_call = MagicMock(sid="CA_twiml", status="queued")
        mock_client_cls.return_value.calls.create.return_value = mock_call
        provider = VoiceCallReminderProvider()
        reminder = _make_reminder(subject="My special milestone")
        provider.send(reminder, {"phone_number": "+447700900123"})
        call_kwargs = mock_client_cls.return_value.calls.create.call_args[1]
        twiml = call_kwargs["twiml"]
        self.assertIn("My special milestone", twiml)
        self.assertIn("<Say", twiml)

    @patch("twilio.rest.Client")
    def test_twiml_strips_xml_special_chars(self, mock_client_cls):
        mock_call = MagicMock(sid="CA_xml", status="queued")
        mock_client_cls.return_value.calls.create.return_value = mock_call
        provider = VoiceCallReminderProvider()
        reminder = _make_reminder(subject='Subject with <xml> & "quotes"')
        provider.send(reminder, {"phone_number": "+447700900123"})
        call_kwargs = mock_client_cls.return_value.calls.create.call_args[1]
        twiml = call_kwargs["twiml"]
        self.assertNotIn("<xml>", twiml)
        self.assertNotIn("&", twiml)

    @patch("twilio.rest.Client")
    def test_send_permanent_failure(self, mock_client_cls):
        from twilio.base.exceptions import TwilioRestException

        exc = TwilioRestException(status=400, uri="", msg="Invalid phone", code=13224)
        mock_client_cls.return_value.calls.create.side_effect = exc
        provider = VoiceCallReminderProvider()
        result = provider.send(_make_reminder(), {"phone_number": "+44invalid"})
        self.assertFalse(result.success)
        self.assertTrue(result.is_permanent_failure)

    @patch("twilio.rest.Client")
    def test_send_transient_failure(self, mock_client_cls):
        from twilio.base.exceptions import TwilioRestException

        exc = TwilioRestException(status=500, uri="", msg="Server error", code=20500)
        mock_client_cls.return_value.calls.create.side_effect = exc
        provider = VoiceCallReminderProvider()
        result = provider.send(_make_reminder(), {"phone_number": "+447700900123"})
        self.assertFalse(result.success)
        self.assertFalse(result.is_permanent_failure)
