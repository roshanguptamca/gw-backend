from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from rest_framework.test import APIClient

from apps.speaking_buddy.models import BuddyMistake, BuddyProfile, BuddySession, BuddySettings, BuddyVocabulary
from apps.speaking_buddy.services.context_builder import build_session_context
from apps.speaking_buddy.services.greeting_service import BuddyGreetingService
from apps.speaking_buddy.services.intent_detector import BuddyIntentDetector
from apps.speaking_buddy.services.personalization_service import BuddyPersonalizationService

User = get_user_model()


class BuddyIntentDetectorTests(TestCase):
    def test_goodbye_in_english_is_detected(self):
        for phrase in ("bye", "Goodbye!", "see you later", "talk to you later", "good night"):
            self.assertTrue(BuddyIntentDetector.is_goodbye(phrase), phrase)

    def test_goodbye_in_dutch_is_detected(self):
        for phrase in ("doei", "Tot ziens!", "tot later", "dag"):
            self.assertTrue(BuddyIntentDetector.is_goodbye(phrase), phrase)

    def test_goodbye_in_hindi_is_detected(self):
        for phrase in ("अलविदा", "फिर मिलेंगे"):
            self.assertTrue(BuddyIntentDetector.is_goodbye(phrase), phrase)

    def test_non_goodbye_sentence_is_not_detected(self):
        for phrase in (
            "I would like to talk about my day at work.",
            "Can you help me practice grammar?",
            "Ik wil graag over het weer praten vandaag.",
        ):
            self.assertFalse(BuddyIntentDetector.is_goodbye(phrase), phrase)

    def test_empty_text_is_not_goodbye(self):
        self.assertFalse(BuddyIntentDetector.is_goodbye(""))
        self.assertFalse(BuddyIntentDetector.is_goodbye(None))


@override_settings(OPENAI_API_KEY="test-key", SPEAKING_BUDDY_MODEL="gpt-4o-mini")
class BuddyGreetingApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user("greeter", "greeter@example.com", "password")
        self.profile = BuddyProfile.objects.create(
            user=self.user, buddy_name="Luna", native_language="en", target_language="nl"
        )
        BuddySettings.objects.get_or_create(profile=self.profile)
        self.client.force_authenticate(user=self.user)

    def test_session_starts_with_greeting(self):
        response = self.client.post("/api/buddy/session/start/", {"topic": "Travel", "language": "nl"}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertIn("welcome_message", response.data)
        self.assertTrue(response.data["welcome_message"])
        self.assertIn("greeting_instructions", response.data)

    def test_greeting_uses_buddy_name_and_language(self):
        greeting = BuddyGreetingService(self.profile, BuddySettings.objects.get(profile=self.profile)).build_greeting()
        self.assertIn("Luna", greeting["text"])
        self.assertIn("Dutch", greeting["text"])
        self.assertIn("Luna", greeting["instructions"])

    def test_goodbye_in_english_ends_call(self):
        start = self.client.post("/api/buddy/session/start/", {"topic": "Travel", "language": "nl"}, format="json")
        session_id = start.data["id"]
        response = self.client.post(
            "/api/buddy/session/message/", {"session_id": session_id, "text": "Okay, bye!"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["should_end_session"])
        session = BuddySession.objects.get(id=session_id)
        self.assertEqual(session.status, "ended")
        self.assertEqual(session.end_reason, "user_goodbye")

    def test_goodbye_in_dutch_ends_call(self):
        start = self.client.post("/api/buddy/session/start/", {"topic": "Travel", "language": "nl"}, format="json")
        session_id = start.data["id"]
        response = self.client.post(
            "/api/buddy/session/message/", {"session_id": session_id, "text": "Oke, doei!"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["should_end_session"])
        session = BuddySession.objects.get(id=session_id)
        self.assertEqual(session.status, "ended")
        self.assertEqual(session.end_reason, "user_goodbye")

    def test_goodbye_in_hindi_ends_call(self):
        start = self.client.post("/api/buddy/session/start/", {"topic": "Travel", "language": "nl"}, format="json")
        session_id = start.data["id"]
        response = self.client.post(
            "/api/buddy/session/message/", {"session_id": session_id, "text": "ठीक है, अलविदा"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["should_end_session"])
        session = BuddySession.objects.get(id=session_id)
        self.assertEqual(session.status, "ended")
        self.assertEqual(session.end_reason, "user_goodbye")

    @patch("apps.speaking_buddy.views.generate_buddy_reply")
    def test_non_goodbye_sentence_does_not_end_call(self, generate_buddy_reply):
        generate_buddy_reply.return_value = "Great, tell me more!"
        start = self.client.post("/api/buddy/session/start/", {"topic": "Travel", "language": "nl"}, format="json")
        session_id = start.data["id"]
        response = self.client.post(
            "/api/buddy/session/message/",
            {"session_id": session_id, "text": "I want to talk about my trip to Amsterdam."},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["should_end_session"])
        session = BuddySession.objects.get(id=session_id)
        self.assertEqual(session.status, "active")


class BuddyPersonalizationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("personalize", "personalize@example.com", "password")
        self.profile = BuddyProfile.objects.create(
            user=self.user,
            buddy_name="Mila",
            native_language="en",
            target_language="nl",
            learning_goal="Prepare for a job interview",
        )
        self.settings_obj, _ = BuddySettings.objects.get_or_create(profile=self.profile)
        BuddySession.objects.create(
            profile=self.profile,
            language="nl",
            topic="job interview",
            status="ended",
            ai_summary="Practiced job interview questions.",
            ended_at=timezone.now(),
        )
        BuddyVocabulary.objects.create(
            profile=self.profile, word="sollicitatie", translation="job application", language="nl"
        )
        BuddyMistake.objects.create(
            profile=self.profile,
            original_text="Ik ben werk",
            corrected_text="Ik werk",
            mistake_type="grammar",
            language="nl",
        )

    def test_personalization_includes_old_mistakes_vocabulary_summaries(self):
        summary = BuddyPersonalizationService(self.profile, self.settings_obj).get_personalization_summary()
        self.assertTrue(summary["memory_enabled"])
        self.assertEqual(summary["learning_goal"], "Prepare for a job interview")
        self.assertTrue(any(s["topic"] == "job interview" for s in summary["recent_sessions"]))
        self.assertTrue(any(v["word"] == "sollicitatie" for v in summary["recent_vocab"]))
        self.assertTrue(any(m["original_text"] == "Ik ben werk" for m in summary["recent_mistakes"]))

    def test_memory_disabled_excludes_old_history_from_personalization(self):
        self.profile.is_memory_enabled = False
        self.profile.save(update_fields=["is_memory_enabled"])
        context = build_session_context(self.profile, self.settings_obj)
        self.assertIn("Memory: disabled", context.system_prompt)
        self.assertIn("none (memory disabled)", context.system_prompt)
