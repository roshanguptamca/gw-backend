from dataclasses import dataclass

from ..models import BuddyProfile, BuddySettings


@dataclass
class BuddyContext:
    system_prompt: str
    prompt_data: dict


LANGUAGE_NAMES = {
    "en": "English",
    "nl": "Dutch",
    "hi": "Hindi",
    "ur": "Urdu",
    "ar": "Arabic",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "other": "the user's selected language",
}


def language_name(code: str) -> str:
    return LANGUAGE_NAMES.get(code or "", code or "the user's selected language")


def _unique_text_values(items):
    values = []
    for item in items:
        if isinstance(item, str):
            value = item.strip()
        elif isinstance(item, dict):
            value = str(item.get("text") or item.get("word") or item.get("title") or item.get("key") or "").strip()
        else:
            value = str(item).strip()
        if value and value not in values:
            values.append(value)
    return values


def build_session_context(
    profile: BuddyProfile, settings_obj: BuddySettings | None = None, limit: int = 5
) -> BuddyContext:
    settings_obj = settings_obj or getattr(profile, "buddy_settings", None)
    selected_avatar = getattr(settings_obj, "selected_avatar", None) if settings_obj else None
    recent_sessions = list(profile.sessions.order_by("-started_at")[:limit])
    recent_memories = list(profile.memories.filter(is_active=True).order_by("-updated_at")[:limit])
    recent_vocab = list(profile.vocabulary.order_by("-last_practiced_at", "-updated_at")[:limit])
    recent_mistakes = list(profile.mistakes.order_by("-created_at")[:limit])
    weak_areas = _unique_text_values(profile.weak_areas)
    favorite_topics = _unique_text_values(profile.favorite_topics)
    learned_words = _unique_text_values([item.word for item in recent_vocab])
    memory_snippets = []
    for memory in recent_memories:
        payload = memory.value if isinstance(memory.value, dict) else {"value": memory.value}
        memory_snippets.append(f"{memory.memory_type}:{memory.key}={payload}")
    selected_avatar_name = (
        getattr(selected_avatar, "name", "")
        or getattr(settings_obj, "selected_3d_avatar_slug", "")
        or "default AI avatar"
    )

    system_prompt = f"""
You are {profile.buddy_name}, an AI speaking buddy avatar for language practice.
You must never claim to be human or claim to be the uploaded person.
You are an AI buddy using the user's selected avatar.
Keep replies short, warm, and natural enough for conversation.
Do not interrupt the learner while they are still speaking.
Wait for a full thought and a clear pause before replying.
Brief pauses, filler words, and sentence restarts do not mean the turn is over.
If the learner is likely continuing, stay silent and keep listening.
Correct politely according to the user's correction style and level.
Encourage the user to speak more and ask follow-up questions.
Speak primarily in the target language: {language_name(profile.target_language)} ({profile.target_language}).
The user's native language is: {language_name(profile.native_language)} ({profile.native_language}).
If the target language is not English, continue in that language naturally.
If the user mixes languages, guide them gently without switching to English unless requested.
Current speaking level: {profile.speaking_level}.
Learning goal: {profile.learning_goal or "general speaking practice"}.
Personality: {getattr(settings_obj, "personality", "friendly") if settings_obj else "friendly"}.
Selected avatar: {selected_avatar_name}.
Voice style: {getattr(settings_obj, "voice_style", "warm") if settings_obj else "warm"}.
Correction level: {getattr(settings_obj, "correction_level", profile.preferred_correction_style)}.
Topic: {getattr(settings_obj, "default_topic", "") if settings_obj else ""}.
Weak areas: {", ".join(weak_areas) or "none"}.
Practice vocabulary: {", ".join(learned_words) or "none"}.
Favorite topics: {", ".join(favorite_topics) or "none"}.
Recent conversation summaries: {profile.previous_conversation_summary or "none"}.
Recent memory snippets: {memory_snippets and " | ".join(memory_snippets) or "none"}.
Recent sessions: {len(recent_sessions)}.
Stored memories: {len(recent_memories)}.
Recent mistakes: {len(recent_mistakes)}.
Safety rule: never pretend to be human or the uploaded person.
Safety rule: clearly remain an AI buddy/avatar.
""".strip()

    prompt_data = {
        "profile": {
            "buddy_name": profile.buddy_name,
            "native_language": profile.native_language,
            "target_language": profile.target_language,
            "native_language_name": language_name(profile.native_language),
            "target_language_name": language_name(profile.target_language),
            "speaking_level": profile.speaking_level,
            "learning_goal": profile.learning_goal,
            "favorite_topics": profile.favorite_topics,
            "weak_areas": profile.weak_areas,
            "preferred_correction_style": profile.preferred_correction_style,
            "is_memory_enabled": profile.is_memory_enabled,
        },
        "settings": {
            "personality": getattr(settings_obj, "personality", "friendly") if settings_obj else "friendly",
            "voice_style": getattr(settings_obj, "voice_style", "warm") if settings_obj else "warm",
            "voice_gender": getattr(settings_obj, "voice_gender", "neutral") if settings_obj else "neutral",
            "voice_age": getattr(settings_obj, "voice_age", "adult") if settings_obj else "adult",
            "speaking_speed": getattr(settings_obj, "speaking_speed", 50) if settings_obj else 50,
            "correction_level": getattr(settings_obj, "correction_level", profile.preferred_correction_style),
            "difficulty_level": getattr(settings_obj, "difficulty_level", "medium") if settings_obj else "medium",
            "theme_color": getattr(settings_obj, "theme_color", "#7c3aed") if settings_obj else "#7c3aed",
            "default_topic": getattr(settings_obj, "default_topic", "") if settings_obj else "",
            "selected_avatar": getattr(selected_avatar, "name", "")
            or getattr(settings_obj, "selected_3d_avatar_slug", ""),
            "turn_detection_mode": getattr(settings_obj, "turn_detection_mode", "auto") if settings_obj else "auto",
            "silence_timeout_ms": getattr(settings_obj, "silence_timeout_ms", 1600) if settings_obj else 1600,
            "min_speech_duration_ms": getattr(settings_obj, "min_speech_duration_ms", 1200) if settings_obj else 1200,
            "max_user_turn_seconds": getattr(settings_obj, "max_user_turn_seconds", 60) if settings_obj else 60,
            "enable_push_to_finish": getattr(settings_obj, "enable_push_to_finish", False) if settings_obj else False,
        },
        "recent_sessions": [
            {
                "id": session.id,
                "topic": session.topic,
                "language": session.language,
                "summary": session.ai_summary,
                "started_at": session.started_at.isoformat(),
                "ended_at": session.ended_at.isoformat() if session.ended_at else None,
            }
            for session in recent_sessions
        ],
        "recent_memories": [
            {
                "id": memory.id,
                "memory_type": memory.memory_type,
                "key": memory.key,
                "value": memory.value,
                "importance": memory.importance,
                "is_active": memory.is_active,
            }
            for memory in recent_memories
        ],
        "recent_vocab": [
            {
                "word": vocab.word,
                "translation": vocab.translation,
                "example_sentence": vocab.example_sentence,
                "language": vocab.language,
            }
            for vocab in recent_vocab
        ],
        "recent_mistakes": [
            {
                "original_text": mistake.original_text,
                "corrected_text": mistake.corrected_text,
                "explanation": mistake.explanation,
                "mistake_type": mistake.mistake_type,
                "language": mistake.language,
            }
            for mistake in recent_mistakes
        ],
    }
    return BuddyContext(system_prompt=system_prompt, prompt_data=prompt_data)
