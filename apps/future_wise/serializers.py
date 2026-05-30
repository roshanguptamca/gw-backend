"""
Serializers for FutureWise / DearTomorrow API.
"""

from django.conf import settings
from django.utils import timezone
from rest_framework import serializers

from .models import AbuseLog, EmailReminder, ReminderAttachment
from .validators import (
    MAX_ATTACHMENTS,
    validate_attachment_count,
    validate_attachment_file,
    validate_scheduled_at,
)


# ── Nested ────────────────────────────────────────────────────────────────────


class ReminderAttachmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReminderAttachment
        fields = ["id", "original_filename", "content_type", "size_bytes", "created_at"]
        read_only_fields = fields


# ── Create ────────────────────────────────────────────────────────────────────


class CreateReminderSerializer(serializers.Serializer):
    """
    Used for POST /reminders/.
    Supports optional file attachments uploaded as multipart/form-data.
    """

    email = serializers.EmailField()
    subject = serializers.CharField(max_length=250)
    message = serializers.CharField()
    scheduled_at = serializers.DateTimeField()
    tier = serializers.ChoiceField(
        choices=EmailReminder.Tier.choices,
        default=EmailReminder.Tier.FREE,
    )
    letter_type = serializers.ChoiceField(
        choices=EmailReminder.LetterType.choices,
        default=EmailReminder.LetterType.FUTURE_SELF,
    )

    def validate_scheduled_at(self, value):
        validate_scheduled_at(value)
        return value

    def validate_email(self, value):
        return value.lower().strip()


class AttachmentUploadSerializer(serializers.Serializer):
    """
    Validates attachment files provided in a multipart request.
    Not a ModelSerializer — files are raw InMemoryUploadedFile objects.
    """

    attachments = serializers.ListField(
        child=serializers.FileField(),
        required=False,
        default=list,
    )

    def validate_attachments(self, files):
        validate_attachment_count(files)
        for f in files:
            validate_attachment_file(f)
        return files


# ── Read ──────────────────────────────────────────────────────────────────────


class ReminderDetailSerializer(serializers.ModelSerializer):
    attachments = ReminderAttachmentSerializer(many=True, read_only=True)
    brand_name = serializers.CharField(read_only=True)
    is_anonymous = serializers.BooleanField(read_only=True)

    class Meta:
        model = EmailReminder
        fields = [
            "id",
            "email",
            "subject",
            "message",
            "scheduled_at",
            "tier",
            "letter_type",
            "brand_name",
            "status",
            "retry_count",
            "sent_at",
            "created_at",
            "attachments",
            "is_anonymous",
        ]
        read_only_fields = fields


class ReminderListSerializer(serializers.ModelSerializer):
    attachment_count = serializers.SerializerMethodField()

    class Meta:
        model = EmailReminder
        fields = [
            "id",
            "email",
            "subject",
            "scheduled_at",
            "tier",
            "letter_type",
            "status",
            "sent_at",
            "created_at",
            "attachment_count",
        ]
        read_only_fields = fields

    def get_attachment_count(self, obj) -> int:
        return obj.attachments.count()


# ── Verification ──────────────────────────────────────────────────────────────


class VerifyEmailSerializer(serializers.Serializer):
    """Used for GET /verify/<token>/"""

    token = serializers.CharField()
