"""Give Buddy memory continuity across sessions: personalized greetings that
reference the last session and recommend what to practice next, while
respecting the user's memory-enabled preference.
"""

from ..models import BuddySession, BuddyWeakArea


class BuddyContinuityService:
    def __init__(self, profile):
        self.profile = profile

    def get_last_session_summary(self):
        if not self.profile.is_memory_enabled:
            return None
        last_session = BuddySession.objects.filter(profile=self.profile, status="ended").order_by("-ended_at").first()
        if not last_session:
            return None
        return {
            "id": last_session.id,
            "topic": last_session.topic,
            "language": last_session.language,
            "summary": last_session.ai_summary,
            "ended_at": last_session.ended_at.isoformat() if last_session.ended_at else None,
        }

    def get_recommended_continuation(self):
        if not self.profile.is_memory_enabled:
            return None
        weak_area = (
            BuddyWeakArea.objects.filter(profile=self.profile, status="active")
            .order_by("-severity", "-updated_at")
            .first()
        )
        if not weak_area:
            return None
        return {
            "area_type": weak_area.area_type,
            "title": weak_area.title,
            "improvement_plan": weak_area.improvement_plan,
        }

    def build_personalized_greeting(self):
        """Return a short greeting string that references memory when available."""
        if not self.profile.is_memory_enabled:
            return "Memory is off. Buddy will not use previous conversations."

        last_session = self.get_last_session_summary()
        continuation = self.get_recommended_continuation()

        if not last_session and not continuation:
            return f"Hi! I'm {self.profile.buddy_name}. Let's start practicing today."

        parts = []
        if last_session and last_session.get("topic"):
            parts.append(f"Last time we practiced {last_session['topic']}. Do you want to continue?")
        if continuation:
            area_label = continuation["area_type"].replace("_", " ")
            parts.append(f"You often have trouble with {area_label}, so let's practice that today.")
        if not parts:
            parts.append(f"Welcome back! I'm {self.profile.buddy_name}, ready for today's practice.")
        return " ".join(parts)
