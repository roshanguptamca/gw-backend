from django.conf import settings

from rest_framework import serializers

from .models import (
    Buddy3DAvatar,
    BuddyAvatar,
    BuddyGeneratedAvatar,
    BuddyMemory,
    BuddyMessage,
    BuddyMistake,
    BuddyPracticeTopic,
    BuddyProfile,
    BuddySession,
    BuddySettings,
    BuddyVocabulary,
)
from .services.voice_mapping import resolve_voice


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
            "selected_voice",
            "speaking_speed",
            "correction_level",
            "difficulty_level",
            "theme_color",
            "default_topic",
            "avatar_render_mode",
            "selected_3d_avatar_slug",
            "selected_generated_avatar",
            "selected_avatar",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def _apply_voice_mapping(self, validated_data, instance=None):
        """Keep selected_voice consistent with voice_gender/voice_age.

        If the caller changes gender/age but does not explicitly choose a
        selected_voice in the same request, derive it via the single voice
        mapping function so the resulting voice always matches the chosen
        gender/age instead of being left stale or mismatched.
        """
        gender_provided = "voice_gender" in validated_data
        age_provided = "voice_age" in validated_data
        if not gender_provided and not age_provided:
            return validated_data
        if "selected_voice" in validated_data:
            return validated_data
        gender = validated_data.get("voice_gender", getattr(instance, "voice_gender", None))
        age = validated_data.get("voice_age", getattr(instance, "voice_age", None))
        validated_data["selected_voice"] = resolve_voice(gender, age)
        return validated_data

    def create(self, validated_data):
        validated_data = self._apply_voice_mapping(validated_data)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        validated_data = self._apply_voice_mapping(validated_data, instance=instance)
        return super().update(instance, validated_data)


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
        request = self.context.get("request") if hasattr(self, "context") else None

        def absolute(url):
            if not url:
                return url
            if str(url).startswith(("http://", "https://")):
                return url
            if request:
                host = getattr(request, "_current_scheme_host", "") or ""
                if not host and hasattr(request, "build_absolute_uri"):
                    try:
                        host = request.build_absolute_uri("/").rstrip("/")
                    except Exception:
                        host = ""
                if host:
                    return f"{host}{url if str(url).startswith('/') else '/' + str(url)}"
            return url

        if obj.image:
            try:
                if getattr(obj.image, "name", "") and obj.image.storage.exists(obj.image.name):
                    return absolute(obj.image.url)
            except Exception:
                return absolute(obj.image_url)
        return absolute(obj.image_url)

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


class Buddy3DAvatarSerializer(serializers.ModelSerializer):
    class Meta:
        model = Buddy3DAvatar
        fields = (
            "id",
            "name",
            "slug",
            "gender_style",
            "age_style",
            "personality",
            "default_voice",
            "voice_style",
            "mood",
            "backstory",
            "thumbnail",
            "glb_file",
            "model_url",
            "thumbnail_url",
            "base_skin_material_key",
            "base_hair_material_key",
            "supported_customizations",
            "supported_blendshapes",
            "has_full_body",
            "has_hair",
            "has_hands",
            "has_feet",
            "idle_animation",
            "talking_animation",
            "listening_animation",
            "thinking_animation",
            "emotion_set",
            "is_premium",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class BuddyGeneratedAvatarSerializer(serializers.ModelSerializer):
    source_image_url = serializers.SerializerMethodField()

    class Meta:
        model = BuddyGeneratedAvatar
        fields = (
            "id",
            "source_image",
            "source_image_url",
            "generated_glb_url",
            "generated_thumbnail_url",
            "generated_model_path",
            "generated_thumbnail",
            "appearance_config",
            "detected_features",
            "generation_logs",
            "generation_method",
            "selected_base_avatar",
            "provider",
            "provider_job_id",
            "status",
            "consent_confirmed",
            "user_generated",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "source_image_url",
            "detected_features",
            "appearance_config",
            "generation_logs",
            "generation_method",
            "selected_base_avatar",
            "status",
            "created_at",
            "updated_at",
        )

    def get_source_image_url(self, obj):
        request = self.context.get("request") if hasattr(self, "context") else None
        if obj.source_image and getattr(obj.source_image, "name", ""):
            try:
                if obj.source_image.storage.exists(obj.source_image.name):
                    url = obj.source_image.url
                    if request and hasattr(request, "build_absolute_uri"):
                        return request.build_absolute_uri(url)
                    return url
            except Exception:
                return ""
        return ""


class BuddyGeneratedAvatarCreateSerializer(serializers.Serializer):
    source_image = serializers.ImageField(required=True)
    consent_confirmed = serializers.BooleanField(required=True)
    provider = serializers.CharField(required=False, allow_blank=True)
    preferred_gender_style = serializers.CharField(required=False, allow_blank=True)
    preferred_age_style = serializers.CharField(required=False, allow_blank=True)
    preferred_hair_style = serializers.CharField(required=False, allow_blank=True)
    preferred_outfit_style = serializers.CharField(required=False, allow_blank=True)
    realism_level = serializers.ChoiceField(
        choices=("stylized", "balanced", "realistic"),
        required=False,
        default="balanced",
    )

    def validate(self, attrs):
        if not attrs.get("consent_confirmed"):
            raise serializers.ValidationError({"consent_confirmed": "Consent is required."})
        image = attrs["source_image"]
        max_bytes = getattr(settings, "SPEAKING_BUDDY_MAX_AVATAR_BYTES", 5 * 1024 * 1024)
        if getattr(image, "size", 0) > max_bytes:
            raise serializers.ValidationError({"source_image": "Avatar image is too large."})
        content_type = getattr(image, "content_type", "")
        if content_type and content_type not in {"image/jpeg", "image/png", "image/webp"}:
            raise serializers.ValidationError({"source_image": "Use a PNG, JPG, or WebP image."})
        return attrs


class BuddyGeneratedAvatarRegenerateSerializer(serializers.Serializer):
    preferred_gender_style = serializers.CharField(required=False, allow_blank=True)
    preferred_age_style = serializers.CharField(required=False, allow_blank=True)
    preferred_hair_style = serializers.CharField(required=False, allow_blank=True)
    preferred_outfit_style = serializers.CharField(required=False, allow_blank=True)
    realism_level = serializers.ChoiceField(
        choices=("stylized", "balanced", "realistic"),
        required=False,
        default="balanced",
    )


class Buddy3DAvatarSelectSerializer(serializers.Serializer):
    avatar_3d_slug = serializers.SlugField(required=False, allow_blank=True)
    generated_avatar_id = serializers.IntegerField(required=False)
    avatar_render_mode = serializers.ChoiceField(
        choices=(
            ("2d", "2D"),
            ("3d", "3D"),
            ("generated_3d", "Generated 3D"),
        ),
        required=False,
    )


class BuddySessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = BuddySession
        fields = (
            "id",
            "language",
            "topic",
            "status",
            "selected_voice",
            "duration_seconds",
            "transcript",
            "ai_summary",
            "user_summary",
            "mistakes_detected",
            "vocabulary_practiced",
            "improvement_notes",
            "selected_avatar",
            "emotion_timeline",
            "usage_counted",
            "end_reason",
            "client_closed_at",
            "started_at",
            "ended_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "status",
            "selected_voice",
            "duration_seconds",
            "transcript",
            "ai_summary",
            "user_summary",
            "mistakes_detected",
            "vocabulary_practiced",
            "improvement_notes",
            "selected_avatar",
            "emotion_timeline",
            "usage_counted",
            "end_reason",
            "client_closed_at",
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
        read_only_fields = ("id", "profile", "created_at", "updated_at")


class BuddyMistakeSerializer(serializers.ModelSerializer):
    class Meta:
        model = BuddyMistake
        fields = "__all__"
        read_only_fields = ("id", "profile", "created_at", "updated_at")


class BuddySessionStartSerializer(serializers.Serializer):
    language = serializers.ChoiceField(choices=BuddyProfile._meta.get_field("native_language").choices, required=False)
    topic = serializers.CharField(required=False, allow_blank=True)


class BuddySessionMessageSerializer(serializers.Serializer):
    session_id = serializers.IntegerField()
    text = serializers.CharField()


class BuddySessionEndSerializer(serializers.Serializer):
    session_id = serializers.IntegerField()
    reason = serializers.CharField(required=False, allow_blank=True)
    client_closed_at = serializers.DateTimeField(required=False)


class BuddyRealtimeTokenSerializer(serializers.Serializer):
    session_id = serializers.IntegerField(required=False)


class BuddyMemoryUpdateSerializer(serializers.Serializer):
    memory_id = serializers.IntegerField()
    value = serializers.JSONField(required=False)
    importance = serializers.IntegerField(required=False, min_value=1, max_value=5)
    is_active = serializers.BooleanField(required=False)
