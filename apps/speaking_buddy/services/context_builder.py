from dataclasses import dataclass

from django.db.models import Q
from django.utils import timezone

from ..models import BuddyProfile, BuddySettings


def models_q_due(now):
    """Vocabulary is 'due' when it has no scheduled review yet or the
    scheduled review time has already passed."""
    return Q(next_review_at__isnull=True) | Q(next_review_at__lte=now)


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
    # Prefer vocabulary that is due for review (next_review_at in the past,
    # or never reviewed / not yet mastered) so the buddy naturally reuses
    # words the learner still needs to practice, falling back to recency.
    now = timezone.now()
    due_vocab = list(
        profile.vocabulary.exclude(review_status="mastered")
        .filter(models_q_due(now))
        .order_by("next_review_at", "-updated_at")[:limit]
    )
    if len(due_vocab) < limit:
        seen_ids = {item.id for item in due_vocab}
        extra = [
            item
            for item in profile.vocabulary.order_by("-last_practiced_at", "-updated_at")[: limit * 2]
            if item.id not in seen_ids
        ][: limit - len(due_vocab)]
        due_vocab.extend(extra)
    recent_vocab = due_vocab
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
    memory_enabled = bool(profile.is_memory_enabled)
    if not memory_enabled:
        # Do not leak prior-session context into the prompt when memory is disabled.
        weak_areas = []
        learned_words = []
        memory_snippets = []
        recent_memories = []
        previous_summary = "none (memory disabled)"
    else:
        previous_summary = profile.previous_conversation_summary or "none"

    difficulty_level = getattr(settings_obj, "difficulty_level", "medium") if settings_obj else "medium"
    speaking_speed = getattr(settings_obj, "speaking_speed", 50) if settings_obj else 50
    voice_gender = getattr(settings_obj, "voice_gender", "neutral") if settings_obj else "neutral"
    voice_age = getattr(settings_obj, "voice_age", "adult") if settings_obj else "adult"
    if speaking_speed <= 40:
        speaking_speed_instruction = "Speak noticeably slower than normal and pause between phrases."
    elif speaking_speed >= 70:
        speaking_speed_instruction = "Speak a bit faster and more fluidly than a beginner pace."
    else:
        speaking_speed_instruction = "Speak at a natural, normal conversational pace."
    difficulty_instruction = {
        "easy": "Use simple vocabulary, short sentences, and avoid idioms or complex grammar.",
        "medium": "Use everyday vocabulary and moderately complex sentences.",
        "hard": "Use rich vocabulary, idioms, and more complex sentence structures.",
    }.get(difficulty_level, "Use everyday vocabulary and moderately complex sentences.")

    system_prompt = f"""
You are {profile.buddy_name}, an AI speaking buddy avatar for language practice.
You must never claim to be human or claim to be the uploaded person.
You are an AI buddy using the user's selected avatar.
Keep replies short, warm, and natural enough for conversation.
Reply naturally and briefly. Do not be slow. Respond as soon as the learner
finishes a thought instead of pausing or over-explaining.
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
Voice gender: {voice_gender}. Voice age: {voice_age}.
Difficulty level: {difficulty_level}. {difficulty_instruction}
Speaking speed preference: {speaking_speed}/120. {speaking_speed_instruction}
Correction level: {getattr(settings_obj, "correction_level", profile.preferred_correction_style)}.
Topic: {getattr(settings_obj, "default_topic", "") if settings_obj else ""}.
Memory: {"enabled" if memory_enabled else "disabled"}.
Weak areas: {", ".join(weak_areas) or "none"}.
Practice vocabulary: {", ".join(learned_words) or "none"}.
Favorite topics: {", ".join(favorite_topics) or "none"}.
Recent conversation summaries: {previous_summary}.
Recent memory snippets: {memory_snippets and " | ".join(memory_snippets) or "none"}.
Recent sessions: {len(recent_sessions)}.
Stored memories: {len(recent_memories)}.
Recent mistakes: {len(recent_mistakes)}.
Safety rule: never pretend to be human or the uploaded person.
Safety rule: clearly remain an AI buddy/avatar.
Goodbye rule: if the learner says goodbye/farewell in any language (e.g. "bye",
"goodbye", "doei", "tot ziens", "अलविदा", "au revoir", "adiós", "tschüss", "ciao"),
respond with one brief, warm goodbye line (e.g. "Nice talking with you. See you
next time!") and do not ask another question.
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
            "silence_timeout_ms": getattr(settings_obj, "silence_timeout_ms", 900) if settings_obj else 900,
            "min_speech_duration_ms": getattr(settings_obj, "min_speech_duration_ms", 500) if settings_obj else 500,
            "max_user_turn_seconds": getattr(settings_obj, "max_user_turn_seconds", 45) if settings_obj else 45,
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
                "review_status": vocab.review_status,
                "next_review_at": vocab.next_review_at.isoformat() if vocab.next_review_at else None,
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
