from django.utils import timezone

from ..models import BuddyMemory, BuddyMistake, BuddyProfile, BuddySession, BuddyVocabulary


def _merge_unique(existing, values):
    items = []
    for value in list(existing or []) + list(values or []):
        if not value:
            continue
        text = str(value).strip()
        if text and text not in items:
            items.append(text)
    return items


def _ensure_memory(profile, memory_type, key, value, importance=2, session=None, is_active=True):
    memory, _ = BuddyMemory.objects.update_or_create(
        profile=profile,
        memory_type=memory_type,
        key=key,
        defaults={
            "value": value,
            "importance": importance,
            "source_session": session,
            "is_active": is_active,
        },
    )
    return memory


def update_session_insights(profile: BuddyProfile, session: BuddySession, insights: dict):
    if not profile.is_memory_enabled:
        return

    profile.previous_conversation_summary = insights.get("summary", profile.previous_conversation_summary)
    profile.weak_areas = _merge_unique(profile.weak_areas, insights.get("weak_areas", []))
    profile.favorite_topics = _merge_unique(profile.favorite_topics, insights.get("practice_topics", []))
    profile.save(update_fields=["previous_conversation_summary", "weak_areas", "favorite_topics", "updated_at"])

    _ensure_memory(profile, "summary", f"session-{session.id}-summary", {"text": insights.get("summary", "")}, importance=5, session=session)
    for area in insights.get("weak_areas", []):
        _ensure_memory(profile, "weak_area", str(area).lower(), {"text": area}, importance=4, session=session)
    for topic in insights.get("practice_topics", []):
        _ensure_memory(profile, "topic", str(topic).lower(), {"text": topic}, importance=3, session=session)
    for note in insights.get("improvement_notes", []):
        _ensure_memory(profile, "note", str(note).lower(), {"text": note}, importance=2, session=session)

    for item in insights.get("vocabulary", []):
        if not isinstance(item, dict):
            continue
        BuddyVocabulary.objects.update_or_create(
            profile=profile,
            word=item.get("word", "").strip(),
            language=item.get("language", profile.target_language),
            defaults={
                "translation": item.get("translation", ""),
                "example_sentence": item.get("example_sentence", ""),
                "confidence_score": int(item.get("confidence_score", 50) or 50),
                "last_practiced_at": timezone.now(),
            },
        )

    for item in insights.get("mistakes", []):
        if not isinstance(item, dict):
            continue
        BuddyMistake.objects.create(
            profile=profile,
            session=session,
            original_text=item.get("original_text", ""),
            corrected_text=item.get("corrected_text", ""),
            explanation=item.get("explanation", ""),
            mistake_type=item.get("mistake_type", ""),
            language=item.get("language", profile.target_language),
        )

