"""Formalizes AI Buddy's "personalization from history" behavior as a
dedicated service, on top of :func:`context_builder.build_session_context`.

This exists mainly to give the personalization concern a clear, testable
surface (per product spec) rather than duplicating the context-building
logic: it decides *what* history to surface and *whether* memory is enabled,
and delegates prompt construction to ``context_builder``.
"""

from .context_builder import build_session_context
from .continuity_service import BuddyContinuityService


class BuddyPersonalizationService:
    """Builds the personalization payload used to seed a new session."""

    def __init__(self, profile, settings_obj=None):
        self.profile = profile
        self.settings_obj = settings_obj

    def build_context(self, limit: int = 5):
        """Return the BuddyContext (system prompt + prompt_data) enriched
        with recent sessions/memories/vocabulary/mistakes, respecting the
        user's memory-enabled preference."""
        return build_session_context(self.profile, self.settings_obj, limit=limit)

    def get_continuity(self):
        """Return the continuity data (last session summary + recommended
        continuation) used to personalize greetings and follow-up
        questions. Returns empty/None values when memory is disabled."""
        continuity = BuddyContinuityService(self.profile)
        return {
            "memory_enabled": bool(self.profile.is_memory_enabled),
            "last_session_summary": continuity.get_last_session_summary(),
            "recommended_continuation": continuity.get_recommended_continuation(),
        }

    def get_personalization_summary(self, limit: int = 5):
        """Return a compact summary of the data used to personalize the
        conversation: recent topics, weak areas, vocabulary due for review,
        mistakes, and the learner's stated goal. Useful for tests/UI without
        needing the full LLM system prompt."""
        context = self.build_context(limit=limit)
        data = context.prompt_data
        return {
            "learning_goal": data["profile"]["learning_goal"],
            "favorite_topics": data["profile"]["favorite_topics"],
            "weak_areas": data["profile"]["weak_areas"],
            "recent_sessions": data["recent_sessions"],
            "recent_vocab": data["recent_vocab"],
            "recent_mistakes": data["recent_mistakes"],
            "memory_enabled": data["profile"]["is_memory_enabled"],
        }
