from django.conf import settings
from rest_framework import serializers

from .models import (
    BuddyAvatar,
    BuddyMemory,
    BuddyMessage,
    BuddyMistake,
    BuddyPracticeTopic,
    BuddyProfile,
    BuddySession,
    BuddySettings,
    BuddyVocabulary,
)


class BuddyProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = BuddyProfile
        fields = (
            "id",
            "buddy_name",
            "native_language",
            "target_language",
            "speaking_level",
            "learning_goal",
            "favorite_topics",
            "weak_areas",
            "preferred_correction_style",
            "is_memory_enabled",
            "previous_conversation_summary",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class BuddySettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = BuddySettings
        fields = (
            "id",
            "personality",
            "voice_style",
            "voice_gender",
            "voice_age",
            "speaking_speed",
            "correction_level",
            "difficulty_level",
            "theme_color",
            "default_topic",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class BuddyAvatarSerializer(serializers.ModelSerializer):
    resolved_image_url = serializers.SerializerMethodField()

    class Meta:
        model = BuddyAvatar
        fields = (
            "id",
            "avatar_type",
            "name",
            "image",
            "image_url",
            "resolved_image_url",
            "consent_confirmed",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "resolved_image_url", "created_at", "updated_at")

    def get_resolved_image_url(self, obj):
        if obj.image:
            try:
                return obj.image.url
            except Exception:
                return obj.image_url
        return obj.image_url

    def validate(self, attrs):
        avatar_type = attrs.get("avatar_type") or getattr(self.instance, "avatar_type", "default")
        image = attrs.get("image") or getattr(self.instance, "image", None)
        consent_confirmed = attrs.get("consent_confirmed")
        if consent_confirmed is None and self.instance is not None:
            consent_confirmed = self.instance.consent_confirmed
        if avatar_type == "uploaded":
            if not consent_confirmed:
                raise serializers.ValidationError({"consent_confirmed": "Consent is required for uploaded avatars."})
            if not image:
                raise serializers.ValidationError({"image": "Upload an image for uploaded avatars."})
            max_bytes = getattr(settings, "SPEAKING_BUDDY_MAX_AVATAR_BYTES", 5 * 1024 * 1024)
            if getattr(image, "size", 0) > max_bytes:
                raise serializers.ValidationError({"image": "Avatar image is too large."})
            content_type = getattr(image, "content_type", "") or ""
            if content_type and not content_type.startswith("image/"):
                raise serializers.ValidationError({"image": "Avatar image must be an image file."})
        return attrs


class BuddySessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = BuddySession
        fields = (
            "id",
            "language",
            "topic",
            "status",
            "duration_seconds",
            "transcript",
            "ai_summary",
            "user_summary",
            "mistakes_detected",
            "vocabulary_practiced",
            "improvement_notes",
            "started_at",
            "ended_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "status",
            "duration_seconds",
            "transcript",
            "ai_summary",
            "user_summary",
            "mistakes_detected",
            "vocabulary_practiced",
            "improvement_notes",
            "started_at",
            "ended_at",
            "created_at",
            "updated_at",
        )


class BuddyMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = BuddyMessage
        fields = ("id", "session", "role", "text", "audio_url", "metadata", "created_at")
        read_only_fields = ("id", "created_at")


class BuddyMemorySerializer(serializers.ModelSerializer):
    class Meta:
        model = BuddyMemory
        fields = (
            "id",
            "memory_type",
            "key",
            "value",
            "importance",
            "source_session",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class BuddyPracticeTopicSerializer(serializers.ModelSerializer):
    class Meta:
        model = BuddyPracticeTopic
        fields = "__all__"
        read_only_fields = ("id", "created_at", "updated_at")


class BuddyVocabularySerializer(serializers.ModelSerializer):
    class Meta:
        model = BuddyVocabulary
        fields = "__all__"
        read_only_fields = ("id", "created_at", "updated_at")


class BuddyMistakeSerializer(serializers.ModelSerializer):
    class Meta:
        model = BuddyMistake
        fields = "__all__"
        read_only_fields = ("id", "created_at")


class BuddySessionStartSerializer(serializers.Serializer):
    language = serializers.ChoiceField(choices=BuddyProfile._meta.get_field("native_language").choices, required=False)
    topic = serializers.CharField(required=False, allow_blank=True)


class BuddySessionMessageSerializer(serializers.Serializer):
    session_id = serializers.IntegerField()
    text = serializers.CharField()


class BuddySessionEndSerializer(serializers.Serializer):
    session_id = serializers.IntegerField()


class BuddyRealtimeTokenSerializer(serializers.Serializer):
    session_id = serializers.IntegerField(required=False)


class BuddyMemoryUpdateSerializer(serializers.Serializer):
    memory_id = serializers.IntegerField()
    value = serializers.JSONField(required=False)
    importance = serializers.IntegerField(required=False, min_value=1, max_value=5)
    is_active = serializers.BooleanField(required=False)

