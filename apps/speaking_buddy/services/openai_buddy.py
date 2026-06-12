import json
import logging
from dataclasses import asdict

from django.conf import settings
from openai import OpenAI

from .context_builder import BuddyContext, language_name

logger = logging.getLogger(__name__)


class SpeakingBuddyError(Exception):
    def __init__(self, code, message=None):
        self.code = code
        super().__init__(message or code)


def _client():
    if not settings.OPENAI_API_KEY:
        if settings.DEBUG:
            return None
        raise SpeakingBuddyError("openai_not_configured")
    return OpenAI(api_key=settings.OPENAI_API_KEY)


def _fallback_reply(context: BuddyContext, user_message: str):
    language = context.prompt_data["profile"]["target_language"]
    replies = {
        "en": "I’m your AI buddy. Try saying that again a little slower so I can help.",
        "nl": "Ik ben je AI buddy. Probeer dezelfde zin nog eens, maar iets langzamer.",
        "hi": "मैं आपका AI buddy हूँ। कृपया वही वाक्य थोड़ा धीरे दोहराएँ।",
        "ur": "میں آپ کا AI buddy ہوں۔ براہِ کرم وہی جملہ ذرا آہستہ دہرائیں۔",
        "ar": "أنا AI buddy الخاص بك. حاول أن تقول الجملة مرة أخرى ببطء قليلًا.",
        "es": "Soy tu AI buddy. Intenta decirlo otra vez un poco más despacio.",
        "fr": "Je suis votre AI buddy. Essayez de le redire un peu plus lentement.",
        "de": "Ich bin dein AI Buddy. Versuch es bitte noch einmal etwas langsamer.",
    }
    if language in replies:
        return replies[language]
    return f"I’m your AI buddy in {language_name(language)}. Try saying that again a little slower so I can help."


def _fallback_summary(context: BuddyContext, transcript: list):
    text = "Session completed with " + str(len(transcript)) + " turns."
    return {
        "summary": text,
        "weak_areas": context.prompt_data["profile"].get("weak_areas", []),
        "practice_topics": [context.prompt_data["settings"].get("default_topic") or "General speaking"],
        "improvement_notes": ["Keep answers a little longer and use more target-language phrases."],
        "vocabulary": [],
        "mistakes": [],
        "user_summary": "Practiced speaking and received feedback.",
    }


def generate_buddy_reply(context: BuddyContext, user_message: str, transcript: list):
    client = _client()
    if client is None:
        return _fallback_reply(context, user_message)

    messages = [{"role": "system", "content": context.system_prompt}]
    for item in transcript[-8:]:
        role = item.get("role")
        text = item.get("text", "")
        if role in {"user", "assistant", "system"} and text:
            messages.append({"role": role, "content": text})
    messages.append({"role": "user", "content": user_message})

    try:
        response = client.chat.completions.create(
            model=getattr(settings, "SPEAKING_BUDDY_MODEL", "gpt-4o-mini"),
            messages=messages,
            temperature=0.6,
        )
        return response.choices[0].message.content.strip()
    except Exception as exc:
        logger.warning("Speaking buddy reply failed: %s", exc)
        return _fallback_reply(context, user_message)


def summarize_session(context: BuddyContext, transcript: list):
    client = _client()
    if client is None:
        return _fallback_summary(context, transcript)

    prompt = {
        "instruction": "Summarize the speaking practice session and return JSON only.",
        "context": context.prompt_data,
        "transcript": transcript,
        "required_fields": [
            "summary",
            "weak_areas",
            "practice_topics",
            "improvement_notes",
            "vocabulary",
            "mistakes",
            "user_summary",
        ],
        "safety": "Never claim to be human or the uploaded person.",
    }
    try:
        response = client.chat.completions.create(
            model=getattr(settings, "SPEAKING_BUDDY_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": context.system_prompt},
                {"role": "user", "content": json.dumps(prompt)},
            ],
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        payload = json.loads(response.choices[0].message.content)
        payload.setdefault("user_summary", "")
        payload.setdefault("summary", "")
        payload.setdefault("weak_areas", [])
        payload.setdefault("practice_topics", [])
        payload.setdefault("improvement_notes", [])
        payload.setdefault("vocabulary", [])
        payload.setdefault("mistakes", [])
        return payload
    except Exception as exc:
        logger.warning("Speaking buddy summary failed: %s", exc)
        return _fallback_summary(context, transcript)


def create_realtime_client_secret(context: BuddyContext):
    client = _client()
    if client is None:
        return {
            "client_secret": "dev-realtime-secret",
            "value": "dev-realtime-secret",
            "session_id": "dev-session",
            "expires_at": None,
        }

    try:
        response = client.realtime.client_secrets.create(
            expires_after={"anchor": "created_at", "seconds": 600},
            session={
                "type": "realtime",
                "model": getattr(settings, "SPEAKING_BUDDY_MODEL", "gpt-4o-mini"),
                "modalities": ["audio", "text"],
                "instructions": context.system_prompt,
            },
        )
        if hasattr(response, "model_dump"):
            payload = response.model_dump()
            payload.setdefault("client_secret", payload.get("value"))
            return payload
        if isinstance(response, dict):
            response.setdefault("client_secret", response.get("value"))
            return response
        client_secret = getattr(response, "client_secret", getattr(response, "value", ""))
        return {
            "client_secret": client_secret,
            "value": getattr(response, "value", client_secret),
            "session_id": getattr(response, "session_id", ""),
        }
    except Exception as exc:
        logger.warning("Speaking buddy realtime token creation failed: %s", exc)
        raise SpeakingBuddyError("realtime_token_failed") from exc
