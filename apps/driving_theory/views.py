from django.db.models import Count, Prefetch, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers as drf_serializers
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    DrivingLesson,
    DrivingQuestion,
    DrivingQuestionOption,
    DrivingTopic,
    MockTestAnswer,
    MockTestAttempt,
    UserDrivingProgress,
)
from .serializers import (
    DrivingLessonDetailSerializer,
    DrivingQuestionSerializer,
    DrivingTopicDetailSerializer,
    DrivingTopicListSerializer,
    MockTestAttemptSerializer,
    MockTestSubmitSerializer,
    ProgressUpdateSerializer,
    UserDrivingProgressSerializer,
)


@extend_schema(tags=["Driving Theory"])
class TopicsListView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(summary="List active driving theory topics", responses={200: DrivingTopicListSerializer(many=True)})
    def get(self, request):
        topics = (
            DrivingTopic.objects.filter(is_active=True)
            .annotate(question_count=Count("questions", filter=Q(questions__is_active=True), distinct=True))
            .order_by("order")
        )
        return Response(DrivingTopicListSerializer(topics, many=True).data)


@extend_schema(tags=["Driving Theory"])
class TopicDetailView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(summary="Get a driving theory topic with lessons", responses={200: DrivingTopicDetailSerializer})
    def get(self, request, slug):
        topic = get_object_or_404(
            DrivingTopic.objects.prefetch_related(
                Prefetch(
                    "lessons",
                    queryset=DrivingLesson.objects.filter(is_active=True).prefetch_related("sections").order_by("order"),
                )
            ),
            slug=slug,
            is_active=True,
        )
        return Response(DrivingTopicDetailSerializer(topic).data)


@extend_schema(tags=["Driving Theory"])
class LessonDetailView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(summary="Get lesson details with sections and practice questions", responses={200: DrivingLessonDetailSerializer})
    def get(self, request, pk):
        lesson = get_object_or_404(
            DrivingLesson.objects.select_related("topic").prefetch_related(
                "sections",
                Prefetch(
                    "questions",
                    queryset=DrivingQuestion.objects.filter(is_active=True).prefetch_related("options"),
                ),
            ),
            pk=pk,
            is_active=True,
            topic__is_active=True,
        )
        return Response(DrivingLessonDetailSerializer(lesson).data)


@extend_schema(tags=["Driving Theory"])
class TopicQuizView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Get a 10-question topic quiz",
        responses={
            200: inline_serializer(
                "TopicQuizResponse",
                fields={
                    "topic": drf_serializers.DictField(),
                    "questions": DrivingQuestionSerializer(many=True),
                },
            )
        },
    )
    def get(self, request, slug):
        topic = get_object_or_404(DrivingTopic, slug=slug, is_active=True)
        questions = list(topic.questions.filter(is_active=True).prefetch_related("options").order_by("?")[:10])
        return Response(
            {
                "topic": {"slug": topic.slug, "title": topic.title, "summary": topic.summary},
                "questions": DrivingQuestionSerializer(
                    questions,
                    many=True,
                    context={"hide_correct_answers": True},
                ).data,
            }
        )


@extend_schema(tags=["Driving Theory"])
class ProgressView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="List user driving progress", responses={200: UserDrivingProgressSerializer(many=True)})
    def get(self, request):
        progress = UserDrivingProgress.objects.filter(user=request.user).select_related("topic", "lesson").order_by("topic__order")
        return Response(UserDrivingProgressSerializer(progress, many=True).data)

    @extend_schema(summary="Save or update user driving progress", request=ProgressUpdateSerializer, responses={200: UserDrivingProgressSerializer})
    def post(self, request):
        serializer = ProgressUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        topic = get_object_or_404(DrivingTopic, slug=data["topic_slug"], is_active=True)
        lesson = None
        if data.get("lesson_id"):
            lesson = get_object_or_404(DrivingLesson, pk=data["lesson_id"], topic=topic, is_active=True)

        if data.get("question_id"):
            get_object_or_404(DrivingQuestion, pk=data["question_id"], topic=topic, is_active=True)

        progress, _ = UserDrivingProgress.objects.get_or_create(
            user=request.user,
            topic=topic,
            defaults={"lesson": lesson},
        )

        if lesson:
            progress.lesson = lesson

        lessons_completed = list(progress.lessons_completed or [])
        if data.get("lesson_completed") and lesson and lesson.id not in lessons_completed:
            lessons_completed.append(lesson.id)
            progress.lessons_completed = lessons_completed

        if data.get("question_id"):
            progress.questions_answered += 1
            if data.get("answer_correct"):
                progress.questions_correct += 1

        progress.save()
        return Response(UserDrivingProgressSerializer(progress).data)


@extend_schema(tags=["Driving Theory"])
class MockTestStartView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Start a mock driving theory test",
        responses={
            201: inline_serializer(
                "MockTestStartResponse",
                fields={
                    "attempt": MockTestAttemptSerializer(),
                    "questions": DrivingQuestionSerializer(many=True),
                },
            ),
            403: inline_serializer(
                "MockTestLimitError",
                fields={"error": drf_serializers.CharField(), "code": drf_serializers.CharField()},
            ),
        },
    )
    def post(self, request):
        completed_attempts = MockTestAttempt.objects.filter(user=request.user, completed_at__isnull=False).count()
        if completed_attempts >= 3:
            return Response(
                {
                    "error": "You have used all 3 free mock tests.",
                    "code": "MOCK_TEST_LIMIT_REACHED",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        questions = list(
            DrivingQuestion.objects.filter(is_active=True, topic__is_active=True).prefetch_related("options").order_by("?")[:25]
        )
        attempt = MockTestAttempt.objects.create(
            user=request.user,
            attempt_number=MockTestAttempt.objects.filter(user=request.user).count() + 1,
            total_questions=len(questions),
        )
        attempt.questions.set(questions)
        return Response(
            {
                "attempt": MockTestAttemptSerializer(attempt).data,
                "questions": DrivingQuestionSerializer(
                    questions,
                    many=True,
                    context={"hide_correct_answers": True},
                ).data,
            },
            status=status.HTTP_201_CREATED,
        )


@extend_schema(tags=["Driving Theory"])
class MockTestSubmitView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Submit a mock driving theory test",
        request=MockTestSubmitSerializer,
        responses={
            200: inline_serializer(
                "MockTestSubmitResponse",
                fields={
                    "id": drf_serializers.IntegerField(),
                    "score": drf_serializers.FloatField(),
                    "passed": drf_serializers.BooleanField(),
                    "correct_answers": drf_serializers.IntegerField(),
                    "total_questions": drf_serializers.IntegerField(),
                },
            )
        },
    )
    def post(self, request, pk):
        attempt = get_object_or_404(MockTestAttempt.objects.prefetch_related("questions"), pk=pk, user=request.user)
        if attempt.completed_at:
            return Response({"error": "This mock test has already been submitted."}, status=status.HTTP_400_BAD_REQUEST)

        serializer = MockTestSubmitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        submitted_answers = {item["question_id"]: item.get("option_id") for item in serializer.validated_data["answers"]}

        question_ids = list(attempt.questions.values_list("id", flat=True))
        option_map = {
            option.id: option
            for option in DrivingQuestionOption.objects.filter(question_id__in=question_ids)
        }

        correct_answers = 0
        for question_id in question_ids:
            selected_option = option_map.get(submitted_answers.get(question_id))
            if selected_option and selected_option.question_id != question_id:
                selected_option = None
            is_correct = bool(selected_option and selected_option.is_correct)
            MockTestAnswer.objects.update_or_create(
                attempt=attempt,
                question_id=question_id,
                defaults={"selected_option": selected_option, "is_correct": is_correct},
            )
            if is_correct:
                correct_answers += 1

        total_questions = attempt.total_questions or len(question_ids)
        score = round((correct_answers / total_questions) * 100, 2) if total_questions else 0.0
        attempt.correct_answers = correct_answers
        attempt.score = score
        attempt.passed = score >= 70
        attempt.completed_at = timezone.now()
        attempt.save(update_fields=["correct_answers", "score", "passed", "completed_at"])

        return Response(
            {
                "id": attempt.id,
                "score": score,
                "passed": attempt.passed,
                "correct_answers": correct_answers,
                "total_questions": total_questions,
            }
        )


@extend_schema(tags=["Driving Theory"])
class MockTestResultView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Get detailed mock test results")
    def get(self, request, pk):
        attempt = get_object_or_404(
            MockTestAttempt.objects.filter(user=request.user).prefetch_related(
                Prefetch("questions", queryset=DrivingQuestion.objects.prefetch_related("options", "topic")),
                "answers__selected_option",
            ),
            pk=pk,
        )
        if not attempt.completed_at:
            return Response({"error": "This mock test has not been submitted yet."}, status=status.HTTP_400_BAD_REQUEST)

        answer_map = {answer.question_id: answer for answer in attempt.answers.all()}
        questions = []
        for question in attempt.questions.all():
            selected_answer = answer_map.get(question.id)
            correct_option = next((option for option in question.options.all() if option.is_correct), None)
            questions.append(
                {
                    "id": question.id,
                    "topic": question.topic.title,
                    "question_text": question.question_text,
                    "explanation": question.explanation,
                    "selected_option": {
                        "id": selected_answer.selected_option_id,
                        "option_text": selected_answer.selected_option.option_text,
                    }
                    if selected_answer and selected_answer.selected_option
                    else None,
                    "correct_option": {
                        "id": correct_option.id,
                        "option_text": correct_option.option_text,
                    }
                    if correct_option
                    else None,
                    "is_correct": bool(selected_answer and selected_answer.is_correct),
                }
            )

        completed_attempts = MockTestAttempt.objects.filter(user=request.user, completed_at__isnull=False).count()
        return Response(
            {
                "id": attempt.id,
                "attempt_number": attempt.attempt_number,
                "started_at": attempt.started_at,
                "completed_at": attempt.completed_at,
                "score": attempt.score,
                "passed": attempt.passed,
                "total_questions": attempt.total_questions,
                "correct_answers": attempt.correct_answers,
                "attempts_remaining": max(0, 3 - completed_attempts),
                "questions": questions,
            }
        )
