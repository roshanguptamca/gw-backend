from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.templates_app.models import ResumeTemplate
from apps.templates_app.serializers import ResumeTemplateSerializer

from .models import (
    Award,
    Certification,
    Education,
    PersonalDetail,
    Project,
    Reference,
    Resume,
    ResumeLanguage,
    ResumeSummary,
    ResumeUpload,
    Skill,
    WorkExperience,
    normalize_resume_value,
)
from .limits import usage_for_request


class PersonalDetailSerializer(serializers.ModelSerializer):
    photo_url = serializers.SerializerMethodField()
    has_photo = serializers.SerializerMethodField()

    class Meta:
        model = PersonalDetail
        exclude = ["resume", "profile_photo"]

    @extend_schema_field(serializers.URLField(allow_null=True))
    def get_photo_url(self, obj):
        if not obj.profile_photo_id:
            return None
        request = self.context.get("request")
        path = f"/api/resumes/{obj.resume_id}/photo/"
        return request.build_absolute_uri(path) if request else path

    @extend_schema_field(serializers.BooleanField())
    def get_has_photo(self, obj):
        return bool(obj.profile_photo_id)


class ResumeSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = ResumeSummary
        exclude = ["resume"]


def section_serializer(model):
    meta = type(
        "Meta",
        (),
        {
            "model": model,
            "exclude": ["resume"],
            "read_only_fields": ["created_at", "updated_at"],
        },
    )
    return type(f"{model.__name__}Serializer", (serializers.ModelSerializer,), {"Meta": meta})


class WorkExperienceSerializer(serializers.ModelSerializer):
    company = serializers.CharField(source="employer", required=False, write_only=True)

    class Meta:
        model = WorkExperience
        exclude = ["resume", "duplicate_key"]
        read_only_fields = ["created_at", "updated_at"]
        extra_kwargs = {
            "employer": {"required": False},
            "job_title": {"required": True, "allow_blank": False},
            "start_date": {"required": True, "allow_null": False},
        }

    def validate(self, attrs):
        if not attrs.get("employer"):
            raise serializers.ValidationError({"company": "Company is required."})
        resume = self.context.get("resume") or getattr(self.instance, "resume", None)
        employer = attrs.get("employer", getattr(self.instance, "employer", ""))
        job_title = attrs.get("job_title", getattr(self.instance, "job_title", ""))
        start_date = attrs.get("start_date", getattr(self.instance, "start_date", None))
        duplicate_key = "|".join(
            [normalize_resume_value(employer), normalize_resume_value(job_title), str(start_date or "")]
        )
        if resume:
            duplicates = WorkExperience.objects.filter(resume=resume, duplicate_key=duplicate_key)
            if self.instance:
                duplicates = duplicates.exclude(pk=self.instance.pk)
            if duplicates.exists():
                raise serializers.ValidationError({"non_field_errors": ["This experience entry already exists."]})
        return attrs


class EducationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Education
        exclude = ["resume", "duplicate_key"]
        read_only_fields = ["created_at", "updated_at"]
        extra_kwargs = {
            "institution": {"required": True, "allow_blank": False},
            "degree": {"required": True, "allow_blank": False},
        }

    def validate(self, attrs):
        resume = self.context.get("resume") or getattr(self.instance, "resume", None)
        values = [
            attrs.get("institution", getattr(self.instance, "institution", "")),
            attrs.get("degree", getattr(self.instance, "degree", "")),
            attrs.get("field_of_study", getattr(self.instance, "field_of_study", "")),
        ]
        start_date = attrs.get("start_date", getattr(self.instance, "start_date", None))
        duplicate_key = "|".join([*(normalize_resume_value(value) for value in values), str(start_date or "")])
        if resume:
            duplicates = Education.objects.filter(resume=resume, duplicate_key=duplicate_key)
            if self.instance:
                duplicates = duplicates.exclude(pk=self.instance.pk)
            if duplicates.exists():
                raise serializers.ValidationError({"non_field_errors": ["This education entry already exists."]})
        return attrs


class ProjectSerializer(serializers.ModelSerializer):
    project_name = serializers.CharField(source="name", required=False, write_only=True)

    class Meta:
        model = Project
        exclude = ["resume", "duplicate_key"]
        read_only_fields = ["created_at", "updated_at"]
        extra_kwargs = {"name": {"required": False}, "description": {"required": True, "allow_blank": False}}

    def validate(self, attrs):
        if not attrs.get("name"):
            raise serializers.ValidationError({"project_name": "Project name is required."})
        resume = self.context.get("resume") or getattr(self.instance, "resume", None)
        name = attrs.get("name", getattr(self.instance, "name", ""))
        role = attrs.get("role", getattr(self.instance, "role", ""))
        duplicate_key = "|".join([normalize_resume_value(name), normalize_resume_value(role)])
        if resume:
            duplicates = Project.objects.filter(resume=resume, duplicate_key=duplicate_key)
            if self.instance:
                duplicates = duplicates.exclude(pk=self.instance.pk)
            if duplicates.exists():
                raise serializers.ValidationError({"non_field_errors": ["This project is already added."]})
        return attrs


class SkillSerializer(serializers.ModelSerializer):
    skill_name = serializers.CharField(source="name", required=False, write_only=True)

    class Meta:
        model = Skill
        exclude = ["resume", "normalized_name"]
        read_only_fields = ["created_at", "updated_at"]
        extra_kwargs = {"name": {"required": False}, "category": {"required": True, "allow_blank": False}}

    def validate(self, attrs):
        if not attrs.get("name"):
            raise serializers.ValidationError({"skill_name": "Skill name is required."})
        resume = self.context.get("resume") or getattr(self.instance, "resume", None)
        normalized_name = normalize_resume_value(attrs.get("name", getattr(self.instance, "name", "")))
        if resume:
            duplicates = Skill.objects.filter(resume=resume, normalized_name=normalized_name)
            if self.instance:
                duplicates = duplicates.exclude(pk=self.instance.pk)
            if duplicates.exists():
                raise serializers.ValidationError({"skill_name": ["This skill is already added."]})
        return attrs


class CertificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Certification
        exclude = ["resume"]
        read_only_fields = ["created_at", "updated_at"]
        extra_kwargs = {"name": {"required": True, "allow_blank": False}}


class ResumeLanguageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ResumeLanguage
        exclude = ["resume"]
        read_only_fields = ["created_at", "updated_at"]
        extra_kwargs = {
            "name": {"required": True, "allow_blank": False},
            "proficiency": {"required": True, "allow_blank": False},
        }


class AwardSerializer(serializers.ModelSerializer):
    class Meta:
        model = Award
        exclude = ["resume"]
        read_only_fields = ["created_at", "updated_at"]
        extra_kwargs = {"title": {"required": True, "allow_blank": False}}


class ReferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Reference
        exclude = ["resume"]
        read_only_fields = ["created_at", "updated_at"]
        extra_kwargs = {"name": {"required": True, "allow_blank": False}}


class ResumeSerializer(serializers.ModelSerializer):
    personal = serializers.SerializerMethodField()
    summary = serializers.SerializerMethodField()
    experiences = serializers.SerializerMethodField()
    education = serializers.SerializerMethodField()
    projects = serializers.SerializerMethodField()
    skills = serializers.SerializerMethodField()
    certifications = serializers.SerializerMethodField()
    languages = serializers.SerializerMethodField()
    awards = serializers.SerializerMethodField()
    references = serializers.SerializerMethodField()
    template_supports_photo = serializers.SerializerMethodField()
    selected_template = ResumeTemplateSerializer(source="template", read_only=True)
    template = serializers.PrimaryKeyRelatedField(
        queryset=ResumeTemplate.objects.filter(is_active=True), allow_null=True, required=False
    )
    owner_email = serializers.EmailField(write_only=True, required=False, allow_blank=True)
    owner_phone = serializers.CharField(write_only=True, required=False, allow_blank=True)
    usage = serializers.SerializerMethodField()

    class Meta:
        model = Resume
        fields = [
            "id",
            "title",
            "locale",
            "template",
            "selected_template",
            "template_settings",
            "include_photo",
            "is_archived",
            "edit_count",
            "max_edit_count",
            "source",
            "is_claimed",
            "owner_email",
            "owner_phone",
            "usage",
            "personal",
            "summary",
            "experiences",
            "education",
            "projects",
            "skills",
            "certifications",
            "languages",
            "awards",
            "references",
            "template_supports_photo",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "created_at",
            "updated_at",
            "edit_count",
            "max_edit_count",
            "source",
            "is_claimed",
        ]

    def create(self, validated_data):
        validated_data.pop("owner_email", None)
        validated_data.pop("owner_phone", None)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        validated_data.pop("owner_email", None)
        validated_data.pop("owner_phone", None)
        return super().update(instance, validated_data)

    @extend_schema_field(serializers.DictField())
    def get_usage(self, obj):
        request = self.context.get("request")
        return usage_for_request(request, obj) if request else {}

    @extend_schema_field(serializers.CharField())
    def get_summary(self, obj):
        return obj.summary.text if hasattr(obj, "summary") else ""

    @extend_schema_field(PersonalDetailSerializer())
    def get_personal(self, obj):
        if not hasattr(obj, "personal"):
            return None
        return PersonalDetailSerializer(obj.personal, context=self.context).data

    @extend_schema_field(WorkExperienceSerializer(many=True))
    def get_experiences(self, obj):
        return WorkExperienceSerializer(WorkExperience.objects.filter(resume=obj), many=True).data

    @extend_schema_field(EducationSerializer(many=True))
    def get_education(self, obj):
        return EducationSerializer(Education.objects.filter(resume=obj), many=True).data

    @extend_schema_field(ProjectSerializer(many=True))
    def get_projects(self, obj):
        return ProjectSerializer(Project.objects.filter(resume=obj), many=True).data

    @extend_schema_field(SkillSerializer(many=True))
    def get_skills(self, obj):
        return SkillSerializer(Skill.objects.filter(resume=obj), many=True).data

    @extend_schema_field(CertificationSerializer(many=True))
    def get_certifications(self, obj):
        return CertificationSerializer(Certification.objects.filter(resume=obj), many=True).data

    @extend_schema_field(ResumeLanguageSerializer(many=True))
    def get_languages(self, obj):
        return ResumeLanguageSerializer(ResumeLanguage.objects.filter(resume=obj), many=True).data

    @extend_schema_field(AwardSerializer(many=True))
    def get_awards(self, obj):
        return AwardSerializer(Award.objects.filter(resume=obj), many=True).data

    @extend_schema_field(ReferenceSerializer(many=True))
    def get_references(self, obj):
        return ReferenceSerializer(Reference.objects.filter(resume=obj), many=True).data

    @extend_schema_field(serializers.BooleanField())
    def get_template_supports_photo(self, obj):
        return bool(obj.template and obj.template.supports_photo)


class ResumeUploadSerializer(serializers.ModelSerializer):
    class Meta:
        model = ResumeUpload
        exclude = ["file_data"]
        read_only_fields = [
            "id",
            "user",
            "filename",
            "content_type",
            "file_size",
            "status",
            "extracted_text",
            "parsed_json",
            "error_message",
            "created_at",
            "updated_at",
        ]


class AutoFillResumeRequestSerializer(serializers.Serializer):
    job_description_text = serializers.CharField(required=False, allow_blank=True, default="")
    job_description_url = serializers.URLField(required=False, allow_blank=True, default="")
    job_description_id = serializers.IntegerField(required=False, allow_null=True)
    resume_id = serializers.IntegerField(required=False, allow_null=True)
    uploaded_resume_id = serializers.UUIDField(required=False, allow_null=True)
    target_language = serializers.ChoiceField(choices=["en", "nl"], default="en")
    target_match_score = serializers.IntegerField(min_value=50, max_value=100, default=90)
    owner_email = serializers.EmailField(required=False, allow_blank=True)
    owner_phone = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        if (
            not attrs["job_description_text"].strip()
            and not attrs["job_description_url"].strip()
            and not attrs.get("job_description_id")
        ):
            raise serializers.ValidationError(
                {
                    "job_description_text": (
                        "Provide job description text, a job description URL, or a parsed job description ID."
                    )
                }
            )
        if attrs.get("resume_id") and attrs.get("uploaded_resume_id"):
            raise serializers.ValidationError(
                {"resume_id": "Choose either an existing resume or an uploaded resume, not both."}
            )
        return attrs


class GenerateSummaryRequestSerializer(serializers.Serializer):
    job_title = serializers.CharField(max_length=180)
    language = serializers.ChoiceField(choices=["en", "nl"], required=False)
