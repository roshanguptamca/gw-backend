from django.contrib import admin

from .models import ATSReport, JobDescription, JobMatch, TemporaryJobDescription


@admin.register(JobDescription)
class JobDescriptionAdmin(admin.ModelAdmin):
    list_display = ("title", "company", "language", "owner", "created_at")
    list_filter = ("language", "created_at")
    search_fields = ("title", "company", "raw_text", "source_url", "user__username", "user__email")
    readonly_fields = ("created_at",)
    raw_id_fields = ("user", "anonymous_identity")
    ordering = ("-created_at",)

    @admin.display(description="Owner")
    def owner(self, obj):
        return obj.user or obj.anonymous_identity


@admin.register(TemporaryJobDescription)
class TemporaryJobDescriptionAdmin(admin.ModelAdmin):
    list_display = ("id", "owner", "source_url", "expires_at", "created_at")
    list_filter = ("expires_at", "created_at")
    search_fields = ("raw_text", "source_url", "user__username", "user__email")
    readonly_fields = ("created_at",)
    raw_id_fields = ("user", "anonymous_identity")
    ordering = ("-created_at",)

    @admin.display(description="Owner")
    def owner(self, obj):
        return obj.user or obj.anonymous_identity


@admin.register(JobMatch)
class JobMatchAdmin(admin.ModelAdmin):
    list_display = ("id", "resume", "job_description", "overall_score", "status", "report_language", "created_at")
    list_filter = ("status", "report_language", "created_at")
    search_fields = (
        "resume__title",
        "job_description__title",
        "job_description__company",
        "user__username",
        "user__email",
    )
    readonly_fields = ("created_at",)
    raw_id_fields = ("user", "anonymous_identity", "resume", "job_description")
    ordering = ("-created_at",)


@admin.register(ATSReport)
class ATSReportAdmin(admin.ModelAdmin):
    list_display = ("id", "resume", "job_match", "score", "created_at")
    list_filter = ("created_at",)
    search_fields = ("resume__title", "user__username", "user__email")
    readonly_fields = ("created_at",)
    raw_id_fields = ("user", "anonymous_identity", "resume", "job_match")
    ordering = ("-created_at",)
