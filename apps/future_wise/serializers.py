"""
Serializers for FutureWise / DearTomorrow API.
"""

import re

from rest_framework import serializers

from .models import EmailReminder, ReminderAttachment, ReminderDeliveryLog, UserNotificationPreference
from .validators import validate_attachment_count, validate_attachment_file, validate_scheduled_at

_E164_RE = re.compile(r"^\+[1-9]\d{7,14}$")
SUPPORTED_CHANNELS = {"email", "sms", "voice", "whatsapp", "telegram"}
CHANNEL_ALIASES = {"call": "voice", "voice_call": "voice"}


def _default_email_channels():
    return ["email"]


class ChannelListField(serializers.ListField):
    def __init__(self, **kwargs):
        super().__init__(child=serializers.CharField(max_length=20), **kwargs)

    def to_internal_value(self, data):
        if isinstance(data, str):
            data = [channel.strip() for channel in data.split(",") if channel.strip()]
        elif isinstance(data, (list, tuple)):
            data = [channel.strip() for value in data for channel in str(value).split(",") if channel.strip()]
        channels = super().to_internal_value(data)
        normalized = []
        for channel in channels:
            code = CHANNEL_ALIASES.get(channel.lower().strip(), channel.lower().strip())
            if code not in SUPPORTED_CHANNELS:
                raise serializers.ValidationError(f"Unsupported reminder channel: {channel}.")
            if code not in normalized:
                normalized.append(code)
        if not normalized:
            raise serializers.ValidationError("Select at least one reminder channel.")
        return normalized


def validate_channel_contacts(data, instance=None):
    channels = data.get("channels")
    if channels is None and instance is not None:
        channels = instance.selected_channels
    channels = channels or ["email"]

    email = data.get("email", instance.email if instance is not None else "")
    phone_number = data.get("phone_number", instance.phone_number if instance is not None else "")
    telegram_chat_id = data.get(
        "telegram_chat_id",
        instance.telegram_chat_id if instance is not None else "",
    )
    errors = {}
    if "email" in channels and not email:
        errors["email"] = "An email address is required for email delivery."
    if {"sms", "voice", "whatsapp"} & set(channels) and not phone_number:
        errors["phone_number"] = "A phone number is required for SMS, Voice, or WhatsApp channels."
    if "telegram" in channels and not telegram_chat_id:
        errors["telegram_chat_id"] = (
            "A Telegram chat ID is required for the Telegram channel. "
            "Send /start to the GuideWisey bot to obtain it."
        )
    if errors:
        raise serializers.ValidationError(errors)
    return data


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
    Also accepts multi-channel delivery options.
    """

    email = serializers.EmailField(required=False, allow_blank=True, default="")
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
        allow_blank=True,
    )
    # Multi-channel fields
    channels = ChannelListField(
        required=False,
        default=_default_email_channels,
        help_text="Delivery channels e.g. ['email','sms','telegram']",
    )
    phone_number = serializers.CharField(
        max_length=20,
        required=False,
        default="",
        allow_blank=True,
        help_text="E.164 format e.g. +447700900123 — required for SMS/Voice/WhatsApp",
    )
    telegram_chat_id = serializers.CharField(
        max_length=50,
        required=False,
        default="",
        allow_blank=True,
        help_text="Obtained by sending /start to the GuideWisey Telegram bot",
    )

    def validate_scheduled_at(self, value):
        validate_scheduled_at(value)
        return value

    def validate_email(self, value):
        return value.lower().strip()

    def validate_phone_number(self, value: str) -> str:
        if not value:
            return value
        if not _E164_RE.match(value):
            raise serializers.ValidationError("Phone number must be in E.164 format, e.g. +447700900123")
        return value

    def validate(self, data: dict) -> dict:
        return validate_channel_contacts(data)


class UpdateReminderSerializer(serializers.ModelSerializer):
    channels = ChannelListField(required=False)
    letter_type = serializers.ChoiceField(choices=EmailReminder.LetterType.choices, required=False, allow_blank=True)

    class Meta:
        model = EmailReminder
        fields = [
            "email",
            "subject",
            "message",
            "scheduled_at",
            "tier",
            "letter_type",
            "channels",
            "phone_number",
            "telegram_chat_id",
        ]
        extra_kwargs = {
            "email": {"required": False, "allow_blank": True},
            "subject": {"required": False},
            "message": {"required": False},
            "scheduled_at": {"required": False},
            "phone_number": {"required": False, "allow_blank": True},
            "telegram_chat_id": {"required": False, "allow_blank": True},
        }

    def validate_scheduled_at(self, value):
        validate_scheduled_at(value)
        return value

    def validate_email(self, value):
        return value.lower().strip()

    def validate_phone_number(self, value):
        if value and not _E164_RE.match(value):
            raise serializers.ValidationError("Phone number must be in E.164 format, e.g. +447700900123")
        return value

    def validate(self, data):
        return validate_channel_contacts(data, self.instance)

    def update(self, instance, validated_data):
        channels = validated_data.pop("channels", None)
        if channels is not None:
            instance.channels = channels
            instance.channels_requested = ",".join(channels)
        return super().update(instance, validated_data)


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
    channels = serializers.ListField(source="selected_channels", read_only=True)
    letter_type_description = serializers.CharField(read_only=True)

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
            "letter_type_description",
            "brand_name",
            "status",
            "retry_count",
            "sent_at",
            "created_at",
            "channels_requested",
            "channels",
            "phone_number",
            "telegram_chat_id",
            "attachments",
            "is_anonymous",
        ]
        read_only_fields = fields


class ReminderListSerializer(serializers.ModelSerializer):
    attachment_count = serializers.SerializerMethodField()
    channels = serializers.ListField(source="selected_channels", read_only=True)
    letter_type_description = serializers.CharField(read_only=True)

    class Meta:
        model = EmailReminder
        fields = [
            "id",
            "email",
            "subject",
            "scheduled_at",
            "tier",
            "letter_type",
            "letter_type_description",
            "status",
            "sent_at",
            "created_at",
            "attachment_count",
            "channels",
            "channels_requested",
            "phone_number",
            "telegram_chat_id",
        ]
        read_only_fields = fields

    def get_attachment_count(self, obj) -> int:
        return obj.attachments.count()


# ── Verification ──────────────────────────────────────────────────────────────


class VerifyEmailSerializer(serializers.Serializer):
    """Used for GET /verify/<token>/"""

    token = serializers.CharField()


# ── Delivery Status ───────────────────────────────────────────────────────────


class DeliveryLogSerializer(serializers.ModelSerializer):
    channel = serializers.CharField(source="channel.code", read_only=True)

    class Meta:
        model = ReminderDeliveryLog
        fields = [
            "channel",
            "attempt_number",
            "status",
            "provider_message_id",
            "error_message",
            "attempted_at",
            "completed_at",
        ]
        read_only_fields = fields


class ReminderDeliveryStatusSerializer(serializers.ModelSerializer):
    logs = DeliveryLogSerializer(source="delivery_logs", many=True, read_only=True)

    class Meta:
        model = EmailReminder
        fields = ["id", "status", "retry_count", "sent_at", "logs"]
        read_only_fields = fields


# ── Notification Preferences ──────────────────────────────────────────────────


class NotificationPreferenceSerializer(serializers.ModelSerializer):
    channel_code = serializers.CharField(source="channel.code", read_only=True)
    channel_name = serializers.CharField(source="channel.display_name", read_only=True)

    class Meta:
        model = UserNotificationPreference
        fields = [
            "id",
            "channel_code",
            "channel_name",
            "is_opted_in",
            "phone_number",
            "telegram_chat_id",
            "whatsapp_opted_in",
            "updated_at",
        ]
        read_only_fields = ["id", "channel_code", "channel_name", "updated_at"]

    def validate_phone_number(self, value: str) -> str:
        if value and not _E164_RE.match(value):
            raise serializers.ValidationError("Phone number must be E.164 format e.g. +447700900123")
        return value


class UpdateNotificationPreferencesSerializer(serializers.Serializer):
    """
    Bulk-update notification preferences via PUT /notification-preferences/.

    Payload example:
        {
            "sms": {"is_opted_in": true, "phone_number": "+447700900123"},
            "telegram": {"is_opted_in": true, "telegram_chat_id": "123456789"},
            "whatsapp": {"is_opted_in": false}
        }
    """

    sms = serializers.DictField(required=False, child=serializers.CharField(allow_blank=True))
    voice = serializers.DictField(required=False, child=serializers.CharField(allow_blank=True))
    whatsapp = serializers.DictField(required=False, child=serializers.CharField(allow_blank=True))
    telegram = serializers.DictField(required=False, child=serializers.CharField(allow_blank=True))


# ── Test Send ─────────────────────────────────────────────────────────────────


class TestReminderSerializer(serializers.Serializer):
    """Used for POST /reminders/<id>/test/"""

    channel = serializers.ChoiceField(choices=["email", "sms", "voice", "whatsapp", "telegram"])


class LetterTypeOptionSerializer(serializers.Serializer):
    value = serializers.CharField()
    label = serializers.CharField()
    description = serializers.CharField()


class AIMessageGenerationRequestSerializer(serializers.Serializer):
    letter_type = serializers.ChoiceField(choices=EmailReminder.LetterType.choices, allow_blank=True)
    occasion = serializers.CharField(required=False, allow_blank=True, default="")
    tone = serializers.CharField(required=False, allow_blank=True, default="")
    recipient_name = serializers.CharField(required=False, allow_blank=True, default="")
    language = serializers.CharField(required=False, allow_blank=True, default="")
    channels = ChannelListField(required=False, default=_default_email_channels)
    extra_context = serializers.CharField(required=False, allow_blank=True, default="")


class AIMessageGenerationResponseSerializer(serializers.Serializer):
    subject = serializers.CharField()
    email_body = serializers.CharField()
    short_message = serializers.CharField()
    call_script = serializers.CharField(allow_blank=True)
