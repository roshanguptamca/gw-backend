import hashlib
import importlib
import json
from collections import Counter
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.utils import timezone

from rest_framework.test import APIClient

from apps.dutch_practice import services
from apps.dutch_practice.blueprints import BANK_VERSION, catalog_formats
from apps.dutch_practice.models import PracticeAttempt, PracticeMedia, PracticeQuestion, validate_payload

BASE = "/api/dutch-practice/"
DATA = Path(__file__).resolve().parents[2] / "apps/dutch_practice/data"


class ExamTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        if not PracticeQuestion.objects.filter(payload__bankVersion=BANK_VERSION).exists():
            editor = type("Editor", (), {"connection": connection})()
            importlib.import_module("apps.dutch_practice.migrations.0008_exam_bank").seed(apps, editor)
        cls.user = get_user_model().objects.create_user("exam-learner")
        cls.other = get_user_model().objects.create_user("exam-other")

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def start(self, level="B1", skill="reading", number=1):
        response = self.client.post(
            BASE + "attempts/",
            {
                "level": level,
                "skill": skill,
                "mock_test": number,
                "mode": "mock",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        return PracticeAttempt.objects.get(pk=response.data["id"])

    def test_bank_sufficiency_counts_mix_groups_and_all_twenty_sets(self):
        self.assertEqual(PracticeQuestion.objects.filter(payload__bankVersion=BANK_VERSION).count(), 6980)
        for spec in catalog_formats():
            selections = set()
            for number in range(1, 21):
                attempt = services.start_attempt(self.user, spec["level"], spec["skill"], number, mode="mock")
                items = list(attempt.items.all())
                self.assertEqual(len(items), spec["count"])
                self.assertEqual(Counter(item.snapshot["taskType"] for item in items), Counter(spec["mix"]))
                self.assertEqual(len({item.snapshot["groupId"] for item in items}), spec["groups"])
                if "topics" in spec:
                    self.assertEqual(Counter(item.snapshot["theme"] for item in items), Counter(spec["topics"]))
                self.assertEqual(len({item.snapshot["id"] for item in items}), len(items))
                self.assertNotIn(attempt.question_signature, selections)
                selections.add(attempt.question_signature)
                self.assertEqual(attempt.bank_version, BANK_VERSION)
                self.assertAlmostEqual(
                    (attempt.expires_at - attempt.created_at).total_seconds(), spec["minutes"] * 60, delta=2
                )
                for item in items:
                    validate_payload(item.snapshot, attempt.level, attempt.skill)
                group_positions = {}
                for item in items:
                    group_positions.setdefault(item.snapshot["groupId"], []).append(item.position)
                self.assertTrue(all(max(pos) - min(pos) + 1 == len(pos) for pos in group_positions.values()))
                attempt.status = "abandoned"
                attempt.save(update_fields=["status"])

    def test_bank_has_no_exact_duplicate_material_and_every_audio_is_committed(self):
        bank = json.loads((DATA / "exam-bank-v3.json").read_text())
        seen = set()
        for question in bank["questions"]:
            fingerprint = (
                question["level"],
                question["skill"],
                question.get("text", question.get("transcript", "")),
                question["prompt"],
                tuple((panel["kind"], panel["label"]) for panel in question.get("picturePanels", [])),
            )
            self.assertTrue(fingerprint not in seen, f"Duplicate learner stimulus: {question['id']}")
            seen.add(fingerprint)
            validate_payload(question, question["level"], question["skill"])
            if "options" in question:
                self.assertEqual(len(set(question["options"])), 3)
                self.assertTrue(question["explanation"])
        manifest = json.loads((DATA / "exam-media-v3.json").read_text())
        codes = set()
        script_hashes = {}
        for clip in manifest["clips"]:
            content = (DATA / "exam-media-v3" / clip["file"]).read_bytes()
            self.assertEqual(hashlib.sha256(content).hexdigest(), clip["sha256"])
            self.assertGreater(clip["duration_seconds"], 1)
            self.assertGreater(len(content), 1000)
            codes.add(clip["code"])
            script_hashes[clip["code"]] = clip["script_sha256"]
        self.assertTrue(all(q["mediaCode"] in codes for q in bank["questions"] if "mediaCode" in q))
        for question in bank["questions"]:
            if "mediaCode" in question:
                self.assertEqual(
                    hashlib.sha256(question["transcript"].encode()).hexdigest(), script_hashes[question["mediaCode"]]
                )
        word_counts = {
            level: [
                len(q["text"].split()) for q in bank["questions"] if q["level"] == level and q["skill"] == "reading"
            ]
            for level in ("A1", "A2", "B1", "B2")
        }
        averages = {level: sum(counts) / len(counts) for level, counts in word_counts.items()}
        self.assertLess(averages["A1"], averages["A2"])
        self.assertLess(averages["A2"], averages["B1"])
        self.assertLess(averages["B1"], averages["B2"])

    def test_a2_speaking_has_original_video_and_all_picture_types(self):
        attempt = self.start("A2", "speaking")
        picture_counts = {"one_picture": 1, "two_pictures": 2, "three_pictures": 3}
        for item in attempt.items.all():
            data = self.client.get(BASE + f"attempts/{attempt.pk}/questions/{item.position}/").data["question"]
            if data["taskType"] == "video_prompt":
                self.assertIn("mediaPath", data)
                self.assertEqual(item.media.mime_type, "video/mp4")
            else:
                self.assertEqual(len(data["picturePanels"]), picture_counts[data["taskType"]])

    def test_no_incomplete_or_four_question_fallback_and_knm_is_single_component(self):
        response = self.client.post(
            BASE + "attempts/",
            {
                "level": "B2",
                "skill": "knm",
                "mock_test": 1,
                "mode": "mock",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        question = PracticeQuestion.objects.filter(
            level="B1", skill="reading", payload__bankVersion=BANK_VERSION
        ).first()
        question.is_active = False
        question.save()
        response = self.client.post(
            BASE + "attempts/",
            {
                "level": "B1",
                "skill": "reading",
                "mock_test": 1,
                "mode": "mock",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("No shortened exam", str(response.data))
        self.assertEqual(PracticeAttempt.objects.filter(user=self.user).count(), 0)
        formats = self.client.get(BASE + "catalog/").data["exam_formats"]
        self.assertEqual(
            [(spec["level"], spec["skill"]) for spec in formats if spec["skill"] == "knm"], [("A2", "knm")]
        )

    def test_question_snapshots_shuffle_answer_mapping_and_refresh_resume(self):
        with patch("apps.dutch_practice.services.random.SystemRandom") as random_source:
            random_source.return_value.shuffle.side_effect = lambda values: values.reverse()
            attempt = self.start()
        items = list(attempt.items.all())
        for item in items:
            original = PracticeQuestion.objects.get(code=item.snapshot["id"])
            self.assertEqual(
                item.snapshot["options"][item.snapshot["answer"]],
                original.payload["options"][original.payload["answer"]],
            )
        self.assertTrue(any(item.snapshot["answer"] != 0 for item in items))
        position = 12
        before = self.client.get(BASE + f"attempts/{attempt.pk}/questions/{position}/").data
        original = PracticeQuestion.objects.get(code=items[position].snapshot["id"])
        original.payload["prompt"] = "Changed live bank; must not change this attempt"
        original.save()
        after = self.client.get(BASE + f"attempts/{attempt.pk}/questions/{position}/").data
        self.assertEqual(before, after)
        metadata = self.client.get(BASE + f"attempts/{attempt.pk}/").data
        self.assertEqual(metadata["next_position"], position)
        self.assertEqual(metadata["bank_version"], BANK_VERSION)

    def test_answers_confidential_until_submission_and_objective_scoring(self):
        attempt = self.start("A2", "reading")
        self.assertEqual(self.client.get(BASE + f"attempts/{attempt.pk}/result/").status_code, 409)
        for item in attempt.items.all():
            data = self.client.get(BASE + f"attempts/{attempt.pk}/questions/{item.position}/").data["question"]
            for private in ("answer", "explanation", "modelAnswer", "rubric"):
                self.assertNotIn(private, data)
            self.client.post(
                BASE + f"attempts/{attempt.pk}/questions/{item.position}/",
                {"choice": item.snapshot["answer"]},
                format="json",
            )
        response = self.client.post(BASE + f"attempts/{attempt.pk}/submit/", {}, format="json")
        self.assertEqual(response.data["attempt"]["score"], 25)
        self.assertEqual(response.data["attempt"]["question_count"], 25)
        self.assertTrue(all(item["feedback"]["correct"] for item in response.data["items"]))
        self.assertEqual(response.data, self.client.get(BASE + f"attempts/{attempt.pk}/result/").data)

    def test_timed_out_attempt_scores_saved_answers_and_cannot_be_changed(self):
        attempt = self.start("A2", "knm")
        item = attempt.items.first()
        self.client.post(
            BASE + f"attempts/{attempt.pk}/questions/0/", {"choice": item.snapshot["answer"]}, format="json"
        )
        PracticeAttempt.objects.filter(pk=attempt.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        response = self.client.get(BASE + f"attempts/{attempt.pk}/")
        self.assertEqual(response.data["status"], "completed")
        self.assertEqual(response.data["score"], 1)
        self.assertEqual(
            self.client.post(BASE + f"attempts/{attempt.pk}/questions/0/", {"choice": 0}, format="json").status_code,
            409,
        )
        self.assertEqual(self.client.get(BASE + f"attempts/{attempt.pk}/result/").status_code, 200)

    def test_once_only_listening_persists_across_refresh_and_hides_transcript(self):
        attempt = self.start("B2", "listening")
        item = attempt.items.first()
        question_path = BASE + f"attempts/{attempt.pk}/questions/0/"
        question = self.client.get(question_path).data["question"]
        self.assertNotIn("transcript", question)
        self.assertTrue(question["mediaPath"])
        media_path = BASE + question["mediaPath"].split("/dutch-practice/", 1)[1]
        response = self.client.get(media_path, HTTP_RANGE="bytes=0-63")
        self.assertEqual(response.status_code, 206)
        self.assertEqual(len(response.content), 64)
        self.assertEqual(response["Content-Type"], "audio/mpeg")
        self.assertEqual(
            self.client.post(question_path + "playback/", {"failed": "invalid"}, format="json").status_code, 400
        )
        self.assertEqual(self.client.post(question_path + "playback/", {}, format="json").status_code, 200)
        self.assertIsNotNone(self.client.get(question_path).data["media_started_at"])
        self.assertEqual(self.client.post(question_path + "playback/", {}, format="json").status_code, 409)
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(media_path).status_code, 404)
        self.assertEqual(self.client.post(question_path + "playback/", {}, format="json").status_code, 404)

    def test_writing_speaking_rubrics_no_numeric_score_or_pass_claim(self):
        for skill in ("writing", "speaking"):
            attempt = self.start("B2", skill)
            item = attempt.items.first()
            answer = {"text": "Mijn antwoord."} if skill == "writing" else {"spoken": True, "text": "Mijn notities."}
            self.client.post(BASE + f"attempts/{attempt.pk}/questions/0/", answer, format="json")
            response = self.client.post(BASE + f"attempts/{attempt.pk}/submit/", {}, format="json")
            self.assertIsNone(response.data["attempt"]["score"])
            self.assertEqual(response.data["attempt"]["assessment"], "self_assessment")
            self.assertTrue(response.data["items"][0]["feedback"]["rubric"]["dimensions"])
            self.assertNotIn("pass_prediction", response.data)

    def test_technical_audio_failure_is_saved_and_not_erased_by_answering(self):
        attempt = self.start("A2", "listening")
        question_path = BASE + f"attempts/{attempt.pk}/questions/0/"
        response = self.client.post(question_path + "playback/", {"failed": True}, format="json")
        self.assertEqual(response.status_code, 200)
        self.client.post(question_path, {"choice": 0}, format="json")
        response = self.client.post(BASE + f"attempts/{attempt.pk}/submit/", {}, format="json")
        self.assertEqual(response.data["attempt"]["media_errors"], 1)

    def test_full_mode_drafts_and_cleared_responses_persist_without_claiming_answered(self):
        for skill in ("writing", "speaking"):
            attempt = self.start("A2", skill)
            path = BASE + f"attempts/{attempt.pk}/questions/0/"
            self.assertEqual(self.client.post(path, {}, format="json").status_code, 400)
            response = self.client.post(path, {"text": "Mijn notities.", "spoken": True}, format="json")
            self.assertEqual(response.status_code, 200)
            response = self.client.post(path, {"text": "", "spoken": False}, format="json")
            self.assertEqual(response.status_code, 200)
            item = attempt.items.first()
            self.assertIsNone(item.answered_at)
            self.assertEqual(self.client.get(path).data["response"]["text"], "")
            if skill == "speaking":
                self.client.post(path, {"text": "Nog niet uitgesproken.", "spoken": False}, format="json")
                self.assertEqual(self.client.get(path).data["response"]["text"], "Nog niet uitgesproken.")
                self.assertIsNone(attempt.items.first().answered_at)
            self.client.post(BASE + f"attempts/{attempt.pk}/submit/", {}, format="json")

    def test_required_a2_speaking_video_cannot_be_missing(self):
        question = PracticeQuestion.objects.filter(
            level="A2", skill="speaking", payload__taskType="video_prompt"
        ).first()
        question.media = None
        question.save()
        response = self.client.post(
            BASE + "attempts/", {"level": "A2", "skill": "speaking", "mock_test": 1, "mode": "mock"}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(PracticeAttempt.objects.filter(user=self.user).exists())
