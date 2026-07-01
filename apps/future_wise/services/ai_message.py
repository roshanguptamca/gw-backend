import json
import logging
import re

from django.conf import settings

from apps.ai_services.providers import get_ai_providers
from apps.future_wise.models import EmailReminder

logger = logging.getLogger(__name__)

_CHANNEL_ALIASES = {"call": "voice", "voice_call": "voice"}
_DEFAULT_LANGUAGE = "English"


class AIMessageGenerationError(Exception):
    """Raised when reminder message generation is unavailable or fails."""


def _normalize_channels(channels) -> list[str]:
    normalized = []
    for channel in channels or []:
        code = _CHANNEL_ALIASES.get(str(channel).strip().lower(), str(channel).strip().lower())
        if code and code not in normalized:
            normalized.append(code)
    return normalized


def _clean_json_payload(value: str) -> dict:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", (value or "").strip(), flags=re.I)
    payload = json.loads(cleaned)
    if not isinstance(payload, dict):
        raise ValueError("AI reminder generator did not return a JSON object.")
    return payload


def _sanitize_generated_message(payload: dict, channels: list[str]) -> dict:
    result = {
        "subject": str(payload.get("subject", "")).strip()[:250],
        "email_body": str(payload.get("email_body", "")).strip(),
        "short_message": str(payload.get("short_message", "")).strip()[:1000],
        "call_script": str(payload.get("call_script", "")).strip()[:4000],
    }
    if "voice" not in channels:
        result["call_script"] = ""
    return result


def _build_system_prompt() -> str:
    return (
        "You write warm, practical Smart Reminder content for GuideWisey users. "
        "Return JSON only with exactly these keys: subject, email_body, short_message, call_script. "
        "Keep the subject concise, write an email body that is ready to edit, keep the short_message suitable "
        "for SMS/WhatsApp/Telegram, and make call_script sound natural for a brief voice reminder. "
        "Do not mention technical details, APIs, or placeholders unless the user provided them."
    )


def _build_user_prompt(
    *,
    letter_type: str,
    occasion: str,
    tone: str,
    recipient_name: str,
    language: str,
    channels: list[str],
    extra_context: str,
) -> str:
    metadata = EmailReminder.get_letter_type_metadata()
    type_info = metadata.get(letter_type or "", metadata.get(EmailReminder.LetterType.CUSTOM_MESSAGE, {}))
    return json.dumps(
        {
            "task": "Generate editable Smart Reminder content.",
            "brand": "GuideWisey Smart Reminders",
            "letter_type": letter_type or "",
            "letter_type_label": type_info.get("label", "Custom Message"),
            "letter_type_description": type_info.get("description", ""),
            "occasion": occasion or "General reminder",
            "tone": tone or "friendly and thoughtful",
            "recipient_name": recipient_name or "",
            "language": language or _DEFAULT_LANGUAGE,
            "channels": channels or ["email"],
            "extra_context": extra_context or "",
            "voice_requested": "voice" in channels,
            "requirements": {
                "subject_max_length": 250,
                "email_body_style": "2-5 short paragraphs",
                "short_message_style": "single concise message",
                "call_script_style": "30-60 seconds when voice_requested is true, otherwise empty string",
            },
        },
        ensure_ascii=False,
    )


def generate_reminder_message(
    letter_type,
    occasion="",
    tone="",
    recipient_name="",
    language="",
    channels=None,
    extra_context="",
):
    channels = _normalize_channels(channels) or ["email"]
    system_prompt = _build_system_prompt()
    user_prompt = _build_user_prompt(
        letter_type=letter_type,
        occasion=occasion,
        tone=tone,
        recipient_name=recipient_name,
        language=language,
        channels=channels,
        extra_context=extra_context,
    )

    providers = get_ai_providers()
    if not providers:
        message = "AI message generation is currently unavailable. Please write your message manually."
        if settings.DEBUG:
            logger.info("AI reminder generation unavailable: no configured AI providers.")
        raise AIMessageGenerationError(message)

    last_error = None
    for provider_name, provider in providers:
        try:
            payload = _clean_json_payload(provider.generate(system_prompt, user_prompt))
            return _sanitize_generated_message(payload, channels)
        except Exception as exc:  # pragma: no cover - exercised via mocked provider failures
            last_error = exc
            logger.warning("Reminder AI generation with %s failed; trying fallback: %s", provider_name, exc)

    raise AIMessageGenerationError(
        "AI message generation is currently unavailable. Please write your message manually."
    ) from last_error
