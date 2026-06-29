from django.contrib import admin

from .models import (
    SecureWiseAuditLog,
    SecureWiseFinding,
    SecureWiseGitIntegration,
    SecureWiseIntegration,
    SecureWiseMembership,
    SecureWiseOrganization,
    SecureWiseProject,
    SecureWiseReport,
    SecureWiseRepository,
    SecureWiseScan,
    SecureWiseScanPolicy,
)


@admin.register(SecureWiseOrganization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "owner", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "slug")
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(SecureWiseMembership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "organization", "role", "created_at")
    list_filter = ("role",)
    search_fields = ("user__username", "user__email", "organization__name")
    readonly_fields = ("id", "created_at")


@admin.register(SecureWiseGitIntegration)
class GitIntegrationAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "provider", "auth_type", "status", "token_last_four", "connected_at")
    list_filter = ("provider", "auth_type", "status")
    search_fields = ("name", "organization__name")
    readonly_fields = ("id", "token_last_four", "connected_at", "last_used_at", "created_at", "updated_at")
    # Never show the encrypted token field
    exclude = ("_encrypted_access_token",)


@admin.register(SecureWiseProject)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "risk_level", "is_active", "created_at")
    list_filter = ("risk_level", "is_active")
    search_fields = ("name", "organization__name")
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(SecureWiseRepository)
class RepositoryAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "provider", "visibility", "access_mode", "last_access_status", "created_at")
    list_filter = ("provider", "visibility", "access_mode", "last_access_status")
    search_fields = ("name", "repository_url")
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(SecureWiseScanPolicy)
class ScanPolicyAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "fail_on_severity", "is_active", "created_at")
    list_filter = ("fail_on_severity", "is_active")
    search_fields = ("name",)
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(SecureWiseScan)
class ScanAdmin(admin.ModelAdmin):
    list_display = ("id", "project", "scan_type", "status", "triggered_by", "started_at", "completed_at")
    list_filter = ("scan_type", "status")
    search_fields = ("project__name",)
    readonly_fields = ("id", "started_at", "completed_at", "duration_seconds", "created_at", "updated_at")


@admin.register(SecureWiseFinding)
class FindingAdmin(admin.ModelAdmin):
    list_display = ("title", "project", "severity", "confidence", "status", "cwe_id", "owasp_category", "created_at")
    list_filter = ("severity", "confidence", "status", "scanner_type")
    search_fields = ("title", "cwe_id", "fingerprint")
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(SecureWiseReport)
class ReportAdmin(admin.ModelAdmin):
    list_display = ("title", "project", "format", "status", "quality_gate_passed", "generated_by", "created_at")
    list_filter = ("format", "status", "quality_gate_passed")
    search_fields = ("title",)
    readonly_fields = ("id", "report_data", "created_at", "updated_at")


@admin.register(SecureWiseIntegration)
class IntegrationAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "integration_type", "is_active", "created_at")
    list_filter = ("integration_type", "is_active")
    search_fields = ("name",)
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(SecureWiseAuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("event", "organization", "user", "target_type", "target_id", "created_at")
    list_filter = ("event",)
    search_fields = ("user__username", "organization__name")
    readonly_fields = ("id", "created_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
