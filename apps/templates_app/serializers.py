import re

from rest_framework import serializers

from .models import ResumeTemplate

SECTION_KEYS = [
    "summary",
    "experience",
    "education",
    "skills",
    "projects",
    "certifications",
    "languages",
    "awards",
    "references",
]


class ResumeTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ResumeTemplate
        fields = [
            "id",
            "name",
            "slug",
            "category",
            "description",
            "preview_image",
            "preview_url",
            "supports_photo",
            "is_ats_friendly",
            "is_premium",
            "layout_type",
            "supported_formats",
            "default_settings",
            "is_active",
            "sort_order",
            "created_at",
            "updated_at",
        ]


class TemplateSettingsSerializer(serializers.Serializer):
    primary_color = serializers.CharField(required=False)
    font_family = serializers.CharField(required=False, max_length=80)
    font_size = serializers.ChoiceField(choices=["small", "medium", "large"], required=False)
    spacing = serializers.ChoiceField(choices=["compact", "normal", "relaxed"], required=False)
    include_photo = serializers.BooleanField(required=False)
    section_order = serializers.ListField(
        child=serializers.ChoiceField(choices=SECTION_KEYS),
        required=False,
        allow_empty=False,
    )

    def validate_primary_color(self, value):
        if not re.fullmatch(r"#[0-9A-Fa-f]{6}", value):
            raise serializers.ValidationError("Use a valid six-digit hex color.")
        return value.upper()

    def validate_section_order(self, value):
        if len(value) != len(set(value)):
            raise serializers.ValidationError("Section order cannot contain duplicates.")
        return value


class SelectTemplateSerializer(serializers.Serializer):
    template_id = serializers.PrimaryKeyRelatedField(
        source="template",
        queryset=ResumeTemplate.objects.filter(is_active=True),
    )
    template_settings = TemplateSettingsSerializer(required=False, default=dict)

    def validate(self, attrs):
        template = attrs.get("template")
        settings = attrs.get("template_settings", {})
        if template and settings.get("include_photo") and not template.supports_photo:
            raise serializers.ValidationError(
                {"template_settings": {"include_photo": "This template does not support photos."}}
            )
        return attrs


class PreviewTemplateSerializer(SelectTemplateSerializer):
    template_id = serializers.PrimaryKeyRelatedField(
        source="template",
        queryset=ResumeTemplate.objects.filter(is_active=True),
        required=False,
    )
