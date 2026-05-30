"""
Transactional email service for FutureWise.

Delivery strategy (tried in order):
  1. Brevo HTTP API  — if BREVO_API_KEY is set (works on Render free tier, port 443)
  2. Django SMTP     — fallback for local dev or environments where SMTP is open
  3. Console backend — local dev with no credentials (prints to stdout)

Render's free tier blocks outbound SMTP (port 587), so the HTTP API path
is always used in production when BREVO_API_KEY is set.
"""

import base64
import logging
import re
from typing import Optional

import requests
from django.conf import settings
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)

_BREVO_SEND_URL = "https://api.brevo.com/v3/smtp/email"


class BrevoEmailService:
    """
    Sends transactional emails via Brevo HTTP API (preferred) or Django SMTP.

    Required settings (set via .env):
        BREVO_API_KEY       — Brevo API key (uses HTTP API, works on Render free tier)
        EMAIL_SENDER_EMAIL  — From address (default: noreply@guidewisey.com)
        EMAIL_SENDER_NAME   — From name    (default: FutureWise by GuideWisey)

    SMTP fallback (local dev):
        EMAIL_HOST / EMAIL_PORT / EMAIL_HOST_USER / EMAIL_HOST_PASSWORD
    """

    def __init__(self):
        self.sender_email: str = settings.EMAIL_SENDER_EMAIL
        self.sender_name: str = settings.EMAIL_SENDER_NAME
        self.from_addr: str = f"{self.sender_name} <{self.sender_email}>"
        self.api_key: str = getattr(settings, "BREVO_API_KEY", "")

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
        template = "future_wise/reminder_email_premium.html" if is_premium else "future_wise/reminder_email_free.html"
        html = render_to_string(template, {"reminder": reminder})
        self._send(
            to_email=reminder.email,
            subject=reminder.subject,
            html=html,
            attachment_data=attachment_data,
        )

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _send(
        self,
        to_email: str,
        subject: str,
        html: str,
        attachment_data: Optional[list[dict]] = None,
    ) -> None:
        if self.api_key:
            self._deliver_via_api(to_email, subject, html, attachment_data)
        else:
            self._deliver_via_smtp(to_email, subject, html, attachment_data)

    def _deliver_via_api(
        self,
        to_email: str,
        subject: str,
        html: str,
        attachment_data: Optional[list[dict]] = None,
    ) -> None:
        """Send via Brevo HTTP API (port 443 — works on Render free tier)."""
        plain = re.sub(r"<[^>]+>", "", html).strip()
        payload = {
            "sender": {"name": self.sender_name, "email": self.sender_email},
            "to": [{"email": to_email}],
            "subject": subject,
            "htmlContent": html,
            "textContent": plain,
        }

        if attachment_data:
            payload["attachment"] = [
                {
                    "name": att["filename"],
                    "content": base64.b64encode(att["content_bytes"]).decode(),
                }
                for att in attachment_data
            ]

        headers = {
            "api-key": self.api_key,
            "Content-Type": "application/json",
        }

        logger.info(
            "Email via Brevo API to=%s subject=%s sender=%s",
            to_email, subject, self.sender_email,
        )
        try:
            resp = requests.post(_BREVO_SEND_URL, json=payload, headers=headers, timeout=30)
            resp.raise_for_status()
            logger.info("✅ Email delivered (Brevo API) to=%s subject=%s", to_email, subject)
        except requests.RequestException as exc:
            body = getattr(exc.response, "text", "") if hasattr(exc, "response") else ""
            logger.error("❌ Brevo API delivery failed to=%s error=%s body=%s", to_email, exc, body)
            raise BrevoDeliveryError(f"Brevo API delivery failed: {exc}") from exc

    def _deliver_via_smtp(
        self,
        to_email: str,
        subject: str,
        html: str,
        attachment_data: Optional[list[dict]] = None,
    ) -> None:
        """Send via Django SMTP backend (local dev fallback)."""
        from django.core.mail import EmailMultiAlternatives

        plain = re.sub(r"<[^>]+>", "", html).strip()
        msg = EmailMultiAlternatives(
            subject=subject,
            body=plain,
            from_email=self.from_addr,
            to=[to_email],
        )
        msg.attach_alternative(html, "text/html")

        if attachment_data:
            for att in attachment_data:
                msg.attach(att["filename"], att["content_bytes"], att["content_type"])

        logger.info(
            "Email via SMTP backend=%s host=%s:%s to=%s subject=%s",
            settings.EMAIL_BACKEND, settings.EMAIL_HOST, settings.EMAIL_PORT,
            to_email, subject,
        )
        try:
            msg.send(fail_silently=False)
            logger.info("✅ Email delivered (SMTP) to=%s subject=%s", to_email, subject)
        except Exception as exc:
            logger.error("❌ SMTP delivery failed to=%s subject=%s error=%s", to_email, subject, exc)
            raise BrevoDeliveryError(f"Email delivery failed: {exc}") from exc


class BrevoDeliveryError(Exception):
    """Raised when email delivery fails."""

