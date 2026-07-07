import json
import logging

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


def _eagerness_from_silence_timeout(silence_timeout_ms: int) -> str:
    """Map the tunable "silence timeout" setting onto Semantic VAD's eagerness
    levels so the existing per-user setting still has an effect: shorter
    timeouts respond faster (high eagerness), longer timeouts wait longer for
    the user to finish a thought (low eagerness)."""
    if silence_timeout_ms <= 600:
        return "high"
    if silence_timeout_ms >= 1200:
        return "low"
    return "auto"


def create_realtime_client_secret(context: BuddyContext, *, selected_voice="marin", buddy_session_id=None):
    client = _client()
    settings_data = context.prompt_data.get("settings", {}) if context and context.prompt_data else {}
    profile_data = context.prompt_data.get("profile", {}) if context and context.prompt_data else {}
    turn_detection_mode = str(settings_data.get("turn_detection_mode") or "auto").lower()
    silence_timeout_ms = int(settings_data.get("silence_timeout_ms") or 900)
    create_response = turn_detection_mode == "auto"
    eagerness = _eagerness_from_silence_timeout(silence_timeout_ms)
    target_language = profile_data.get("target_language") or "en"
    debug_metadata = {
        "buddy_session_id": buddy_session_id,
        "selected_voice": selected_voice,
        "audio_source": "openai_realtime",
        "turn_detection_mode": turn_detection_mode,
        "silence_timeout_ms": silence_timeout_ms,
    }
    logger.info(
        "Speaking buddy realtime token: session_id=%s selected_voice=%s "
        "audio_source=%s turn_detection_mode=%s silence_timeout_ms=%s eagerness=%s",
        buddy_session_id,
        selected_voice,
        debug_metadata["audio_source"],
        turn_detection_mode,
        silence_timeout_ms,
        eagerness,
    )
    if client is None:
        return {
            "client_secret": "dev-realtime-secret",
            "value": "dev-realtime-secret",
            "session_id": "dev-session",
            "expires_at": None,
            **debug_metadata,
        }

    try:
        response = client.realtime.client_secrets.create(
            expires_after={"anchor": "created_at", "seconds": 600},
            session={
                "type": "realtime",
                "model": getattr(settings, "SPEAKING_BUDDY_REALTIME_MODEL", "gpt-realtime-2"),
                "audio": {
                    "output": {"voice": selected_voice},
                    "input": {
                        # Semantic VAD uses a model to judge whether the
                        # learner has actually finished a thought (instead of
                        # a fixed silence window), which is both more
                        # human-like and less likely to cut the user off or
                        # end the call mid-sentence. interrupt_response lets
                        # the learner naturally talk over the AI, like a real
                        # conversation partner would allow.
                        "turn_detection": {
                            "type": "semantic_vad",
                            "eagerness": eagerness,
                            "create_response": create_response,
                            "interrupt_response": True,
                        },
                        # near_field noise reduction and a dedicated
                        # transcription model improve recognition accuracy in
                        # noisy environments and give more reliable
                        # transcripts for the on-screen captions.
                        "noise_reduction": {"type": "near_field"},
                        "transcription": {
                            "model": "gpt-4o-mini-transcribe",
                            "language": target_language,
                        },
                    },
                },
                "instructions": context.system_prompt,
            },
        )
        if hasattr(response, "model_dump"):
            payload = response.model_dump()
            payload.setdefault("client_secret", payload.get("value"))
            payload.update(debug_metadata)
            return payload
        if isinstance(response, dict):
            response.setdefault("client_secret", response.get("value"))
            response.update(debug_metadata)
            return response
        client_secret = getattr(response, "client_secret", getattr(response, "value", ""))
        return {
            "client_secret": client_secret,
            "value": getattr(response, "value", client_secret),
            "session_id": getattr(response, "session_id", ""),
            **debug_metadata,
        }
    except Exception as exc:
        logger.warning("Speaking buddy realtime token creation failed: %s", exc)
        raise SpeakingBuddyError("realtime_token_failed") from exc
