"""
Email backends for GuideWisey.

Two backends are provided:

1. BrevoAPIEmailBackend  (RECOMMENDED for production / Render)
   Uses the Brevo Transactional Email REST API over HTTPS (port 443).
   Render and most cloud hosts block outbound SMTP (port 587/465/25).
   HTTPS is never blocked, so this backend works everywhere.

   Required env var:
       BREVO_API_KEY   — your Brevo API key (from Brevo dashboard → API Keys)

2. CertifiSMTPEmailBackend  (kept for local / legacy use)
   Standard Django SMTP backend patched to use certifi's CA bundle.
   Works locally where port 587 is open.
"""

import logging

import certifi
import requests
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend
from django.core.mail.backends.smtp import EmailBackend

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Brevo HTTP API backend
# ──────────────────────────────────────────────────────────────────────────────

_BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"
_BREVO_TIMEOUT = 15  # seconds — HTTPS is fast, no reason to wait longer


class BrevoAPIEmailBackend(BaseEmailBackend):
    """Send email via Brevo Transactional API (HTTPS).

    Advantages over SMTP on Render:
      - Uses port 443 — never firewalled.
      - No persistent TCP connection; each send is a short HTTPS POST.
      - Faster and more reliable than SMTP on cloud-hosted dynos.

    Configure in settings.py:
        EMAIL_BACKEND = "guidewisey.email_backend.BrevoAPIEmailBackend"
        BREVO_API_KEY = os.getenv("BREVO_API_KEY", "")
    """

    def send_messages(self, email_messages):
        api_key = getattr(settings, "BREVO_API_KEY", "") or ""
        if not api_key:
            logger.error("BrevoAPIEmailBackend: BREVO_API_KEY not set — emails skipped.")
            return 0

        sent = 0
        for msg in email_messages:
            # Parse sender — "Name <email>" or plain email
            from_email = msg.from_email or settings.DEFAULT_FROM_EMAIL
            if "<" in from_email:
                name_part, addr_part = from_email.split("<", 1)
                sender = {"name": name_part.strip(), "email": addr_part.rstrip(">")}
            else:
                sender = {"email": from_email}

            payload = {
                "sender": sender,
                "to": [{"email": r} for r in msg.to],
                "subject": msg.subject,
                "textContent": msg.body or " ",
            }

            # Attach HTML alternative if present
            for content, mimetype in getattr(msg, "alternatives", []):
                if mimetype == "text/html":
                    payload["htmlContent"] = content
                    break

            # CC / BCC
            if msg.cc:
                payload["cc"] = [{"email": r} for r in msg.cc]
            if msg.bcc:
                payload["bcc"] = [{"email": r} for r in msg.bcc]

            try:
                resp = requests.post(
                    _BREVO_API_URL,
                    headers={
                        "api-key": api_key,
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    },
                    json=payload,
                    timeout=_BREVO_TIMEOUT,
                    verify=certifi.where(),
                )
                if resp.status_code in (200, 201):
                    sent += 1
                    logger.debug("Brevo API: sent to %s (status %s)", msg.to, resp.status_code)
                else:
                    logger.error(
                        "Brevo API: failed for %s — HTTP %s: %s",
                        msg.to,
                        resp.status_code,
                        resp.text[:200],
                    )
                    if not self.fail_silently:
                        raise RuntimeError(f"Brevo API error {resp.status_code}: {resp.text[:200]}")
            except requests.RequestException as exc:
                logger.exception("Brevo API: request error for %s — %s", msg.to, exc)
                if not self.fail_silently:
                    raise

        return sent


# ──────────────────────────────────────────────────────────────────────────────
# Legacy SMTP backend (local dev / fallback)
# ──────────────────────────────────────────────────────────────────────────────

import ssl  # noqa: E402  (after third-party imports)

_DEFAULT_SMTP_TIMEOUT = 10  # reduced from 30 — fail fast on blocked ports


class CertifiSMTPEmailBackend(EmailBackend):
    """SMTP backend that trusts certifi's CA bundle for TLS verification.

    Use this locally where port 587 is open.
    On Render / cloud, use BrevoAPIEmailBackend instead.
    """

    def open(self):
        if self.connection:
            return False

        import smtplib

        connection_params = {"local_hostname": None}
        connection_params["timeout"] = self.timeout if self.timeout is not None else _DEFAULT_SMTP_TIMEOUT

        if self.use_ssl:
            connection_params["context"] = ssl.create_default_context(cafile=certifi.where())

        try:
            self.connection = self.connection_class(self.host, self.port, **connection_params)

            if self.use_tls:
                ctx = ssl.create_default_context(cafile=certifi.where())
                self.connection.ehlo()
                self.connection.starttls(context=ctx)
                self.connection.ehlo()

            if self.username and self.password:
                self.connection.login(self.username, self.password)
            return True
        except smtplib.SMTPException:
            if not self.fail_silently:
                raise
