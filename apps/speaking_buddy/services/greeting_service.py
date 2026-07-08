"""Builds the greeting AI Buddy uses to speak first when a call/session
starts, instead of waiting for the learner to talk first.

Produces both:
- ``text``: a deterministic, ready-to-display greeting (always available,
  even without an OpenAI call) used for the session transcript / UI.
- ``instructions``: extra instructions handed to the realtime voice model so
  it can deliver an equivalent (but naturally varied) spoken greeting
  immediately after connecting.
"""

from .context_builder import language_name
from .continuity_service import BuddyContinuityService

MEMORY_OFF_NOTE = "Memory is off. Buddy will not use previous conversations."


class BuddyGreetingService:
    def __init__(self, profile, settings_obj=None):
        self.profile = profile
        self.settings_obj = settings_obj

    def build_greeting(self, topic=None, scenario=None):
        if scenario:
            return self._build_scenario_greeting(scenario)
        return self._build_default_greeting(topic)

    def _build_scenario_greeting(self, scenario):
        buddy_name = self.profile.buddy_name or "your AI speaking buddy"
        target_language = language_name(scenario.language or self.profile.target_language)
        text = scenario.opening_message or (
            f"Hi, I'm {buddy_name}, your AI speaking buddy. "
            f"Let's practice the '{scenario.title}' scenario in {target_language}. Ready to start?"
        )
        instructions = (
            f"Greet the learner first, before they say anything. Stay in character for the "
            f"'{scenario.title}' scenario. Briefly introduce yourself as {buddy_name} if it fits "
            f"naturally, then start the scenario in {target_language}. Keep it short (1-3 sentences) "
            f"and ask exactly one simple opening question."
        )
        return {"text": text, "instructions": instructions}

    def _build_default_greeting(self, topic=None):
        buddy_name = self.profile.buddy_name or "your AI speaking buddy"
        target_language = language_name(self.profile.target_language)
        personality = getattr(self.settings_obj, "personality", "friendly") if self.settings_obj else "friendly"

        continuity = BuddyContinuityService(self.profile)
        continuity_note = continuity.build_personalized_greeting()
        memory_enabled = self.profile.is_memory_enabled
        question = self._opening_question(topic)

        text = f"Hi, I'm {buddy_name}, your AI speaking buddy. Let's practice {target_language} together."
        if memory_enabled and continuity_note and continuity_note != MEMORY_OFF_NOTE:
            text = f"{text} {continuity_note}"
        else:
            text = f"{text} {question}"

        instructions_parts = [
            f"Greet the learner first, before they say anything. Introduce yourself as {buddy_name}, "
            f"a friendly AI speaking buddy with a {personality} personality.",
            f"Mention that you'll practice {target_language} together today.",
        ]
        if memory_enabled and continuity_note and continuity_note != MEMORY_OFF_NOTE:
            instructions_parts.append(
                f"Personalize the greeting using this context (say it naturally, don't read it verbatim): {continuity_note}"
            )
        else:
            instructions_parts.append(
                f"Vary the greeting each session so it does not sound identical every time. Ask: {question}"
            )
        instructions_parts.append("Keep the greeting short (2-3 sentences) and ask exactly one simple opening question.")
        instructions = " ".join(instructions_parts)

        return {"text": text, "instructions": instructions, "memory_note": continuity_note if not memory_enabled else None}

    @staticmethod
    def _opening_question(topic=None):
        if topic:
            return f"How has your day been, and shall we talk about {topic}?"
        return "How was your day?"
