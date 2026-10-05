import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

LEVELS = [(value, value) for value in ("A1", "A2", "B1", "B2")]
SKILLS = [(value, value.title()) for value in ("reading", "writing", "listening", "speaking", "knm")]


def validate_payload(payload, level, skill):
    if not isinstance(payload, dict) or payload.get("level") != level or payload.get("skill") != skill:
        raise ValidationError("Question level and skill must match the payload.")
    if not payload.get("prompt") or payload.get("provenance") != "original":
        raise ValidationError("Original question provenance and a prompt are required.")
    if skill in ("reading", "listening", "knm"):
        options = payload.get("options")
        answer = payload.get("answer")
        if (
            not isinstance(options, list)
            or len(options) != 3
            or not all(isinstance(option, str) and option.strip() for option in options)
            or len(set(options)) != 3
            or type(answer) is not int
            or not 0 <= answer < 3
            or not payload.get("explanation")
            or not payload.get("transcript" if skill == "listening" else "text")
        ):
            raise ValidationError("Invalid multiple-choice question.")
    else:
        criteria = payload.get("criteria")
        if not payload.get("modelAnswer") or not isinstance(criteria, list) or not criteria:
            raise ValidationError("A model answer and assessment criteria are required.")
        if not all(isinstance(criterion, str) and criterion.strip() for criterion in criteria):
            raise ValidationError("Assessment criteria must contain non-empty text.")
        if skill == "speaking" and (
            type(payload.get("responseSeconds")) is not int
            or not 1 <= payload["responseSeconds"] <= 180
            or type(payload.get("preparationSeconds")) is not int
            or not 0 <= payload["preparationSeconds"] <= 120
        ):
            raise ValidationError("Invalid speaking timings.")


class PracticeMedia(models.Model):
    """Immutable generated clips; content is stored in the database, never a public bucket."""

    code = models.CharField(max_length=100, unique=True)
    content = models.BinaryField(editable=False)
    mime_type = models.CharField(max_length=40, default="video/mp4")
    sha256 = models.CharField(max_length=64)
    duration_seconds = models.FloatField()


class PracticeQuestion(models.Model):
    code = models.CharField(max_length=80, unique=True)
    level = models.CharField(max_length=2, choices=LEVELS)
    skill = models.CharField(max_length=10, choices=SKILLS)
    media = models.ForeignKey(PracticeMedia, null=True, blank=True, on_delete=models.PROTECT)
    payload = models.JSONField()
    is_active = models.BooleanField(default=True)
    review_status = models.CharField(
        max_length=20, default="draft", choices=[("draft", "Draft"), ("reviewed", "Reviewed")]
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["level", "skill", "is_active"], name="dutch_question_pool")]

    def clean(self):
        super().clean()
        validate_payload(self.payload, self.level, self.skill)

    def __str__(self):
        return self.code


class PracticeAttempt(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="dutch_practice_attempts")
    level = models.CharField(max_length=2, choices=LEVELS)
    skill = models.CharField(max_length=10, choices=SKILLS)
    mock_test = models.PositiveSmallIntegerField()
    status = models.CharField(
        max_length=12,
        default="active",
        choices=[("active", "Active"), ("completed", "Completed"), ("abandoned", "Abandoned"), ("expired", "Expired")],
    )
    question_signature = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    completed_at = models.DateTimeField(null=True, blank=True)
    score = models.PositiveSmallIntegerField(null=True, blank=True)
    assisted = models.BooleanField(default=False)
    mode = models.CharField(max_length=10, default="practice", choices=[("practice", "Practice"), ("mock", "Mock")])
    bank_version = models.CharField(max_length=40, default="legacy-v2")
    blueprint = models.JSONField(default=dict, blank=True)
    last_position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user"], condition=models.Q(status="active"), name="dutch_one_active_attempt"
            ),
            models.CheckConstraint(condition=models.Q(mock_test__gte=1, mock_test__lte=20), name="dutch_test_range"),
        ]
        indexes = [models.Index(fields=["user", "level", "skill", "created_at"], name="dutch_user_history")]


class AttemptQuestion(models.Model):
    attempt = models.ForeignKey(PracticeAttempt, on_delete=models.CASCADE, related_name="items")
    position = models.PositiveSmallIntegerField()
    # Keep the selected wording, option order and answer key stable if the bank is edited later.
    media = models.ForeignKey(PracticeMedia, null=True, blank=True, on_delete=models.PROTECT)
    snapshot = models.JSONField()
    response = models.JSONField(default=dict, blank=True)
    answered_at = models.DateTimeField(null=True, blank=True)
    media_started_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["position"]
        constraints = [models.UniqueConstraint(fields=["attempt", "position"], name="dutch_attempt_position")]
