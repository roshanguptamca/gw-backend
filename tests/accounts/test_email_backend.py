import base64
from email.mime.application import MIMEApplication
from unittest.mock import patch

from django.core.mail import EmailMultiAlternatives
from django.test import SimpleTestCase, override_settings

from guidewisey.email_backend import BrevoAPIEmailBackend


@override_settings(BREVO_API_KEY="test-api-key", DEFAULT_FROM_EMAIL="GuideWisey <sender@example.test>")
class BrevoAttachmentTests(SimpleTestCase):
    def message(self):
        message = EmailMultiAlternatives("Order confirmed", "Order details", to=["buyer@example.test"])
        message.attach_alternative("<p>Order details</p>", "text/html")
        return message

    @patch("guidewisey.email_backend.requests.post")
    def test_multiple_invoice_attachments_are_sent_as_base64(self, post):
        post.return_value.status_code = 201
        message = self.message()
        message.attach("RK-2026-000001.pdf", b"%PDF-first", "application/pdf")
        message.attach("SB-2026-000001.pdf", b"%PDF-second", "application/pdf")
        self.assertEqual(BrevoAPIEmailBackend().send_messages([message]), 1)
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["htmlContent"], "<p>Order details</p>")
        self.assertEqual(payload["textContent"], "Order details")
        self.assertEqual(payload["sender"], {"name": "GuideWisey", "email": "sender@example.test"})
        self.assertEqual(
            payload["attachment"],
            [
                {"name": "RK-2026-000001.pdf", "content": base64.b64encode(b"%PDF-first").decode("ascii")},
                {"name": "SB-2026-000001.pdf", "content": base64.b64encode(b"%PDF-second").decode("ascii")},
            ],
        )

    @patch("guidewisey.email_backend.requests.post")
    def test_email_without_attachments_preserves_existing_payload(self, post):
        post.return_value.status_code = 201
        self.assertEqual(BrevoAPIEmailBackend().send_messages([self.message()]), 1)
        self.assertNotIn("attachment", post.call_args.kwargs["json"])

    @patch("guidewisey.email_backend.requests.post")
    def test_text_and_mime_attachments(self, post):
        post.return_value.status_code = 201
        message = self.message()
        message.attach("notes.txt", "Thank you", "text/plain")
        attachment = MIMEApplication(b"%PDF-file", _subtype="pdf")
        attachment.add_header("Content-Disposition", "attachment", filename="invoice.pdf")
        message.attach(attachment)
        BrevoAPIEmailBackend().send_messages([message])
        payload = post.call_args.kwargs["json"]["attachment"]
        self.assertEqual(base64.b64decode(payload[0]["content"]), b"Thank you")
        self.assertEqual(base64.b64decode(payload[1]["content"]), b"%PDF-file")
        self.assertEqual(payload[1]["name"], "invoice.pdf")

    @patch("guidewisey.email_backend.requests.post")
    def test_ip_allowlist_rejection_is_not_reported_as_success(self, post):
        post.return_value.status_code = 401
        post.return_value.text = '{"message":"Unrecognised IP address"}'
        with self.assertRaisesRegex(RuntimeError, "Brevo API error 401"):
            BrevoAPIEmailBackend().send_messages([self.message()])

    @patch("guidewisey.email_backend.requests.post")
    def test_invalid_attachment_is_not_silently_dropped(self, post):
        message = self.message()
        message.attach(MIMEApplication(b"%PDF-file", _subtype="pdf"))
        with self.assertRaisesRegex(ValueError, "filename"):
            BrevoAPIEmailBackend().send_messages([message])
        post.assert_not_called()
