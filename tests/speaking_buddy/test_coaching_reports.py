from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from rest_framework.test import APIClient

from apps.speaking_buddy.models import (
    BuddyNextLesson,
    BuddyProfile,
    BuddyScenario,
    BuddySession,
    BuddySessionReport,
    BuddySettings,
    BuddyVocabulary,
    BuddyWeakArea,
)
from apps.speaking_buddy.services.continuity_service import BuddyContinuityService
from apps.speaking_buddy.services.scenario_seed import seed_scenarios

User = get_user_model()


@override_settings(
    OPENAI_API_KEY="test-key",
    SPEAKING_BUDDY_MODEL="gpt-4o-mini",
    SPEAKING_BUDDY_REALTIME_MODEL="gpt-realtime-test",
)
class BuddyCoachingApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user1 = User.objects.create_user("coach1", "coach1@example.com", "password")
        self.user2 = User.objects.create_user("coach2", "coach2@example.com", "password")
        self.profile1 = BuddyProfile.objects.create(
            user=self.user1, buddy_name="Mila", native_language="en", target_language="nl"
        )
        self.profile2 = BuddyProfile.objects.create(
            user=self.user2, buddy_name="Sam", native_language="en", target_language="en"
        )
        BuddySettings.objects.get_or_create(profile=self.profile1)
        BuddySettings.objects.get_or_create(profile=self.profile2)
        seed_scenarios()

    def auth(self, user):
        self.client.force_authenticate(user=user)

    @patch("apps.speaking_buddy.views.generate_buddy_reply")
    @patch("apps.speaking_buddy.views.summarize_session")
    def _start_and_end_session(self, summarize_session, generate_buddy_reply, mistakes_count=2, vocab_count=1):
        generate_buddy_reply.side_effect = ["Welcome!", "Nice work."]
        summarize_session.return_value = {
            "summary": "Practiced speaking.",
            "weak_areas": ["grammar"],
            "practice_topics": ["travel"],
            "improvement_notes": ["Use longer answers."],
            "vocabulary": [
                {"word": f"woord{i}", "translation": f"word{i}", "language": "nl"} for i in range(vocab_count)
            ],
            "mistakes": [
                {
                    "original_text": f"Ik zijn {i}",
                    "corrected_text": f"Ik ben {i}",
                    "mistake_type": "grammar",
                    "language": "nl",
                }
                for i in range(mistakes_count)
            ],
            "user_summary": "Practiced Dutch.",
        }
        start = self.client.post("/api/buddy/session/start/", {"topic": "Travel", "language": "nl"}, format="json")
        session_id = start.data["id"]
        end = self.client.post("/api/buddy/session/end/", {"session_id": session_id}, format="json")
        return session_id, end

    def test_report_generated_after_session_end_with_score_fields(self):
        self.auth(self.user1)
        session_id, end = self._start_and_end_session()
        self.assertEqual(end.status_code, 200)
        self.assertIn("report", end.data)
        report = BuddySessionReport.objects.get(session_id=session_id)
        for field in (
            "overall_score",
            "fluency_score",
            "grammar_score",
            "vocabulary_score",
            "confidence_score",
            "completeness_score",
        ):
            value = getattr(report, field)
            self.assertGreaterEqual(value, 0)
            self.assertLessEqual(value, 100)
        self.assertTrue(report.is_fallback)  # no OpenAI client configured in tests -> fallback scorer

    def test_next_lesson_generated_after_report(self):
        self.auth(self.user1)
        self._start_and_end_session()
        self.assertTrue(BuddyNextLesson.objects.filter(user=self.user1).exists())
        response = self.client.get("/api/buddy/next-lesson/")
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.data.get("id"))

    def test_next_lesson_complete_endpoint(self):
        self.auth(self.user1)
        self._start_and_end_session()
        lesson = BuddyNextLesson.objects.filter(user=self.user1).first()
        response = self.client.post(f"/api/buddy/next-lesson/{lesson.id}/complete/", {"status": "completed"})
        self.assertEqual(response.status_code, 200)
        lesson.refresh_from_db()
        self.assertEqual(lesson.status, "completed")

    def test_weak_areas_update_after_report(self):
        self.auth(self.user1)
        self._start_and_end_session(mistakes_count=5)
        self.assertTrue(BuddyWeakArea.objects.filter(user=self.user1).exists())
        response = self.client.get("/api/buddy/weak-areas/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(len(response.data) > 0)

    def test_progress_endpoint_returns_aggregates(self):
        self.auth(self.user1)
        self._start_and_end_session()
        response = self.client.get("/api/buddy/progress/")
        self.assertEqual(response.status_code, 200)
        for key in (
            "total_conversations",
            "total_minutes_practiced",
            "average_score",
            "score_trend",
            "weekly_practice_chart",
            "current_streak",
            "vocabulary_learned",
        ):
            self.assertIn(key, response.data)
        self.assertEqual(response.data["total_conversations"], 1)

    def test_scenario_list_filters_by_language_and_kids_mode(self):
        self.auth(self.user1)
        response = self.client.get("/api/buddy/scenarios/", {"language": "nl"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(all(item["language"] == "nl" for item in response.data))

        response = self.client.get("/api/buddy/scenarios/", {"language": "en"})
        self.assertTrue(all(item["language"] == "en" for item in response.data))

    def test_kids_mode_hides_unsafe_scenarios(self):
        BuddyScenario.objects.create(
            title="Adult topic",
            slug="adult-topic-test",
            language="en",
            category="daily_life",
            is_kids_safe=False,
            is_active=True,
        )
        settings_obj = BuddySettings.objects.get(profile=self.profile1)
        settings_obj.kids_mode = True
        settings_obj.save(update_fields=["kids_mode"])
        self.auth(self.user1)
        response = self.client.get("/api/buddy/scenarios/", {"language": "en"})
        slugs = [item["slug"] for item in response.data]
        self.assertNotIn("adult-topic-test", slugs)
        self.assertTrue(all(item["is_kids_safe"] for item in response.data))

    def test_vocabulary_review_updates_status(self):
        vocab = BuddyVocabulary.objects.create(profile=self.profile1, word="huis", translation="house", language="nl")
        self.auth(self.user1)
        response = self.client.get("/api/buddy/vocabulary/review/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(any(item["id"] == vocab.id for item in response.data))

        response = self.client.post(f"/api/buddy/vocabulary/{vocab.id}/review-result/", {"result": "known"})
        self.assertEqual(response.status_code, 200)
        vocab.refresh_from_db()
        self.assertEqual(vocab.review_count, 1)
        self.assertEqual(vocab.last_result, "known")
        self.assertIsNotNone(vocab.next_review_at)

    def test_memory_continuity_uses_latest_summary(self):
        session = BuddySession.objects.create(
            profile=self.profile1,
            language="nl",
            topic="job interview",
            status="ended",
            ai_summary="Practiced job interview questions.",
            ended_at=timezone.now(),
        )
        self.profile1.is_memory_enabled = True
        self.profile1.save(update_fields=["is_memory_enabled"])
        BuddyWeakArea.objects.create(
            user=self.user1,
            profile=self.profile1,
            area_type="grammar",
            title="Word order",
            language="nl",
            severity="high",
            status="active",
        )
        service = BuddyContinuityService(self.profile1)
        greeting = service.build_personalized_greeting()
        self.assertIn("job interview", greeting)
        self.assertIn("grammar", greeting)
        self.assertEqual(session.status, "ended")

    def test_memory_disabled_excludes_old_history(self):
        BuddySession.objects.create(
            profile=self.profile1,
            language="nl",
            topic="job interview",
            status="ended",
            ai_summary="Practiced job interview questions.",
            ended_at=timezone.now(),
        )
        self.profile1.is_memory_enabled = False
        self.profile1.save(update_fields=["is_memory_enabled"])
        service = BuddyContinuityService(self.profile1)
        self.assertIsNone(service.get_last_session_summary())
        greeting = service.build_personalized_greeting()
        self.assertEqual(greeting, "Memory is off. Buddy will not use previous conversations.")

    def test_permissions_prevent_cross_user_access(self):
        self.auth(self.user1)
        _session_id, end = self._start_and_end_session()
        report = BuddySessionReport.objects.get(session__profile=self.profile1)
        lesson = BuddyNextLesson.objects.filter(user=self.user1).first()

        self.auth(self.user2)
        response = self.client.get(f"/api/buddy/reports/{report.id}/")
        self.assertEqual(response.status_code, 404)

        response = self.client.post(f"/api/buddy/next-lesson/{lesson.id}/complete/", {"status": "completed"})
        self.assertEqual(response.status_code, 404)

        vocab = BuddyVocabulary.objects.create(profile=self.profile1, word="fiets", language="nl")
        response = self.client.post(f"/api/buddy/vocabulary/{vocab.id}/review-result/", {"result": "known"})
        self.assertEqual(response.status_code, 404)

    def test_report_list_and_detail_and_regenerate(self):
        self.auth(self.user1)
        self._start_and_end_session()
        response = self.client.get("/api/buddy/reports/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        report_id = response.data[0]["id"]

        response = self.client.get(f"/api/buddy/reports/{report_id}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["id"], report_id)

        response = self.client.post(f"/api/buddy/reports/{report_id}/regenerate/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["id"], report_id)


class BuddyAdminRegistrationTests(TestCase):
    def test_new_models_registered_in_admin(self):
        from django.contrib import admin

        from apps.speaking_buddy.models import BuddyNextLesson, BuddyScenario, BuddySessionReport, BuddyWeakArea

        for model in (BuddyNextLesson, BuddyScenario, BuddySessionReport, BuddyWeakArea):
            self.assertIn(model, admin.site._registry)
