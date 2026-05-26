from rest_framework import serializers
from .models import InsuranceSession, InsuranceMessage


class InsuranceMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = InsuranceMessage
        fields = ["id", "role", "content", "created_at"]


class InsuranceSessionSerializer(serializers.ModelSerializer):
    messages = InsuranceMessageSerializer(many=True, read_only=True)

    class Meta:
        model = InsuranceSession
        fields = [
            "id",
            "country",
            "language",
            "insurance_type",
            "provider_url",
            "filename",
            "analysis",
            "raw_summary",
            "status",
            "error_message",
            "created_at",
            "updated_at",
            "messages",
        ]
        read_only_fields = ["id", "analysis", "raw_summary", "status", "error_message", "created_at", "updated_at"]


class InsuranceSessionListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list view — no messages or analysis."""

    class Meta:
        model = InsuranceSession
        fields = [
            "id",
            "country",
            "language",
            "insurance_type",
            "filename",
            "status",
            "created_at",
        ]


class ExplainRequestSerializer(serializers.Serializer):
    """Input for creating a new insurance analysis."""
    country = serializers.CharField(max_length=100, default="International")
    language = serializers.CharField(max_length=50, default="English")
    provider_url = serializers.URLField(required=False, allow_blank=True, default="")
    policy_text = serializers.CharField(required=False, allow_blank=True, default="")
    file = serializers.FileField(required=False)

    def validate(self, data):
        if not data.get("policy_text") and not data.get("file"):
            raise serializers.ValidationError("Provide either policy_text or a file.")
        if data.get("policy_text") and len(data["policy_text"]) < 50:
            raise serializers.ValidationError("policy_text is too short. Paste at least 50 characters.")
        return data


class InsuranceChatRequestSerializer(serializers.Serializer):
    message = serializers.CharField(min_length=1, max_length=2000)
