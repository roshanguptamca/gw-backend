"""
Unit tests for TelegramReminderProvider.
"""

from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from apps.future_wise.providers.telegram_provider import TelegramReminderProvider


def _make_reminder(**kwargs):
    r = MagicMock()
    r.id = "test-uuid-telegram"
    r.email = "user@example.com"
    r.subject = kwargs.get("subject", "Hey future me")
    r.message = kwargs.get("message", "I hope you are doing well and have achieved your goals.")
    r.brand_name = "FutureWise"
    return r


def _mock_response(status_code=200, json_data=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {"ok": True, "result": {"message_id": 42}}
    if status_code >= 400:
        from requests import HTTPError
        resp.raise_for_status.side_effect = HTTPError(response=resp)
        resp.text = "Bad Request"
    else:
        resp.raise_for_status.return_value = None
    return resp


@override_settings(TELEGRAM_BOT_TOKEN="123456:TEST")
class TelegramReminderProviderTest(TestCase):

    def test_channel_code(self):
        self.assertEqual(TelegramReminderProvider.channel_code, "telegram")

    def test_is_available_with_chat_id(self):
        provider = TelegramReminderProvider()
        self.assertTrue(provider.is_available({"telegram_chat_id": "123456789"}))

    def test_is_available_without_chat_id(self):
        provider = TelegramReminderProvider()
        self.assertFalse(provider.is_available({"telegram_chat_id": ""}))

    @patch("apps.future_wise.providers.telegram_provider.requests.post")
    def test_send_success(self, mock_post):
        mock_post.return_value = _mock_response()
        provider = TelegramReminderProvider()
        result = provider.send(_make_reminder(), {"telegram_chat_id": "123456789"})
        self.assertTrue(result.success)
        self.assertEqual(result.provider_message_id, "42")

    @patch("apps.future_wise.providers.telegram_provider.requests.post")
    def test_send_posts_to_correct_url(self, mock_post):
        mock_post.return_value = _mock_response()
        provider = TelegramReminderProvider()
        provider.send(_make_reminder(), {"telegram_chat_id": "999"})
        call_args = mock_post.call_args
        url = call_args[0][0]
        self.assertIn("123456:TEST", url)
        self.assertIn("sendMessage", url)

    @patch("apps.future_wise.providers.telegram_provider.requests.post")
    def test_send_includes_subject_in_text(self, mock_post):
        mock_post.return_value = _mock_response()
        provider = TelegramReminderProvider()
        reminder = _make_reminder(subject="My special subject")
        provider.send(reminder, {"telegram_chat_id": "999"})
        call_args = mock_post.call_args
        payload = call_args[1]["json"]
        self.assertIn("My special subject", payload["text"])

    @patch("apps.future_wise.providers.telegram_provider.requests.post")
    def test_send_http_400_is_permanent_failure(self, mock_post):
        mock_post.return_value = _mock_response(status_code=400)
        provider = TelegramReminderProvider()
        result = provider.send(_make_reminder(), {"telegram_chat_id": "invalid_id"})
        self.assertFalse(result.success)
        self.assertTrue(result.is_permanent_failure)

    @patch("apps.future_wise.providers.telegram_provider.requests.post")
    def test_send_http_500_is_transient_failure(self, mock_post):
        mock_post.return_value = _mock_response(status_code=500)
        provider = TelegramReminderProvider()
        result = provider.send(_make_reminder(), {"telegram_chat_id": "123456789"})
        self.assertFalse(result.success)
        self.assertFalse(result.is_permanent_failure)

    @patch("apps.future_wise.providers.telegram_provider.requests.post")
    def test_send_connection_error(self, mock_post):
        from requests import ConnectionError
        mock_post.side_effect = ConnectionError("network down")
        provider = TelegramReminderProvider()
        result = provider.send(_make_reminder(), {"telegram_chat_id": "123456789"})
        self.assertFalse(result.success)
        self.assertIn("Connection error", result.error_message)
        self.assertFalse(result.is_permanent_failure)

    @patch("apps.future_wise.providers.telegram_provider.requests.post")
    def test_message_excerpt_truncated(self, mock_post):
        mock_post.return_value = _mock_response()
        provider = TelegramReminderProvider()
        long_message = "X" * 1000
        reminder = _make_reminder(message=long_message)
        provider.send(reminder, {"telegram_chat_id": "123"})
        call_args = mock_post.call_args
        payload = call_args[1]["json"]
        # Excerpt is capped at 300 chars + ellipsis
        self.assertIn("...", payload["text"])
