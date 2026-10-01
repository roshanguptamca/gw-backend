from django.db import IntegrityError, transaction
from django.db.models import Count
from django.shortcuts import get_object_or_404

from drf_spectacular.utils import extend_schema
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .models import LEVELS, SKILLS, PracticeAttempt, PracticeQuestion
from .serializers import AnswerSerializer, StartAttemptSerializer


@extend_schema(tags=["Dutch Practice"])
class AuthenticatedPracticeView(APIView):
    permission_classes = [IsAuthenticated]

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        return response

    def get_attempt(self, request, attempt_id, locked=False):
        services.expire_attempts(request.user)
        queryset = PracticeAttempt.objects.filter(user=request.user)
        if locked:
            queryset = queryset.select_for_update()
        return get_object_or_404(queryset, pk=attempt_id)


class CatalogView(AuthenticatedPracticeView):
    def get(self, request):
        services.expire_attempts(request.user)
        counts = {
            (row["level"], row["skill"]): row["count"]
            for row in PracticeQuestion.objects.filter(is_active=True)
            .values("level", "skill")
            .annotate(count=Count("id"))
        }
        active = PracticeAttempt.objects.filter(user=request.user, status="active").first()
        return Response(
            {
                "levels": [level for level, _ in LEVELS],
                "skills": [{"id": skill, "label": label} for skill, label in SKILLS],
                "pools": [
                    {
                        "level": level,
                        "skill": skill,
                        "available": counts.get((level, skill), 0) >= 8,
                        "question_count": counts.get((level, skill), 0),
                        "test_count": services.TEST_COUNT,
                        "questions_per_test": services.QUESTIONS_PER_TEST,
                    }
                    for level, _ in LEVELS
                    for skill, _ in SKILLS
                ],
                "active_attempt": services.summary(active) if active else None,
                "format": "short-practice-preview",
            }
        )


class AttemptsView(AuthenticatedPracticeView):
    def get(self, request):
        services.expire_attempts(request.user)
        try:
            page = int(request.query_params.get("page", 1))
            if page < 1:
                raise ValueError
        except ValueError:
            raise ValidationError("Page must be a positive integer.")
        attempts = PracticeAttempt.objects.filter(user=request.user)
        start = (page - 1) * 20
        return Response(
            {
                "count": attempts.count(),
                "page": page,
                "results": [services.summary(a) for a in attempts[start : start + 20]],
            }
        )

    @extend_schema(request=StartAttemptSerializer)
    def post(self, request):
        serializer = StartAttemptSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            attempt = services.start_attempt(request.user, **serializer.validated_data)
        except IntegrityError:
            active = PracticeAttempt.objects.filter(user=request.user, status="active").first()
            if not active:
                raise
            raise services.ActiveAttemptConflict(
                {"detail": "Finish or abandon your active test first.", "attempt_id": str(active.id)}
            )
        return Response(services.summary(attempt), status=201)


class AttemptView(AuthenticatedPracticeView):
    def get(self, request, attempt_id):
        return Response(services.summary(self.get_attempt(request, attempt_id)))


class QuestionView(AuthenticatedPracticeView):
    def get(self, request, attempt_id, position):
        attempt = self.get_attempt(request, attempt_id)
        services.require_active(attempt)
        item = get_object_or_404(attempt.items, position=position)
        return Response(services.public_question(item))

    @extend_schema(request=AnswerSerializer)
    @transaction.atomic
    def post(self, request, attempt_id, position):
        attempt = self.get_attempt(request, attempt_id, locked=True)
        serializer = AnswerSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item = services.save_answer(attempt, position, serializer.validated_data)
        return Response({"saved": True, "position": item.position})


class SubmitView(AuthenticatedPracticeView):
    @transaction.atomic
    def post(self, request, attempt_id):
        attempt = self.get_attempt(request, attempt_id, locked=True)
        services.submit_attempt(attempt)
        return Response(services.result(attempt))


class AbandonView(AuthenticatedPracticeView):
    @transaction.atomic
    def post(self, request, attempt_id):
        attempt = self.get_attempt(request, attempt_id, locked=True)
        if attempt.status == "active":
            attempt.status = "abandoned"
            attempt.save(update_fields=["status"])
        return Response(services.summary(attempt))


class ResultView(AuthenticatedPracticeView):
    def get(self, request, attempt_id):
        return Response(services.result(self.get_attempt(request, attempt_id)))


class MediaView(AuthenticatedPracticeView):
    def get(self, request, attempt_id, position):
        import re

        from django.http import HttpResponse

        attempt = self.get_attempt(request, attempt_id)
        if attempt.status not in ("active", "completed"):
            raise services.AttemptStateConflict()
        item = get_object_or_404(attempt.items.select_related("media"), position=position, media__isnull=False)
        data = bytes(item.media.content)
        size = len(data)
        start, end = 0, size - 1
        status = 200
        requested = request.headers.get("Range")
        if requested:
            match = re.fullmatch(r"bytes=(\d*)-(\d*)", requested)
            if not match or not any(match.groups()):
                response = HttpResponse(status=416)
                response["Content-Range"] = f"bytes */{size}"
                return response
            left, right = match.groups()
            if left:
                start = int(left)
                end = min(int(right), size - 1) if right else size - 1
            else:
                start = max(0, size - int(right))
            if start > end or start >= size or (not left and int(right) == 0):
                response = HttpResponse(status=416)
                response["Content-Range"] = f"bytes */{size}"
                return response
            status = 206
        response = HttpResponse(data[start : end + 1], status=status, content_type=item.media.mime_type)
        response["Accept-Ranges"] = "bytes"
        response["Content-Length"] = str(end - start + 1)
        response["X-Content-Type-Options"] = "nosniff"
        if status == 206:
            response["Content-Range"] = f"bytes {start}-{end}/{size}"
        return response
