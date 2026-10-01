from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from rest_framework.test import APIClient

from apps.dutch_practice.models import PracticeAttempt, PracticeMedia, PracticeQuestion

BASE = "/api/dutch-practice/"


class PracticeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Repository pytest defaults to --nomigrations. Explicitly seed there too;
        # manage.py test exercises the real migration chain separately.
        import importlib

        from django.apps import apps
        from django.db import connection

        if not PracticeQuestion.objects.exists():
            editor = type("Editor", (), {"connection": connection})()
            importlib.import_module("apps.dutch_practice.migrations.0002_initial_questions").seed_questions(
                apps, editor
            )
            importlib.import_module("apps.dutch_practice.migrations.0004_initial_media").seed(apps, editor)
            importlib.import_module("apps.dutch_practice.migrations.0006_expanded_bank").seed(apps, editor)
        cls.user = get_user_model().objects.create_user("learner", password="example-long-password")
        cls.other = get_user_model().objects.create_user("other")

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def start(self, skill="reading", level="A1"):
        response = self.client.post(BASE + "attempts/", {"level": level, "skill": skill, "mock_test": 1}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        return response.data["id"]

    def test_seed_and_catalog_do_not_expose_questions(self):
        self.assertEqual(PracticeQuestion.objects.count(), 320)
        self.assertEqual(PracticeMedia.objects.count(), 64)
        response = self.client.get(BASE + "catalog/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["pools"]), 20)
        self.assertTrue(all(p["available"] for p in response.data["pools"]))
        self.assertNotIn("questions", response.data)
        self.assertEqual(response["Cache-Control"], "private, no-store")

    def test_login_required_and_cross_user_isolation(self):
        id = self.start()
        anonymous = APIClient()
        self.assertIn(anonymous.get(BASE + "catalog/").status_code, (401, 403))
        anonymous.force_authenticate(self.other)
        for suffix in ("", "questions/0/", "result/"):
            self.assertEqual(anonymous.get(BASE + f"attempts/{id}/" + suffix).status_code, 404)
        self.assertEqual(anonymous.get(BASE + "attempts/").data["count"], 0)
        self.assertEqual(anonymous.post(BASE + f"attempts/{id}/abandon/", {}, format="json").status_code, 404)

    def test_one_active_attempt_and_database_constraint(self):
        id = self.start()
        second = self.client.post(
            BASE + "attempts/", {"level": "B2", "skill": "writing", "mock_test": 20}, format="json"
        )
        self.assertEqual(second.status_code, 409)
        with self.assertRaises(IntegrityError), transaction.atomic():
            PracticeAttempt.objects.create(
                user=self.user,
                level="A1",
                skill="reading",
                mock_test=1,
                question_signature="x" * 64,
                expires_at=timezone.now() + timedelta(hours=1),
            )
        self.client.post(BASE + f"attempts/{id}/abandon/", {}, format="json")
        self.start("speaking", "B2")

    def test_answers_private_until_submit_and_persisted_result(self):
        id = self.start()
        attempt = PracticeAttempt.objects.get(pk=id)
        self.assertEqual(self.client.get(BASE + f"attempts/{id}/result/").status_code, 409)
        self.assertEqual(self.client.post(BASE + f"attempts/{id}/submit/", {}, format="json").status_code, 400)
        for item in attempt.items.all():
            response = self.client.get(BASE + f"attempts/{id}/questions/{item.position}/")
            self.assertNotIn("answer", response.data["question"])
            self.assertNotIn("explanation", response.data["question"])
            self.assertEqual(
                self.client.post(
                    BASE + f"attempts/{id}/questions/{item.position}/",
                    {"choice": item.snapshot["answer"]},
                    format="json",
                ).status_code,
                200,
            )
        first = self.client.post(BASE + f"attempts/{id}/submit/", {}, format="json")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.data["attempt"]["score"], 4)
        second = self.client.post(BASE + f"attempts/{id}/submit/", {}, format="json")
        self.assertEqual(first.data, second.data)
        self.assertEqual(self.client.get(BASE + f"attempts/{id}/questions/0/").status_code, 409)
        self.assertEqual(self.client.get(BASE + "attempts/").data["results"][0]["status"], "completed")
        next_id = self.start()
        self.assertNotEqual(attempt.question_signature, PracticeAttempt.objects.get(pk=next_id).question_signature)

    def test_media_range_ownership_and_stable_snapshot(self):
        id = self.start("listening")
        path = BASE + f"attempts/{id}/questions/0/media/"
        response = self.client.get(path, HTTP_RANGE="bytes=0-31")
        self.assertEqual(response.status_code, 206)
        self.assertEqual(len(response.content), 32)
        self.assertEqual(response["Content-Type"], "video/mp4")
        self.assertTrue(response["Content-Range"].startswith("bytes 0-31/"))
        self.assertEqual(self.client.get(path, HTTP_RANGE="bytes=999999999-").status_code, 416)
        self.assertEqual(self.client.get(path, HTTP_RANGE="bytes=-0").status_code, 416)
        self.assertEqual(self.client.get(path, HTTP_RANGE="bytes=-10").status_code, 206)
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(path).status_code, 404)

    def test_writing_speaking_and_transcript_assistance(self):
        for skill in ("writing", "speaking", "listening"):
            id = self.start(skill)
            for position in range(4):
                data = (
                    {"text": "Mijn originele antwoord."}
                    if skill == "writing"
                    else {"spoken": True} if skill == "speaking" else {"choice": 0, "used_transcript": True}
                )
                self.assertEqual(
                    self.client.post(BASE + f"attempts/{id}/questions/{position}/", data, format="json").status_code,
                    200,
                )
            response = self.client.post(BASE + f"attempts/{id}/submit/", {}, format="json")
            self.assertEqual(response.status_code, 200)
            if skill == "listening":
                self.assertTrue(response.data["attempt"]["assisted"])
            else:
                self.assertIsNone(response.data["attempt"]["score"])
                self.assertIn("modelAnswer", response.data["items"][0]["feedback"])

    def test_expired_attempt_validation_and_csrf(self):
        id = self.start()
        PracticeAttempt.objects.filter(pk=id).update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.client.get(BASE + f"attempts/{id}/questions/0/").status_code, 409)
        self.start()
        for data in (
            {"level": "C1", "skill": "reading", "mock_test": 1},
            {"level": "A1", "skill": "reading", "mock_test": 21},
        ):
            self.assertEqual(self.client.post(BASE + "attempts/", data, format="json").status_code, 400)
        csrf = APIClient(enforce_csrf_checks=True)
        csrf.force_login(self.user)
        self.assertEqual(
            csrf.post(
                BASE + "attempts/", {"level": "A2", "skill": "reading", "mock_test": 1}, format="json"
            ).status_code,
            403,
        )

    def test_twenty_distinct_random_sets_for_every_level_and_category(self):
        from apps.dutch_practice import services

        for level in ("A1", "A2", "B1", "B2"):
            for skill in ("reading", "writing", "listening", "speaking", "knm"):
                signatures = set()
                for mock_test in range(1, 21):
                    attempt = services.start_attempt(self.user, level, skill, mock_test)
                    self.assertNotIn(attempt.question_signature, signatures)
                    signatures.add(attempt.question_signature)
                    self.assertEqual(attempt.items.count(), 4)
                    attempt.status = "abandoned"
                    attempt.save(update_fields=["status"])
                self.assertEqual(len(signatures), 20)

    def test_knm_is_automatically_scored(self):
        id = self.start("knm", "A2")
        for item in PracticeAttempt.objects.get(pk=id).items.all():
            response = self.client.post(
                BASE + f"attempts/{id}/questions/{item.position}/", {"choice": item.snapshot["answer"]}, format="json"
            )
            self.assertEqual(response.status_code, 200)
        result = self.client.post(BASE + f"attempts/{id}/submit/", {}, format="json")
        self.assertEqual(result.data["attempt"]["score"], 4)
        self.assertEqual(result.data["attempt"]["assessment"], "automatic")
