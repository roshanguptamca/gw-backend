"""
Unit tests for BrevoEmailService (Django SMTP backend).
"""

from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

SMTP_SETTINGS = {
    "EMAIL_BACKEND": "django.core.mail.backends.locmem.EmailBackend",
    "EMAIL_SENDER_EMAIL": "noreply@guidewisey.com",
    "EMAIL_SENDER_NAME": "FutureWise",
    "DEFAULT_FROM_EMAIL": "FutureWise <noreply@guidewisey.com>",
    # Force SMTP path so tests use locmem backend, not real Brevo API
    "BREVO_API_KEY": "",
}


@override_settings(**SMTP_SETTINGS)
class BrevoEmailServiceTest(TestCase):

    def test_send_verification_email_uses_correct_recipient(self):
        """Verification email should be addressed to the target user."""
        from django.core import mail

        from apps.future_wise.email_service import BrevoEmailService

        service = BrevoEmailService()
        service.send_verification_email("user@example.com", "https://example.com/verify/tok")

        self.assertEqual(len(mail.outbox), 1)
        msg = mail.outbox[0]
        self.assertIn("user@example.com", msg.to)
        self.assertIn("Verify", msg.subject)

    def test_send_verification_email_contains_url(self):
        """Verification email HTML should contain the verification URL."""
        from django.core import mail

        from apps.future_wise.email_service import BrevoEmailService

        verification_url = "https://example.com/verify/tok123"
        service = BrevoEmailService()
        service.send_verification_email("user@example.com", verification_url)

        msg = mail.outbox[0]
        # Check HTML alternative contains the URL
        html_body = msg.alternatives[0][0]
        self.assertIn(verification_url, html_body)

    def test_send_reminder_email_free(self):
        """Free reminder email should be sent without attachments."""
        from django.core import mail
        from django.utils import timezone

        from apps.future_wise.email_service import BrevoEmailService

        reminder = MagicMock()
        reminder.__getitem__ = MagicMock(side_effect=KeyError)  # force attribute lookup in templates
        reminder.email = "user@example.com"
        reminder.subject = "Hello self"
        reminder.tier = "free"
        reminder.scheduled_at = timezone.now()
        reminder.created_at = timezone.now()
        reminder.message = "Stay strong."

        service = BrevoEmailService()
        service.send_reminder_email(reminder)

        self.assertEqual(len(mail.outbox), 1)
        msg = mail.outbox[0]
        self.assertIn("user@example.com", msg.to)
        self.assertEqual(msg.subject, "Hello self")
        self.assertEqual(len(msg.attachments), 0)

    def test_send_reminder_email_with_attachment(self):
        """Reminder email with attachment data should include the attachment."""
        from django.core import mail
        from django.utils import timezone

        from apps.future_wise.email_service import BrevoEmailService

        reminder = MagicMock()
        reminder.__getitem__ = MagicMock(side_effect=KeyError)
        reminder.email = "user@example.com"
        reminder.subject = "With file"
        reminder.tier = "free"
        reminder.scheduled_at = timezone.now()
        reminder.created_at = timezone.now()
        reminder.message = "Check attachment."

        attachment_data = [
            {
                "filename": "notes.pdf",
                "content_bytes": b"PDF content",
                "content_type": "application/pdf",
            }
        ]

        service = BrevoEmailService()
        service.send_reminder_email(reminder, attachment_data)

        self.assertEqual(len(mail.outbox), 1)
        msg = mail.outbox[0]
        self.assertEqual(len(msg.attachments), 1)
        self.assertEqual(msg.attachments[0][0], "notes.pdf")

    def test_send_reminder_email_premium_uses_premium_template(self):
        """Premium reminder should use the premium email template."""
        from django.core import mail
        from django.utils import timezone

        from apps.future_wise.email_service import BrevoEmailService

        reminder = MagicMock()
        reminder.__getitem__ = MagicMock(side_effect=KeyError)
        reminder.email = "vip@example.com"
        reminder.subject = "VIP reminder"
        reminder.tier = "premium"
        reminder.scheduled_at = timezone.now()
        reminder.created_at = timezone.now()
        reminder.message = "VIP message."

        service = BrevoEmailService()
        service.send_reminder_email(reminder)

        self.assertEqual(len(mail.outbox), 1)

    def test_delivery_failure_raises_brevo_delivery_error(self):
        """SMTP errors should be wrapped in BrevoDeliveryError."""
        from apps.future_wise.email_service import BrevoDeliveryError, BrevoEmailService

        with patch("django.core.mail.EmailMultiAlternatives.send", side_effect=Exception("SMTP down")):
            service = BrevoEmailService()
            with self.assertRaises(BrevoDeliveryError):
                service.send_verification_email("x@example.com", "https://verify.me")

    def test_from_address_uses_sender_settings(self):
        """From address should combine EMAIL_SENDER_NAME and EMAIL_SENDER_EMAIL."""
        from apps.future_wise.email_service import BrevoEmailService

        service = BrevoEmailService()
        self.assertEqual(service.from_addr, "FutureWise <noreply@guidewisey.com>")

    @override_settings(BREVO_API_KEY="test-api-key")
    def test_brevo_api_path_used_when_api_key_set(self):
        """When BREVO_API_KEY is set, HTTP API should be used instead of SMTP."""
        from unittest.mock import MagicMock, patch

        from apps.future_wise.email_service import BrevoEmailService

        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None

        with patch("apps.future_wise.email_service.requests.post", return_value=mock_resp) as mock_post:
            service = BrevoEmailService()
            service.send_verification_email("user@example.com", "https://verify.me/tok")

        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        payload = call_kwargs[1]["json"] if "json" in call_kwargs[1] else call_kwargs[0][1]
        self.assertEqual(payload["to"][0]["email"], "user@example.com")
        self.assertEqual(call_kwargs[1]["headers"]["api-key"], "test-api-key")

    @override_settings(BREVO_API_KEY="test-api-key")
    def test_brevo_api_failure_raises_delivery_error(self):
        """Brevo API HTTP errors should be wrapped in BrevoDeliveryError."""
        import requests as req

        from apps.future_wise.email_service import BrevoDeliveryError, BrevoEmailService

        with patch("apps.future_wise.email_service.requests.post", side_effect=req.ConnectionError("API timeout")):
            service = BrevoEmailService()
            with self.assertRaises(BrevoDeliveryError):
                service.send_verification_email("x@example.com", "https://verify.me")
