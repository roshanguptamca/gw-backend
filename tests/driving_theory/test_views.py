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
        cls.topic = DrivingTopic.objects.create(
            slug="traffic-signs",
            title="Verkeersborden",
            summary="Learn the most common Dutch traffic signs.",
            dutch_terms=[{"term": "verbodsbord", "meaning": "prohibition sign"}],
            order=1,
        )
        cls.lesson = DrivingLesson.objects.create(
            topic=cls.topic,
            title="Traffic signs basics",
            summary="Understand shapes, colours, and sign priorities.",
            difficulty="easy",
            estimated_minutes=12,
            order=1,
        )
        DrivingLessonSection.objects.create(
            lesson=cls.lesson,
            title="Shapes and colours",
            content="Round red signs prohibit, blue signs instruct, and triangles warn.",
            examples=["A red circle often bans an action."],
            dutch_keywords=["verbodsbord", "waarschuwingsbord"],
            order=1,
        )
        DrivingLessonSection.objects.create(
            lesson=cls.lesson,
            title="Reading context",
            content="Always combine the sign meaning with the road layout and traffic around you.",
            examples=["A sign can be repeated after a junction."],
            dutch_keywords=["onderbord", "rijstrook"],
            order=2,
        )

        cls.questions = []
        for idx in range(1, 31):
            question = DrivingQuestion.objects.create(
                topic=cls.topic,
                lesson=cls.lesson,
                question_text=f"Practice question {idx}?",
                explanation=f"Explanation for question {idx}.",
                difficulty=1 if idx <= 10 else 2 if idx <= 20 else 3,
                points=1,
            )
            correct_option = None
            for option_idx in range(1, 5):
                option = DrivingQuestionOption.objects.create(
                    question=question,
                    option_text=f"Question {idx} option {option_idx}",
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
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["slug"], self.topic.slug)
        self.assertEqual(response.data[0]["question_count"], 30)

    def test_get_topic_detail_returns_lessons(self):
        response = self.client.get(f"/api/driving/topics/{self.topic.slug}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["slug"], self.topic.slug)
        self.assertEqual(len(response.data["lessons"]), 1)

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
