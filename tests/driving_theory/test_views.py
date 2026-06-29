from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from rest_framework import status
from rest_framework.test import APIClient

from apps.driving_theory.models import (
    DrivingLesson,
    DrivingLessonSection,
    DrivingQuestion,
    DrivingQuestionOption,
    DrivingTopic,
    MockTestAttempt,
    UserDrivingProgress,
)

User = get_user_model()


class DrivingTheoryViewsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="driver", email="driver@example.com", password="pass1234")
        cls.topic, _ = DrivingTopic.objects.update_or_create(
            slug="traffic-signs",
            defaults={
                "title": "Verkeersborden",
                "title_nl": "Verkeersborden NL",
                "summary": "Learn the most common Dutch traffic signs.",
                "summary_nl": "Leer de meest voorkomende Nederlandse verkeersborden.",
                "dutch_terms": [{"term": "verbodsbord", "meaning": "prohibition sign"}],
                "order": 1,
            },
        )
        cls.lesson, _ = DrivingLesson.objects.update_or_create(
            topic=cls.topic,
            title="Traffic signs basics",
            defaults={
                "title_nl": "Basis verkeersborden",
                "summary": "Understand shapes, colours, and sign priorities.",
                "summary_nl": "Begrijp vormen, kleuren en voorrang van borden.",
                "learning_objectives": ["Recognise sign categories."],
                "learning_objectives_nl": ["Verkeersbordcategorieën herkennen."],
                "exam_tips": ["Pay attention to shape first."],
                "exam_tips_nl": ["Let eerst op de vorm van het bord."],
                "common_mistakes": ["Ignoring temporary signs."],
                "common_mistakes_nl": ["Tijdelijke borden negeren."],
                "key_takeaways": ["Use colour and shape together."],
                "key_takeaways_nl": ["Gebruik kleur en vorm samen."],
                "difficulty": "easy",
                "estimated_minutes": 12,
                "order": 1,
            },
        )
        DrivingLessonSection.objects.update_or_create(
            lesson=cls.lesson,
            title="Shapes and colours",
            defaults={
                "content": "Round red signs prohibit, blue signs instruct, and triangles warn.",
                "title_nl": "Vormen en kleuren",
                "content_nl": "Ronde rode borden verbieden, blauwe borden gebieden en driehoeken waarschuwen.",
                "examples": ["A red circle often bans an action."],
                "examples_nl": ["Een rode cirkel verbiedt vaak een handeling."],
                "dutch_keywords": ["verbodsbord", "waarschuwingsbord"],
                "callout_boxes": [{"type": "remember", "text": "Check the border colour first."}],
                "callout_boxes_nl": [{"type": "remember", "text": "Controleer eerst de randkleur."}],
                "order": 1,
            },
        )
        DrivingLessonSection.objects.update_or_create(
            lesson=cls.lesson,
            title="Reading context",
            defaults={
                "content": "Always combine the sign meaning with the road layout and traffic around you.",
                "title_nl": "Context lezen",
                "content_nl": "Combineer de betekenis van het bord altijd met de weginrichting en het verkeer om je heen.",
                "examples": ["A sign can be repeated after a junction."],
                "examples_nl": ["Een bord kan na een kruispunt worden herhaald."],
                "dutch_keywords": ["onderbord", "rijstrook"],
                "callout_boxes": [{"type": "tip", "text": "Read the full road scene."}],
                "callout_boxes_nl": [{"type": "tip", "text": "Lees het volledige verkeersbeeld."}],
                "order": 2,
            },
        )

        cls.questions = []
        for idx in range(1, 31):
            question = DrivingQuestion.objects.create(
                topic=cls.topic,
                lesson=cls.lesson,
                question_text=f"Practice question {idx}?",
                question_text_nl=f"Oefenvraag {idx}?",
                explanation=f"Explanation for question {idx}.",
                explanation_nl=f"Uitleg voor vraag {idx}.",
                difficulty=1 if idx <= 10 else 2 if idx <= 20 else 3,
                points=1,
            )
            correct_option = None
            for option_idx in range(1, 5):
                option = DrivingQuestionOption.objects.create(
                    question=question,
                    option_text=f"Question {idx} option {option_idx}",
                    option_text_nl=f"Vraag {idx} optie {option_idx}",
                    is_correct=option_idx == 1,
                    order=option_idx,
                )
                if option_idx == 1:
                    correct_option = option
            question.correct_option = correct_option
            cls.questions.append(question)

    def setUp(self):
        self.client = APIClient()

    def test_get_topics_returns_list(self):
        response = self.client.get("/api/driving/topics/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data), 1)
        slugs = [t["slug"] for t in response.data]
        self.assertIn(self.topic.slug, slugs)

    def test_get_topics_returns_nl_content_when_requested(self):
        response = self.client.get("/api/driving/topics/?lang=nl")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        topic = next(item for item in response.data if item["slug"] == self.topic.slug)
        self.assertEqual(topic["title"], self.topic.title_nl)
        self.assertEqual(topic["summary"], self.topic.summary_nl)

    def test_get_topic_detail_returns_lessons(self):
        response = self.client.get(f"/api/driving/topics/{self.topic.slug}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["slug"], self.topic.slug)
        self.assertGreaterEqual(len(response.data["lessons"]), 1)

    def test_get_lesson_detail_returns_nl_content_when_requested(self):
        response = self.client.get(f"/api/driving/lessons/{self.lesson.id}/?lang=nl")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["title"], self.lesson.title_nl)
        self.assertEqual(response.data["summary"], self.lesson.summary_nl)
        self.assertEqual(response.data["learning_objectives"], self.lesson.learning_objectives_nl)
        self.assertEqual(response.data["exam_tips"], self.lesson.exam_tips_nl)
        self.assertEqual(response.data["common_mistakes"], self.lesson.common_mistakes_nl)
        self.assertEqual(response.data["key_takeaways"], self.lesson.key_takeaways_nl)
        self.assertEqual(response.data["sections"][0]["title"], "Vormen en kleuren")
        self.assertEqual(
            response.data["sections"][0]["content"],
            "Ronde rode borden verbieden, blauwe borden gebieden en driehoeken waarschuwen.",
        )
        self.assertEqual(response.data["sections"][0]["examples"], ["Een rode cirkel verbiedt vaak een handeling."])
        self.assertEqual(
            response.data["sections"][0]["callout_boxes"],
            [{"type": "remember", "text": "Controleer eerst de randkleur."}],
        )
        question = DrivingQuestion.objects.get(pk=response.data["questions"][0]["id"])
        self.assertEqual(response.data["questions"][0]["question_text"], question.question_text_nl)
        self.assertEqual(response.data["questions"][0]["explanation"], question.explanation_nl)
        option = DrivingQuestionOption.objects.get(pk=response.data["questions"][0]["options"][0]["id"])
        self.assertEqual(response.data["questions"][0]["options"][0]["option_text"], option.option_text_nl)

    def test_get_lesson_detail_returns_sections_and_questions(self):
        response = self.client.get(f"/api/driving/lessons/{self.lesson.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["sections"]), 2)
        self.assertEqual(len(response.data["questions"]), 30)
        self.assertIn("is_correct", response.data["questions"][0]["options"][0])

    def test_post_progress_saves_progress(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.post(
            "/api/driving/progress/",
            {
                "topic_slug": self.topic.slug,
                "lesson_id": self.lesson.id,
                "lesson_completed": True,
                "question_id": self.questions[0].id,
                "answer_correct": True,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        progress = UserDrivingProgress.objects.get(user=self.user, topic=self.topic)
        self.assertIn(self.lesson.id, progress.lessons_completed)
        self.assertEqual(progress.questions_answered, 1)
        self.assertEqual(progress.questions_correct, 1)

    def test_start_mock_test_creates_attempt_with_25_questions(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.post("/api/driving/mock-tests/start/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(response.data["questions"]), 25)
        attempt = MockTestAttempt.objects.get(pk=response.data["attempt"]["id"])
        self.assertEqual(attempt.questions.count(), 25)

    def test_start_mock_test_returns_403_after_three_completed_attempts(self):
        self.client.force_authenticate(user=self.user)
        for attempt_number in range(1, 4):
            attempt = MockTestAttempt.objects.create(
                user=self.user,
                attempt_number=attempt_number,
                total_questions=25,
                correct_answers=18,
                score=72,
                passed=True,
                completed_at=timezone.now(),
            )
            attempt.questions.set(self.questions[:25])

        response = self.client.post("/api/driving/mock-tests/start/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["code"], "MOCK_TEST_LIMIT_REACHED")

    def test_submit_mock_test_returns_score_and_pass_fail(self):
        self.client.force_authenticate(user=self.user)
        attempt = MockTestAttempt.objects.create(user=self.user, attempt_number=1, total_questions=25)
        attempt.questions.set(self.questions[:25])
        answers = [
            {"question_id": question.id, "option_id": question.options.filter(is_correct=True).first().id}
            for question in self.questions[:25]
        ]
        response = self.client.post(
            f"/api/driving/mock-tests/{attempt.id}/submit/",
            {"answers": answers},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["score"], 100.0)
        self.assertTrue(response.data["passed"])

    def test_score_calculation_18_of_25_is_passed(self):
        self.client.force_authenticate(user=self.user)
        attempt = MockTestAttempt.objects.create(user=self.user, attempt_number=1, total_questions=25)
        selected_questions = self.questions[:25]
        attempt.questions.set(selected_questions)
        answers = []
        for index, question in enumerate(selected_questions):
            option = question.options.filter(order=1 if index < 18 else 2).first()
            answers.append({"question_id": question.id, "option_id": option.id})

        response = self.client.post(
            f"/api/driving/mock-tests/{attempt.id}/submit/",
            {"answers": answers},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["correct_answers"], 18)
        self.assertEqual(response.data["score"], 72.0)
        self.assertTrue(response.data["passed"])

    def test_score_calculation_17_of_25_is_failed(self):
        self.client.force_authenticate(user=self.user)
        attempt = MockTestAttempt.objects.create(user=self.user, attempt_number=1, total_questions=25)
        selected_questions = self.questions[:25]
        attempt.questions.set(selected_questions)
        answers = []
        for index, question in enumerate(selected_questions):
            option = question.options.filter(order=1 if index < 17 else 2).first()
            answers.append({"question_id": question.id, "option_id": option.id})

        response = self.client.post(
            f"/api/driving/mock-tests/{attempt.id}/submit/",
            {"answers": answers},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["correct_answers"], 17)
        self.assertEqual(response.data["score"], 68.0)
        self.assertFalse(response.data["passed"])

    def test_start_mock_test_unauthenticated(self):
        """Unauthenticated request can start a mock test without creating an attempt."""
        response = self.client.post("/api/driving/mock-tests/start/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIsNone(response.data["attempt"])
        self.assertEqual(len(response.data["questions"]), 25)
        self.assertEqual(MockTestAttempt.objects.count(), 0)

    def test_in_progress_attempts_do_not_count_toward_limit(self):
        """An unsubmitted (in-progress) attempt does not reduce the 3-test allowance."""
        self.client.force_authenticate(user=self.user)
        # Create 3 in-progress attempts (no completed_at)
        for i in range(1, 4):
            a = MockTestAttempt.objects.create(user=self.user, attempt_number=i, total_questions=25)
            a.questions.set(self.questions[:25])

        # Should still be allowed to start a new attempt
        response = self.client.post("/api/driving/mock-tests/start/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_submit_belongs_to_another_user_is_denied(self):
        """A user cannot submit another user's mock test attempt."""
        other_user = User.objects.create_user(username="otheruser", password="pass12345")
        attempt = MockTestAttempt.objects.create(user=other_user, attempt_number=1, total_questions=25)
        attempt.questions.set(self.questions[:25])

        self.client.force_authenticate(user=self.user)
        answers = [
            {"question_id": q.id, "option_id": q.options.filter(is_correct=True).first().id}
            for q in self.questions[:25]
        ]
        response = self.client.post(
            f"/api/driving/mock-tests/{attempt.id}/submit/",
            {"answers": answers},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_double_submit_is_rejected(self):
        """Submitting an already-completed attempt returns 400."""
        self.client.force_authenticate(user=self.user)
        attempt = MockTestAttempt.objects.create(
            user=self.user,
            attempt_number=1,
            total_questions=25,
            correct_answers=18,
            score=72.0,
            passed=True,
            completed_at=timezone.now(),
        )
        attempt.questions.set(self.questions[:25])
        answers = [
            {"question_id": q.id, "option_id": q.options.filter(is_correct=True).first().id}
            for q in self.questions[:25]
        ]
        response = self.client.post(
            f"/api/driving/mock-tests/{attempt.id}/submit/",
            {"answers": answers},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.data)

    def test_attempts_remaining_decrements_after_completion(self):
        """Result endpoint returns correct attempts_remaining after each submission."""
        self.client.force_authenticate(user=self.user)

        # Complete 1 attempt
        attempt = MockTestAttempt.objects.create(
            user=self.user,
            attempt_number=1,
            total_questions=25,
            correct_answers=20,
            score=80.0,
            passed=True,
            completed_at=timezone.now(),
        )
        attempt.questions.set(self.questions[:25])

        response = self.client.get(f"/api/driving/mock-tests/{attempt.id}/result/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["attempts_remaining"], 2)

    def test_exactly_three_completed_blocks_fourth_start(self):
        """Exactly 3 completed attempts block a 4th start (boundary check)."""
        self.client.force_authenticate(user=self.user)
        for i in range(1, 4):
            a = MockTestAttempt.objects.create(
                user=self.user,
                attempt_number=i,
                total_questions=25,
                correct_answers=18,
                score=72.0,
                passed=True,
                completed_at=timezone.now(),
            )
            a.questions.set(self.questions[:25])

        response = self.client.post("/api/driving/mock-tests/start/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["code"], "MOCK_TEST_LIMIT_REACHED")

    def test_result_endpoint_requires_authentication(self):
        """Result endpoint rejects unauthenticated requests."""
        attempt = MockTestAttempt.objects.create(
            user=self.user,
            attempt_number=1,
            total_questions=25,
            correct_answers=18,
            score=72.0,
            passed=True,
            completed_at=timezone.now(),
        )
        attempt.questions.set(self.questions[:25])
        response = self.client.get(f"/api/driving/mock-tests/{attempt.id}/result/")
        self.assertIn(response.status_code, [401, 403])
