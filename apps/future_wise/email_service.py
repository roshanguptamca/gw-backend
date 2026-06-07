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

    def send_account_confirmation_email(self, to_email: str, confirmation_url: str) -> None:
        """Send an account email-confirmation link after user registration."""
        html = render_to_string(
            "accounts/confirmation_email.html",
            {"confirmation_url": confirmation_url, "to_email": to_email},
        )
        self._send(
            to_email=to_email,
            subject="Confirm your email — GuideWisey",
            html=html,
        )

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

        The email template is chosen based on reminder.letter_type (falls back
        to the free FutureWise template for legacy/unknown types).

        attachment_data: list of dicts with keys:
            filename (str), content_bytes (bytes), content_type (str)
        """
        template = self._pick_template(reminder)
        logger.debug(
            "FutureWise: send_reminder_email id=%s letter_type=%s template=%s",
            getattr(reminder, "id", "?"),
            getattr(reminder, "letter_type", "?"),
            template,
        )
        html = render_to_string(template, {"reminder": reminder})
        self._send(
            to_email=reminder.email,
            subject=reminder.subject,
            html=html,
            attachment_data=attachment_data,
        )

    # ── Template selection ────────────────────────────────────────────────────

    def _pick_template(self, reminder) -> str:
        """Return the HTML template path for this reminder's letter_type and tier."""
        from .models import EmailReminder as ER

        letter_type = getattr(reminder, "letter_type", ER.LetterType.FUTURE_SELF)
        is_premium = getattr(reminder, "tier", "free") == "premium"

        template_map = {
            ER.LetterType.FUTURE_SELF: (
                "future_wise/reminder_email_premium.html" if is_premium else "future_wise/reminder_email_free.html"
            ),
            ER.LetterType.MILESTONE: "future_wise/reminder_email_milestone.html",
            ER.LetterType.GRIEF: "future_wise/reminder_email_grief.html",
            ER.LetterType.FORGIVENESS: "future_wise/reminder_email_forgiveness.html",
            ER.LetterType.GRATITUDE: "future_wise/reminder_email_gratitude.html",
        }
        chosen = template_map.get(letter_type, "future_wise/reminder_email_free.html")
        logger.debug("_pick_template: letter_type=%s → %s", letter_type, chosen)
        return chosen

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _send(
        self,
        to_email: str,
        subject: str,
        html: str,
        attachment_data: Optional[list[dict]] = None,
    ) -> None:
        if self.api_key:
            logger.info(
                "FutureWise: delivery path=Brevo_API to=%s attachments=%d",
                to_email,
                len(attachment_data) if attachment_data else 0,
            )
            try:
                self._deliver_via_api(to_email, subject, html, attachment_data)
                return
            except BrevoDeliveryError as exc:
                # 401 means this IP isn't whitelisted in Brevo (common in local dev).
                # Fall back to SMTP so development works without IP whitelisting.
                if "401" in str(exc):
                    logger.warning(
                        "Brevo API returned 401 (IP not whitelisted) — falling back to SMTP for to=%s",
                        to_email,
                    )
                else:
                    raise

        logger.info(
            "FutureWise: delivery path=SMTP host=%s:%s to=%s attachments=%d",
            settings.EMAIL_HOST,
            settings.EMAIL_PORT,
            to_email,
            len(attachment_data) if attachment_data else 0,
        )
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
            "Brevo API: POST %s to=%s sender=%s",
            _BREVO_SEND_URL,
            to_email,
            self.sender_email,
        )
        try:
            resp = requests.post(_BREVO_SEND_URL, json=payload, headers=headers, timeout=30)
            logger.debug("Brevo API: response status=%s body=%s", resp.status_code, resp.text[:300])
            resp.raise_for_status()
            message_id = resp.json().get("messageId", "?")
            logger.info("✅ Brevo API delivered to=%s messageId=%s", to_email, message_id)
        except requests.HTTPError as exc:
            body = exc.response.text[:500] if exc.response is not None else ""
            logger.error(
                "❌ Brevo API HTTP error to=%s status=%s body=%s",
                to_email,
                exc.response.status_code if exc.response is not None else "?",
                body,
            )
            raise BrevoDeliveryError(
                f"Brevo API HTTP error {exc.response.status_code if exc.response is not None else '?'}: {body}"
            ) from exc
        except requests.RequestException as exc:
            logger.error("❌ Brevo API request failed to=%s error=%s", to_email, exc)
            raise BrevoDeliveryError(f"Brevo API request failed: {exc}") from exc

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
            "Email via SMTP backend=%s host=%s:%s to=%s",
            settings.EMAIL_BACKEND,
            settings.EMAIL_HOST,
            settings.EMAIL_PORT,
            to_email,
        )
        try:
            msg.send(fail_silently=False)
            logger.info("✅ Email delivered (SMTP) to=%s", to_email)
        except Exception as exc:
            logger.error("❌ SMTP delivery failed to=%s error=%s", to_email, exc)
            raise BrevoDeliveryError(f"Email delivery failed: {exc}") from exc


class BrevoDeliveryError(Exception):
    """Raised when email delivery fails."""
