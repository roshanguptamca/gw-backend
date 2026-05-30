"""
Transactional email service for FutureWise.

Uses Django's built-in email backend (configured for Brevo SMTP relay by default).
Switch EMAIL_BACKEND in settings / .env to change delivery method without touching
this code — e.g. console backend for local dev, SMTP for production.
"""

import logging
from typing import Optional

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)


class BrevoEmailService:
    """
    Sends transactional emails via Django's email backend.

    Required settings (set via .env):
        EMAIL_HOST          — SMTP server  (default: smtp-relay.brevo.com)
        EMAIL_PORT          — SMTP port    (default: 587)
        EMAIL_HOST_USER     — SMTP login   (default: ac98f2001@smtp-brevo.com)
        EMAIL_HOST_PASSWORD — SMTP key/password
        EMAIL_SENDER_EMAIL  — From address (default: noreply@guidewisey.com)
        EMAIL_SENDER_NAME   — From name    (default: FutureWise by GuideWisey)

    In DEV mode with no EMAIL_HOST_PASSWORD set, Django automatically falls back
    to the console backend — emails are printed to stdout, nothing is sent.
    """

    def __init__(self):
        self.sender_email: str = settings.EMAIL_SENDER_EMAIL
        self.sender_name: str = settings.EMAIL_SENDER_NAME
        self.from_addr: str = f"{self.sender_name} <{self.sender_email}>"

    # ── Public API ────────────────────────────────────────────────────────────

    def send_verification_email(self, to_email: str, verification_url: str) -> None:
        """Send a one-click email-verification link to an anonymous user."""
        html = render_to_string(
            "future_wise/verification_email.html",
            {"verification_url": verification_url, "to_email": to_email},
        )
        self._send(
            to_email=to_email,
            subject="Verify your email — FutureWise Reminder",
            html=html,
        )

    def send_reminder_email(
        self,
        reminder,
        attachment_data: Optional[list[dict]] = None,
    ) -> None:
        """
        Deliver the actual scheduled reminder to the user.

        attachment_data: list of dicts with keys:
            filename (str), content_bytes (bytes), content_type (str)
        """
        is_premium = reminder.tier == "premium"
        template = (
            "future_wise/reminder_email_premium.html"
            if is_premium
            else "future_wise/reminder_email_free.html"
        )
        html = render_to_string(template, {"reminder": reminder})

        email_msg = self._build_message(
            to_email=reminder.email,
            subject=reminder.subject,
            html=html,
        )

        if attachment_data:
            for att in attachment_data:
                email_msg.attach(
                    att["filename"],
                    att["content_bytes"],
                    att["content_type"],
                )

        self._deliver(email_msg)

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _send(self, to_email: str, subject: str, html: str) -> None:
        msg = self._build_message(to_email, subject, html)
        self._deliver(msg)

    def _build_message(
        self, to_email: str, subject: str, html: str
    ) -> EmailMultiAlternatives:
        # Plain-text fallback — strip HTML tags crudely
        import re
        plain = re.sub(r"<[^>]+>", "", html).strip()
        msg = EmailMultiAlternatives(
            subject=subject,
            body=plain,
            from_email=self.from_addr,
            to=[to_email],
        )
        msg.attach_alternative(html, "text/html")
        return msg

    def _deliver(self, msg: EmailMultiAlternatives) -> None:
        try:
            from django.conf import settings as django_settings
            logger.info(
                "Email backend=%s host=%s port=%s user=%s to=%s subject=%s",
                django_settings.EMAIL_BACKEND,
                django_settings.EMAIL_HOST,
                django_settings.EMAIL_PORT,
                django_settings.EMAIL_HOST_USER,
                msg.to,
                msg.subject,
            )
            msg.send(fail_silently=False)
            logger.info(
                "✅ Email delivered to=%s subject=%s", msg.to, msg.subject
            )
        except Exception as exc:
            logger.error("❌ Email delivery failed to=%s subject=%s error=%s", msg.to, msg.subject, exc)
            raise BrevoDeliveryError(f"Email delivery failed: {exc}") from exc


class BrevoDeliveryError(Exception):
    """Raised when email delivery fails."""
