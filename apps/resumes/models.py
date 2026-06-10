import re
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone


def normalize_resume_value(value):
    return re.sub(r"\s+", " ", (value or "").strip()).casefold()


class OwnedModel(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class ExpiringModel(models.Model):
    expires_at = models.DateTimeField(db_index=True)

    class Meta:
        abstract = True

    @property
    def is_expired(self):
        return self.expires_at <= timezone.now()


class Resume(OwnedModel):
    LANGUAGE_CHOICES = [("en", "English"), ("nl", "Dutch")]
    SOURCE_CHOICES = [("anonymous", "Anonymous"), ("registered", "Registered")]
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="resume_set",
    )
    anonymous_identity = models.ForeignKey(
        "AnonymousResumeIdentity",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="resumes",
    )
    title = models.CharField(max_length=255, default="Untitled Resume")
    locale = models.CharField(max_length=10, choices=LANGUAGE_CHOICES, default="en")
    template = models.ForeignKey(
        "templates_app.ResumeTemplate", null=True, blank=True, on_delete=models.SET_NULL, related_name="resumes"
    )
    template_settings = models.JSONField(default=dict, blank=True)
    include_photo = models.BooleanField(default=True)
    is_archived = models.BooleanField(default=False)
    edit_count = models.PositiveIntegerField(default=0)
    max_edit_count = models.PositiveIntegerField(default=10)
    is_claimed = models.BooleanField(default=False)
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default="registered")

    class Meta:
        ordering = ["-updated_at"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(user__isnull=False, anonymous_identity__isnull=True)
                    | Q(user__isnull=True, anonymous_identity__isnull=False)
                ),
                name="resume_has_exactly_one_owner",
            )
        ]

    def clean(self):
        if bool(self.user_id) == bool(self.anonymous_identity_id):
            raise ValidationError("A resume must have exactly one owner.")


class AnonymousResumeIdentity(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ip_address = models.GenericIPAddressField(null=True, blank=True, db_index=True)
    email = models.EmailField(null=True, blank=True, db_index=True)
    phone_number = models.CharField(max_length=40, null=True, blank=True, db_index=True)
    session_key = models.CharField(max_length=64, null=True, blank=True, db_index=True)
    fingerprint_hash = models.CharField(max_length=64, null=True, blank=True, db_index=True)
    user_agent_hash = models.CharField(max_length=64, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_seen_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["created_at"]


class ResumeVersion(models.Model):
    resume = models.ForeignKey(Resume, on_delete=models.CASCADE, related_name="versions")
    version_number = models.PositiveIntegerField()
    snapshot = models.JSONField(default=dict)
    source = models.CharField(max_length=30, default="manual")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("resume", "version_number")
        ordering = ["-version_number"]


class PersonalDetail(models.Model):
    resume = models.OneToOneField(Resume, on_delete=models.CASCADE, related_name="personal")
    profile_photo = models.ForeignKey(
        "files.UserFile",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="resume_profiles",
    )
    include_photo = models.BooleanField(default=True)
    first_name = models.CharField(max_length=120, blank=True)
    last_name = models.CharField(max_length=120, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=60, blank=True)
    city = models.CharField(max_length=120, blank=True)
    country = models.CharField(max_length=120, blank=True)
    professional_title = models.CharField(max_length=180, blank=True)
    address = models.CharField(max_length=255, blank=True)
    postal_code = models.CharField(max_length=30, blank=True)
    linkedin_url = models.URLField(blank=True)
    portfolio_url = models.URLField(blank=True)


class ResumeSummary(models.Model):
    resume = models.OneToOneField(Resume, on_delete=models.CASCADE, related_name="summary")
    text = models.TextField(blank=True)


class OrderedResumeItem(models.Model):
    resume = models.ForeignKey(Resume, on_delete=models.CASCADE)
    position = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ["position", "created_at"]


class WorkExperience(OrderedResumeItem):
    employer = models.CharField(max_length=180)
    job_title = models.CharField(max_length=180)
    duplicate_key = models.CharField(max_length=500, blank=True, editable=False)
    city = models.CharField(max_length=120, blank=True)
    country = models.CharField(max_length=120, blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    current = models.BooleanField(default=False)
    description = models.TextField(blank=True)
    achievements = models.JSONField(default=list, blank=True)

    class Meta(OrderedResumeItem.Meta):
        constraints = [models.UniqueConstraint(fields=["resume", "duplicate_key"], name="unique_resume_experience")]

    def save(self, *args, **kwargs):
        self.duplicate_key = "|".join(
            [normalize_resume_value(self.employer), normalize_resume_value(self.job_title), str(self.start_date or "")]
        )
        if kwargs.get("update_fields") is not None:
            kwargs["update_fields"] = set(kwargs["update_fields"]) | {"duplicate_key"}
        super().save(*args, **kwargs)


class Education(OrderedResumeItem):
    institution = models.CharField(max_length=180)
    degree = models.CharField(max_length=180, blank=True)
    field_of_study = models.CharField(max_length=180, blank=True)
    duplicate_key = models.CharField(max_length=700, blank=True, editable=False)
    city = models.CharField(max_length=120, blank=True)
    country = models.CharField(max_length=120, blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    description = models.TextField(blank=True)

    class Meta(OrderedResumeItem.Meta):
        constraints = [models.UniqueConstraint(fields=["resume", "duplicate_key"], name="unique_resume_education")]

    def save(self, *args, **kwargs):
        self.duplicate_key = "|".join(
            [
                normalize_resume_value(self.institution),
                normalize_resume_value(self.degree),
                normalize_resume_value(self.field_of_study),
                str(self.start_date or ""),
            ]
        )
        if kwargs.get("update_fields") is not None:
            kwargs["update_fields"] = set(kwargs["update_fields"]) | {"duplicate_key"}
        super().save(*args, **kwargs)


class Project(OrderedResumeItem):
    name = models.CharField(max_length=180)
    role = models.CharField(max_length=180, blank=True)
    duplicate_key = models.CharField(max_length=400, blank=True, editable=False)
    url = models.URLField(blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    description = models.TextField(blank=True)
    technologies = models.JSONField(default=list, blank=True)

    class Meta(OrderedResumeItem.Meta):
        constraints = [models.UniqueConstraint(fields=["resume", "duplicate_key"], name="unique_resume_project")]

    def save(self, *args, **kwargs):
        self.duplicate_key = "|".join([normalize_resume_value(self.name), normalize_resume_value(self.role)])
        if kwargs.get("update_fields") is not None:
            kwargs["update_fields"] = set(kwargs["update_fields"]) | {"duplicate_key"}
        super().save(*args, **kwargs)


class Skill(OrderedResumeItem):
    name = models.CharField(max_length=120)
    normalized_name = models.CharField(max_length=120, blank=True, editable=False)
    level = models.CharField(max_length=50, blank=True)
    category = models.CharField(max_length=120, blank=True)

    class Meta(OrderedResumeItem.Meta):
        constraints = [models.UniqueConstraint(fields=["resume", "normalized_name"], name="unique_resume_skill")]

    def save(self, *args, **kwargs):
        self.normalized_name = normalize_resume_value(self.name)
        if kwargs.get("update_fields") is not None:
            kwargs["update_fields"] = set(kwargs["update_fields"]) | {"normalized_name"}
        super().save(*args, **kwargs)


class Certification(OrderedResumeItem):
    name = models.CharField(max_length=180)
    issuer = models.CharField(max_length=180, blank=True)
    issued_at = models.DateField(null=True, blank=True)
    expires_at = models.DateField(null=True, blank=True)
    credential_id = models.CharField(max_length=180, blank=True)
    credential_url = models.URLField(blank=True)


class ResumeLanguage(OrderedResumeItem):
    name = models.CharField(max_length=120)
    proficiency = models.CharField(max_length=60, blank=True)


class Award(OrderedResumeItem):
    title = models.CharField(max_length=180)
    issuer = models.CharField(max_length=180, blank=True)
    awarded_at = models.DateField(null=True, blank=True)
    description = models.TextField(blank=True)


class Reference(OrderedResumeItem):
    name = models.CharField(max_length=180)
    company = models.CharField(max_length=180, blank=True)
    job_title = models.CharField(max_length=180, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=60, blank=True)


class ResumeUpload(OwnedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE, related_name="resumeupload_set"
    )
    anonymous_identity = models.ForeignKey(
        AnonymousResumeIdentity, null=True, blank=True, on_delete=models.CASCADE, related_name="uploads"
    )
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=120, blank=True)
    file_size = models.PositiveIntegerField()
    file_data = models.BinaryField(editable=False)
    status = models.CharField(max_length=20, default="uploaded")
    extracted_text = models.TextField(blank=True)
    parsed_json = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True)


class TemporaryResumeUpload(OwnedModel, ExpiringModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="temporaryresumeupload_set",
    )
    anonymous_identity = models.ForeignKey(AnonymousResumeIdentity, null=True, blank=True, on_delete=models.CASCADE)
    upload = models.ForeignKey(ResumeUpload, on_delete=models.CASCADE, related_name="temporary_records")
    extracted_text = models.TextField(blank=True)
    parsed_json = models.JSONField(default=dict, blank=True)
    match_results = models.JSONField(default=dict, blank=True)


class TemporaryGeneratedResume(OwnedModel, ExpiringModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="temporarygeneratedresume_set",
    )
    anonymous_identity = models.ForeignKey(AnonymousResumeIdentity, null=True, blank=True, on_delete=models.CASCADE)
    source_resume = models.ForeignKey(Resume, null=True, blank=True, on_delete=models.CASCADE)
    generated_json = models.JSONField(default=dict)
    match_results = models.JSONField(default=dict, blank=True)


class OptimizedResume(OwnedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE, related_name="optimizedresume_set"
    )
    anonymous_identity = models.ForeignKey(AnonymousResumeIdentity, null=True, blank=True, on_delete=models.CASCADE)
    source_resume = models.ForeignKey(Resume, on_delete=models.CASCADE, related_name="optimizations")
    optimized_resume = models.ForeignKey(
        Resume, null=True, blank=True, on_delete=models.SET_NULL, related_name="optimized_copies"
    )
    job_match = models.ForeignKey("jobs.JobMatch", null=True, blank=True, on_delete=models.SET_NULL)
    optimized_json = models.JSONField(default=dict)
    suggestions = models.JSONField(default=list, blank=True)
    confirmation_required_skills = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=30, default="completed")
    output_language = models.CharField(max_length=10, choices=Resume.LANGUAGE_CHOICES, default="en")
