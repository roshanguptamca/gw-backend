from django.contrib import admin

from .models import (
    AnonymousResumeIdentity,
    Award,
    Certification,
    Education,
    OptimizedResume,
    PersonalDetail,
    Project,
    Reference,
    Resume,
    ResumeLanguage,
    ResumeSummary,
    ResumeUpload,
    ResumeVersion,
    Skill,
    TemporaryGeneratedResume,
    TemporaryResumeUpload,
    WorkExperience,
)


class ResumeRelatedAdmin(admin.ModelAdmin):
    raw_id_fields = ("resume",)
    ordering = ("resume", "position")


@admin.register(Resume)
class ResumeAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "owner",
        "locale",
        "template",
        "source",
        "is_archived",
        "is_claimed",
        "edit_count",
        "updated_at",
    )
    list_filter = ("locale", "source", "is_archived", "is_claimed", "include_photo", "created_at")
    search_fields = ("title", "user__username", "user__email", "anonymous_identity__email")
    readonly_fields = ("created_at", "updated_at")
    raw_id_fields = ("user", "anonymous_identity", "template")
    ordering = ("-updated_at",)

    @admin.display(description="Owner")
    def owner(self, obj):
        return obj.user or obj.anonymous_identity


@admin.register(AnonymousResumeIdentity)
class AnonymousResumeIdentityAdmin(admin.ModelAdmin):
    list_display = ("id", "email", "phone_number", "ip_address", "session_key", "last_seen_at", "created_at")
    list_filter = ("created_at", "last_seen_at")
    search_fields = ("=id", "email", "phone_number", "ip_address", "session_key", "fingerprint_hash")
    readonly_fields = ("id", "created_at", "updated_at")
    ordering = ("-last_seen_at",)


@admin.register(ResumeVersion)
class ResumeVersionAdmin(admin.ModelAdmin):
    list_display = ("resume", "version_number", "source", "created_at")
    list_filter = ("source", "created_at")
    search_fields = ("resume__title",)
    readonly_fields = ("created_at",)
    raw_id_fields = ("resume",)
    ordering = ("resume", "-version_number")


@admin.register(PersonalDetail)
class PersonalDetailAdmin(admin.ModelAdmin):
    list_display = ("resume", "first_name", "last_name", "email", "professional_title", "include_photo")
    search_fields = ("resume__title", "first_name", "last_name", "email", "professional_title")
    raw_id_fields = ("resume", "profile_photo")


@admin.register(ResumeSummary)
class ResumeSummaryAdmin(admin.ModelAdmin):
    list_display = ("resume", "summary_preview")
    search_fields = ("resume__title", "text")
    raw_id_fields = ("resume",)

    @admin.display(description="Summary")
    def summary_preview(self, obj):
        return obj.text[:100]


@admin.register(WorkExperience)
class WorkExperienceAdmin(ResumeRelatedAdmin):
    list_display = ("employer", "job_title", "resume", "start_date", "end_date", "current", "position")
    list_filter = ("current",)
    search_fields = ("employer", "job_title", "resume__title")
    readonly_fields = ("duplicate_key", "created_at", "updated_at")


@admin.register(Education)
class EducationAdmin(ResumeRelatedAdmin):
    list_display = ("institution", "degree", "field_of_study", "resume", "start_date", "end_date", "position")
    search_fields = ("institution", "degree", "field_of_study", "resume__title")
    readonly_fields = ("duplicate_key", "created_at", "updated_at")


@admin.register(Project)
class ProjectAdmin(ResumeRelatedAdmin):
    list_display = ("name", "role", "resume", "start_date", "end_date", "position")
    search_fields = ("name", "role", "resume__title")
    readonly_fields = ("duplicate_key", "created_at", "updated_at")


@admin.register(Skill)
class SkillAdmin(ResumeRelatedAdmin):
    list_display = ("name", "level", "category", "resume", "position")
    list_filter = ("category", "level")
    search_fields = ("name", "category", "resume__title")
    readonly_fields = ("normalized_name", "created_at", "updated_at")


@admin.register(Certification)
class CertificationAdmin(ResumeRelatedAdmin):
    list_display = ("name", "issuer", "resume", "issued_at", "expires_at", "position")
    search_fields = ("name", "issuer", "resume__title")
    readonly_fields = ("created_at", "updated_at")


@admin.register(ResumeLanguage)
class ResumeLanguageAdmin(ResumeRelatedAdmin):
    list_display = ("name", "proficiency", "resume", "position")
    search_fields = ("name", "proficiency", "resume__title")
    readonly_fields = ("created_at", "updated_at")


@admin.register(Award)
class AwardAdmin(ResumeRelatedAdmin):
    list_display = ("title", "issuer", "resume", "awarded_at", "position")
    search_fields = ("title", "issuer", "resume__title")
    readonly_fields = ("created_at", "updated_at")


@admin.register(Reference)
class ReferenceAdmin(ResumeRelatedAdmin):
    list_display = ("name", "company", "job_title", "email", "resume", "position")
    search_fields = ("name", "company", "job_title", "email", "resume__title")
    readonly_fields = ("created_at", "updated_at")


@admin.register(ResumeUpload)
class ResumeUploadAdmin(admin.ModelAdmin):
    list_display = ("filename", "owner", "content_type", "file_size", "status", "created_at")
    list_filter = ("status", "content_type", "created_at")
    search_fields = ("filename", "user__username", "user__email", "anonymous_identity__email")
    readonly_fields = ("id", "created_at", "updated_at")
    raw_id_fields = ("user", "anonymous_identity")
    ordering = ("-created_at",)

    @admin.display(description="Owner")
    def owner(self, obj):
        return obj.user or obj.anonymous_identity


@admin.register(TemporaryResumeUpload)
class TemporaryResumeUploadAdmin(admin.ModelAdmin):
    list_display = ("id", "upload", "owner", "expires_at", "created_at")
    list_filter = ("expires_at", "created_at")
    search_fields = ("upload__filename", "user__username", "user__email")
    readonly_fields = ("created_at", "updated_at")
    raw_id_fields = ("user", "anonymous_identity", "upload")
    ordering = ("-created_at",)

    @admin.display(description="Owner")
    def owner(self, obj):
        return obj.user or obj.anonymous_identity


@admin.register(TemporaryGeneratedResume)
class TemporaryGeneratedResumeAdmin(admin.ModelAdmin):
    list_display = ("id", "source_resume", "owner", "expires_at", "created_at")
    list_filter = ("expires_at", "created_at")
    search_fields = ("source_resume__title", "user__username", "user__email")
    readonly_fields = ("created_at", "updated_at")
    raw_id_fields = ("user", "anonymous_identity", "source_resume")
    ordering = ("-created_at",)

    @admin.display(description="Owner")
    def owner(self, obj):
        return obj.user or obj.anonymous_identity


@admin.register(OptimizedResume)
class OptimizedResumeAdmin(admin.ModelAdmin):
    list_display = ("id", "source_resume", "optimized_resume", "status", "output_language", "owner", "created_at")
    list_filter = ("status", "output_language", "created_at")
    search_fields = ("source_resume__title", "optimized_resume__title", "user__username", "user__email")
    readonly_fields = ("created_at", "updated_at")
    raw_id_fields = ("user", "anonymous_identity", "source_resume", "optimized_resume", "job_match")
    ordering = ("-created_at",)

    @admin.display(description="Owner")
    def owner(self, obj):
        return obj.user or obj.anonymous_identity
