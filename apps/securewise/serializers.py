from django.contrib.auth import get_user_model
from django.utils.text import slugify

from rest_framework import serializers

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
    SecureWiseScanEngineResult,
    SecureWiseScanPolicy,
)

User = get_user_model()


class MinimalUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "username", "email", "first_name", "last_name")
        read_only_fields = fields


# ---------------------------------------------------------------------------
# Organization
# ---------------------------------------------------------------------------


class SecureWiseOrganizationSerializer(serializers.ModelSerializer):
    owner_detail = MinimalUserSerializer(source="owner", read_only=True)
    member_count = serializers.SerializerMethodField()

    class Meta:
        model = SecureWiseOrganization
        fields = (
            "id",
            "name",
            "slug",
            "description",
            "website",
            "logo_url",
            "is_active",
            "owner",
            "owner_detail",
            "member_count",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "slug", "owner", "owner_detail", "member_count", "created_at", "updated_at")

    def get_member_count(self, obj):
        return obj.memberships.count()

    def validate(self, attrs):
        # Auto-generate slug from name if not provided
        if not attrs.get("slug") and attrs.get("name"):
            base = slugify(attrs["name"])
            slug = base
            n = 1
            while (
                SecureWiseOrganization.objects.filter(slug=slug)
                .exclude(pk=self.instance.pk if self.instance else None)
                .exists()
            ):
                slug = f"{base}-{n}"
                n += 1
            attrs["slug"] = slug
        return attrs


# ---------------------------------------------------------------------------
# Membership
# ---------------------------------------------------------------------------


class SecureWiseMembershipSerializer(serializers.ModelSerializer):
    user_detail = MinimalUserSerializer(source="user", read_only=True)

    class Meta:
        model = SecureWiseMembership
        fields = ("id", "organization", "user", "user_detail", "role", "invited_by", "created_at")
        read_only_fields = ("id", "invited_by", "created_at")


# ---------------------------------------------------------------------------
# Git Integration  — NEVER expose full token
# ---------------------------------------------------------------------------


class SecureWiseGitIntegrationSerializer(serializers.ModelSerializer):
    """Read serializer — token fields are excluded."""

    connected_by_detail = MinimalUserSerializer(source="connected_by", read_only=True)
    # Accept raw token on write only
    access_token = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = SecureWiseGitIntegration
        fields = (
            "id",
            "organization",
            "provider",
            "auth_type",
            "name",
            "base_url",
            "token_last_four",  # last 4 only, read-only
            "scopes",
            "connected_by",
            "connected_by_detail",
            "connected_at",
            "last_used_at",
            "status",
            "metadata",
            "created_at",
            "updated_at",
            "access_token",  # write-only
        )
        read_only_fields = (
            "id",
            "token_last_four",
            "connected_by",
            "connected_by_detail",
            "connected_at",
            "last_used_at",
            "created_at",
            "updated_at",
        )

    def create(self, validated_data):
        raw_token = validated_data.pop("access_token", None)
        instance = super().create(validated_data)
        if raw_token:
            instance.set_token(raw_token)
            instance.save(update_fields=["_encrypted_access_token", "token_last_four"])
        return instance

    def update(self, instance, validated_data):
        raw_token = validated_data.pop("access_token", None)
        instance = super().update(instance, validated_data)
        if raw_token:
            instance.set_token(raw_token)
            instance.save(update_fields=["_encrypted_access_token", "token_last_four"])
        return instance


# ---------------------------------------------------------------------------
# Project
# ---------------------------------------------------------------------------


class SecureWiseProjectSerializer(serializers.ModelSerializer):
    created_by_detail = MinimalUserSerializer(source="created_by", read_only=True)
    scan_count = serializers.SerializerMethodField()
    open_findings_count = serializers.SerializerMethodField()

    class Meta:
        model = SecureWiseProject
        fields = (
            "id",
            "organization",
            "name",
            "slug",
            "description",
            "tags",
            "risk_level",
            "is_active",
            "created_by",
            "created_by_detail",
            "scan_count",
            "open_findings_count",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "slug",
            "created_by",
            "created_by_detail",
            "scan_count",
            "open_findings_count",
            "created_at",
            "updated_at",
        )

    def get_scan_count(self, obj):
        return obj.scans.count()

    def validate(self, attrs):
        # Auto-generate slug from name if not provided
        if not attrs.get("slug") and attrs.get("name"):
            base = slugify(attrs["name"])
            slug = base
            n = 1
            org = attrs.get("organization", getattr(self.instance, "organization", None))
            while (
                SecureWiseProject.objects.filter(slug=slug, organization=org)
                .exclude(pk=self.instance.pk if self.instance else None)
                .exists()
            ):
                slug = f"{base}-{n}"
                n += 1
            attrs["slug"] = slug
        return attrs

    def get_open_findings_count(self, obj):
        return obj.findings.filter(status="open").count()


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------


class SecureWiseRepositorySerializer(serializers.ModelSerializer):
    created_by_detail = MinimalUserSerializer(source="created_by", read_only=True)

    class Meta:
        model = SecureWiseRepository
        fields = (
            "id",
            "organization",
            "project",
            "integration",
            "name",
            "provider",
            "repository_url",
            "clone_url",
            "default_branch",
            "visibility",
            "access_mode",
            "last_access_check_at",
            "last_access_status",
            "created_by",
            "created_by_detail",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "provider",
            "clone_url",
            "last_access_check_at",
            "last_access_status",
            "created_by",
            "created_by_detail",
            "created_at",
            "updated_at",
        )


# ---------------------------------------------------------------------------
# Scan Policy
# ---------------------------------------------------------------------------


class SecureWiseScanPolicySerializer(serializers.ModelSerializer):
    created_by_detail = MinimalUserSerializer(source="created_by", read_only=True)

    class Meta:
        model = SecureWiseScanPolicy
        fields = (
            "id",
            "organization",
            "project",
            "name",
            "description",
            "scan_types",
            "fail_on_severity",
            "max_critical",
            "max_high",
            "schedule_cron",
            "is_active",
            "created_by",
            "created_by_detail",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_by", "created_by_detail", "created_at", "updated_at")


# ---------------------------------------------------------------------------
# Scan
# ---------------------------------------------------------------------------


class SecureWiseScanSerializer(serializers.ModelSerializer):
    triggered_by_detail = MinimalUserSerializer(source="triggered_by", read_only=True)
    finding_counts = serializers.SerializerMethodField()

    class Meta:
        model = SecureWiseScan
        fields = (
            "id",
            "organization",
            "project",
            "repository",
            "policy",
            "scan_type",
            "branch",
            "commit_sha",
            "status",
            "progress",
            "selected_engines",
            "target_url",
            "api_spec_url",
            "docker_image",
            "triggered_by",
            "triggered_by_detail",
            "started_at",
            "completed_at",
            "duration_seconds",
            "error_message",
            "scanner_metadata",
            "quality_gate_passed",
            "finding_counts",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "organization",
            "progress",
            "selected_engines",
            "triggered_by",
            "triggered_by_detail",
            "started_at",
            "completed_at",
            "duration_seconds",
            "error_message",
            "scanner_metadata",
            "quality_gate_passed",
            "finding_counts",
            "created_at",
            "updated_at",
        )

    def validate(self, attrs):
        scan_type = attrs.get("scan_type", getattr(self.instance, "scan_type", "full"))
        repository = attrs.get("repository", getattr(self.instance, "repository", None))
        target_url = attrs.get("target_url", getattr(self.instance, "target_url", ""))
        api_spec_url = attrs.get("api_spec_url", getattr(self.instance, "api_spec_url", ""))

        # Engines that operate on cloned source code need a repository.
        source_dependent_types = {"sast", "sca", "secrets", "iac", "container"}
        if scan_type in source_dependent_types and not repository:
            raise serializers.ValidationError(
                {"repository": f"A repository is required to run a '{scan_type}' scan."}
            )
        if scan_type == "full" and not repository and not target_url and not api_spec_url:
            raise serializers.ValidationError(
                {
                    "repository": (
                        "A full scan needs at least a repository, target URL, or API spec — "
                        "otherwise there is nothing to scan."
                    )
                }
            )
        if scan_type == "dast" and not target_url:
            raise serializers.ValidationError({"target_url": "Target URL is required to run a DAST scan."})
        if scan_type == "api" and not api_spec_url and not repository:
            raise serializers.ValidationError(
                {"api_spec_url": "An OpenAPI spec URL/path or a repository is required to run an API scan."}
            )
        return attrs

    def get_finding_counts(self, obj):
        qs = obj.findings.values("severity").order_by()
        counts = {s: 0 for s in ("critical", "high", "medium", "low", "info")}
        for row in qs:
            counts[row["severity"]] = counts.get(row["severity"], 0) + 1
        counts["total"] = sum(counts.values())
        return counts

    def validate(self, attrs):
        # Auto-derive organization from project
        project = attrs.get("project", getattr(self.instance, "project", None))
        if project and not attrs.get("organization"):
            attrs["organization"] = project.organization
        return attrs


class ScanEngineResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = SecureWiseScanEngineResult
        fields = (
            "id",
            "scan",
            "engine",
            "status",
            "started_at",
            "completed_at",
            "duration_seconds",
            "findings_count",
            "skipped_reason",
            "raw_summary",
            "error_message",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


# ---------------------------------------------------------------------------
# Finding
# ---------------------------------------------------------------------------


class SecureWiseFindingSerializer(serializers.ModelSerializer):
    reviewed_by_detail = MinimalUserSerializer(source="reviewed_by", read_only=True)

    class Meta:
        model = SecureWiseFinding
        fields = (
            "id",
            "scan",
            "project",
            "organization",
            "title",
            "description",
            "file_path",
            "line_number",
            "endpoint",
            "cwe_id",
            "owasp_category",
            "scanner_type",
            "severity",
            "confidence",
            "status",
            "risk",
            "impact",
            "recommendation",
            "bad_code_example",
            "fixed_code_example",
            "evidence",
            "fingerprint",
            "ai_fix_suggestion",
            "reviewed_by",
            "reviewed_by_detail",
            "reviewed_at",
            "review_note",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "scan",
            "project",
            "organization",
            "reviewed_by",
            "reviewed_by_detail",
            "reviewed_at",
            "created_at",
            "updated_at",
        )


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


class SecureWiseReportSerializer(serializers.ModelSerializer):
    generated_by_detail = MinimalUserSerializer(source="generated_by", read_only=True)

    class Meta:
        model = SecureWiseReport
        fields = (
            "id",
            "organization",
            "project",
            "scan",
            "title",
            "format",
            "status",
            "report_data",
            "quality_gate_passed",
            "generated_by",
            "generated_by_detail",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "status",
            "report_data",
            "quality_gate_passed",
            "generated_by",
            "generated_by_detail",
            "created_at",
            "updated_at",
        )


# ---------------------------------------------------------------------------
# Integration (external tools)
# ---------------------------------------------------------------------------


class SecureWiseIntegrationSerializer(serializers.ModelSerializer):
    class Meta:
        model = SecureWiseIntegration
        fields = (
            "id",
            "organization",
            "integration_type",
            "name",
            "config",
            "is_active",
            "created_by",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_by", "created_at", "updated_at")


# ---------------------------------------------------------------------------
# Audit Log
# ---------------------------------------------------------------------------


class SecureWiseAuditLogSerializer(serializers.ModelSerializer):
    user_detail = MinimalUserSerializer(source="user", read_only=True)

    class Meta:
        model = SecureWiseAuditLog
        fields = (
            "id",
            "organization",
            "user",
            "user_detail",
            "event",
            "target_type",
            "target_id",
            "detail",
            "ip_address",
            "created_at",
        )
        read_only_fields = fields
