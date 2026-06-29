"""
TelegramReminderProvider — delivers reminder via Telegram Bot API.

Free and unrestricted. No trial limitations.

The user's telegram_chat_id is captured when they send /start to the
Telegram bot. It is stored in UserNotificationPreference.telegram_chat_id
and also on EmailReminder.telegram_chat_id for direct lookups.

Required settings:
    TELEGRAM_BOT_TOKEN — from @BotFather e.g. 123456789:AAF-your-token

Bot setup:
    1. Message @BotFather on Telegram
    2. /newbot → follow prompts → copy the token
    3. Set TELEGRAM_BOT_TOKEN in .env
    4. Register webhook: POST https://api.telegram.org/bot<TOKEN>/setWebhook
       with url = https://<your-domain>/api/future-wise/telegram/webhook/
"""

import logging

from django.conf import settings

import requests

from .base import DeliveryResult, IReminderProvider

logger = logging.getLogger(__name__)

_API_URL = "https://api.telegram.org/bot{token}/sendMessage"


class TelegramReminderProvider(IReminderProvider):
    channel_code = "telegram"

    def is_available(self, recipient_context: dict) -> bool:
        return bool(recipient_context.get("telegram_chat_id"))

    def send(self, reminder, recipient_context: dict) -> DeliveryResult:
        chat_id = recipient_context["telegram_chat_id"]
        text = self._build_text(reminder)
        url = _API_URL.format(token=settings.TELEGRAM_BOT_TOKEN)
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": False,
        }

        try:
            resp = requests.post(url, json=payload, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            msg_id = str(data.get("result", {}).get("message_id", ""))
            logger.info(
                "TelegramReminderProvider: delivered reminder=%s chat_id=%s msg_id=%s",
                reminder.id,
                chat_id,
                msg_id,
            )
            return DeliveryResult(
                success=True,
                provider_message_id=msg_id,
                provider_response=str(data)[:500],
            )
        except requests.HTTPError as exc:
            status_code = exc.response.status_code if exc.response is not None else 0
            body = exc.response.text[:300] if exc.response is not None else ""
            # 400 Bad Request from Telegram means invalid chat_id — permanent failure
            is_permanent = status_code == 400
            logger.warning(
                "TelegramReminderProvider: HTTPError reminder=%s status=%s permanent=%s body=%s",
                reminder.id,
                status_code,
                is_permanent,
                body,
            )
            return DeliveryResult(
                success=False,
                error_message=f"HTTP {status_code}: {body}"[:1000],
                is_permanent_failure=is_permanent,
            )
        except requests.ConnectionError as exc:
            logger.error(
                "TelegramReminderProvider: ConnectionError reminder=%s error=%s",
                reminder.id,
                exc,
            )
            return DeliveryResult(success=False, error_message=f"Connection error: {exc}"[:1000])
        except Exception as exc:
            logger.error(
                "TelegramReminderProvider: unexpected error reminder=%s error=%s",
                reminder.id,
                exc,
            )
            return DeliveryResult(success=False, error_message=f"Unexpected: {exc}"[:1000])

    def _build_text(self, reminder) -> str:
        brand = reminder.brand_name
        subject = reminder.subject[:200]
        # Truncate message for preview; full letter is on the site
        excerpt = reminder.message[:300].strip()
        ellipsis = "..." if len(reminder.message) > 300 else ""
        return (
            f"*{brand}* 📬\n\n"
            f"*{subject}*\n\n"
            f"{excerpt}{ellipsis}\n\n"
            f"[Read your full letter on GuideWisey](https://www.guidewisey.com)"
        )
