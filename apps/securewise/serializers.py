import ipaddress
import json
import re

from django.contrib.auth import get_user_model
from django.utils.text import slugify

from rest_framework import serializers

from .models import (
    PentestEvidence,
    PentestExecution,
    PentestScope,
    PentestSession,
    PentestTestCase,
    PentestTestProposal,
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
    SecureWiseScanPolicyTemplate,
)
from .runtime.logs import redact_secrets, tail_lines

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

    def validate(self, attrs):
        auth_type = attrs.get("auth_type", getattr(self.instance, "auth_type", ""))
        if auth_type == "github_app":
            raise serializers.ValidationError(
                {"auth_type": "GitHub App access is managed through the installation flow, not personal tokens."}
            )
        return attrs

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
        organization = attrs.get("organization", getattr(self.instance, "organization", None))
        if self.instance and organization and organization.id != self.instance.organization_id:
            raise serializers.ValidationError({"organization": "Projects cannot be moved to another organization."})
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
            "local_path",
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

    def validate(self, attrs):
        organization = attrs.get("organization", getattr(self.instance, "organization", None))
        project = attrs.get("project", getattr(self.instance, "project", None))
        integration = attrs.get("integration", getattr(self.instance, "integration", None))
        access_mode = attrs.get("access_mode", getattr(self.instance, "access_mode", "public"))
        if organization and project and project.organization_id != organization.id:
            raise serializers.ValidationError({"project": "The project must belong to the selected organization."})
        if integration and organization and integration.organization_id != organization.id:
            raise serializers.ValidationError(
                {"integration": "The Git integration must belong to the selected organization."}
            )
        if access_mode == "github_app" and (self.instance is None or self.instance.access_mode != "github_app"):
            raise serializers.ValidationError(
                {"access_mode": "GitHub App repositories can only be synchronized from an installation."}
            )
        if self.instance and self.instance.access_mode == "github_app":
            immutable_fields = {
                "organization",
                "integration",
                "repository_url",
                "access_mode",
                "name",
                "provider",
                "default_branch",
                "visibility",
            }
            if immutable_fields.intersection(attrs):
                raise serializers.ValidationError(
                    {"repository_url": "GitHub App repository identity is managed by the installation sync."}
                )
        installation = attrs.get(
            "github_app_installation",
            getattr(self.instance, "github_app_installation", None),
        )
        if installation and organization and installation.organization_id != organization.id:
            raise serializers.ValidationError(
                {"github_app_installation": "The GitHub App installation must belong to the selected organization."}
            )
        return attrs


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
            "max_medium",
            "fail_on_secrets",
            "fail_on_new_findings_only",
            "allow_accepted_risks",
            "allow_false_positives",
            "is_default",
            "schedule_cron",
            "is_active",
            "created_by",
            "created_by_detail",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_by", "created_by_detail", "created_at", "updated_at")

    def validate(self, attrs):
        organization = attrs.get("organization", getattr(self.instance, "organization", None))
        project = attrs.get("project", getattr(self.instance, "project", None))
        if organization and project and project.organization_id != organization.id:
            raise serializers.ValidationError({"project": "The project must belong to the selected organization."})
        return attrs


class SecureWiseScanPolicyTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SecureWiseScanPolicyTemplate
        fields = (
            "id",
            "key",
            "name",
            "description",
            "recommended_for",
            "scan_types",
            "fail_on_severity",
            "max_critical",
            "max_high",
            "max_medium",
            "fail_on_secrets",
            "fail_on_new_findings_only",
            "allow_accepted_risks",
            "allow_false_positives",
            "is_recommended",
            "is_active",
            "sort_order",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


# ---------------------------------------------------------------------------
# Scan
# ---------------------------------------------------------------------------


class SecureWiseScanSerializer(serializers.ModelSerializer):
    triggered_by_detail = MinimalUserSerializer(source="triggered_by", read_only=True)
    finding_counts = serializers.SerializerMethodField()
    can_retry = serializers.SerializerMethodField()
    error_message = serializers.SerializerMethodField()

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
            "bypass_quality_gate",
            "bypass_reason",
            "retry_of",
            "triggered_by",
            "triggered_by_detail",
            "started_at",
            "completed_at",
            "duration_seconds",
            "error_message",
            "scanner_metadata",
            "quality_gate_passed",
            "finding_counts",
            "can_retry",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "organization",
            "progress",
            "selected_engines",
            "retry_of",
            "triggered_by",
            "triggered_by_detail",
            "started_at",
            "completed_at",
            "duration_seconds",
            "error_message",
            "scanner_metadata",
            "quality_gate_passed",
            "finding_counts",
            "can_retry",
            "created_at",
            "updated_at",
        )

    def validate(self, attrs):
        # Auto-derive organization from project.
        project = attrs.get("project", getattr(self.instance, "project", None))
        organization = project.organization if project else attrs.get(
            "organization", getattr(self.instance, "organization", None)
        )
        if organization:
            attrs["organization"] = organization
        if project and organization and project.organization_id != organization.id:
            raise serializers.ValidationError({"project": "The project must belong to the selected organization."})
        repository = attrs.get("repository", getattr(self.instance, "repository", None))
        policy = attrs.get("policy", getattr(self.instance, "policy", None))
        if repository and project and (
            repository.organization_id != project.organization_id or repository.project_id != project.id
        ):
            raise serializers.ValidationError(
                {"repository": "The repository must be associated with the selected project and organization."}
            )
        if policy and organization and policy.organization_id != organization.id:
            raise serializers.ValidationError({"policy": "The policy must belong to the selected organization."})
        if policy and project and policy.project_id not in (None, project.id):
            raise serializers.ValidationError({"policy": "The policy must apply to the selected project."})

        scan_type = attrs.get("scan_type", getattr(self.instance, "scan_type", "full"))
        target_url = attrs.get("target_url", getattr(self.instance, "target_url", ""))
        api_spec_url = attrs.get("api_spec_url", getattr(self.instance, "api_spec_url", ""))

        # Engines that operate on cloned source code need a repository.
        source_dependent_types = {"sast", "sca", "secrets", "iac", "container"}
        if scan_type in source_dependent_types and not repository:
            raise serializers.ValidationError({"repository": f"A repository is required to run a '{scan_type}' scan."})
        if scan_type == "full" and not repository and not target_url and not api_spec_url:
            raise serializers.ValidationError(
                {
                    "repository": (
                        "A full scan needs at least a repository, target URL, or API spec — "
                        "otherwise there is nothing to scan."
                    )
                }
            )
        if scan_type == "dast" and not target_url and not repository:
            raise serializers.ValidationError(
                {
                    "target_url": (
                        "Target URL is required to run a DAST scan unless a repository is attached "
                        "and SecureWise can auto-start the application runtime."
                    )
                }
            )
        if scan_type == "api" and not api_spec_url and not repository:
            raise serializers.ValidationError(
                {"api_spec_url": "An OpenAPI spec URL/path or a repository is required to run an API scan."}
            )

        bypass = attrs.get("bypass_quality_gate", getattr(self.instance, "bypass_quality_gate", False))
        bypass_reason = attrs.get("bypass_reason", getattr(self.instance, "bypass_reason", ""))
        if bypass and not bypass_reason.strip():
            raise serializers.ValidationError(
                {"bypass_reason": "A reason is required when bypassing the quality gate (for audit purposes)."}
            )
        return attrs

    def get_finding_counts(self, obj):
        qs = obj.findings.values("severity").order_by()
        counts = {s: 0 for s in ("critical", "high", "medium", "low", "info")}
        for row in qs:
            counts[row["severity"]] = counts.get(row["severity"], 0) + 1
        counts["total"] = sum(counts.values())
        return counts

    def get_can_retry(self, obj):
        return obj.status in ("failed", "cancelled", "completed_with_warnings", "completed", "completed_partial")

    def get_error_message(self, obj):
        return redact_secrets(tail_lines(obj.error_message or "", max_lines=80))[:4000]


class ScanEngineResultSerializer(serializers.ModelSerializer):
    diagnostics = serializers.SerializerMethodField()
    error_message = serializers.SerializerMethodField()

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
            "diagnostics",
            "error_message",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_diagnostics(self, obj):
        raw_summary = obj.raw_summary or {}
        log_excerpt = (
            raw_summary.get("dast_runtime_logs")
            or raw_summary.get("stdout")
            or raw_summary.get("stderr")
            or obj.error_message
            or obj.skipped_reason
            or ""
        )
        return {
            "log_excerpt": redact_secrets(tail_lines(str(log_excerpt), max_lines=80))[:4000],
            "stage": raw_summary.get("stage", ""),
            "root_cause": redact_secrets(str(raw_summary.get("root_cause", "")))[:1000],
            "retryable": raw_summary.get("retryable"),
            "mode": raw_summary.get("mode", ""),
            "execution_mode": raw_summary.get("execution_mode", ""),
            "coverage": raw_summary.get("coverage", {}),
        }

    def get_error_message(self, obj):
        return redact_secrets(tail_lines(obj.error_message or "", max_lines=80))[:4000]


class PentestEvidenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = PentestEvidence
        fields = ("id", "kind", "content", "sha256", "created_at")
        read_only_fields = fields


class PentestExecutionSerializer(serializers.ModelSerializer):
    evidence = PentestEvidenceSerializer(many=True, read_only=True)

    class Meta:
        model = PentestExecution
        fields = ("id", "outcome", "started_at", "completed_at", "duration_ms", "summary", "error_message", "evidence")
        read_only_fields = fields


class PentestTestCaseSerializer(serializers.ModelSerializer):
    executions = PentestExecutionSerializer(many=True, read_only=True)

    class Meta:
        model = PentestTestCase
        fields = (
            "id",
            "test_key",
            "title",
            "category",
            "endpoint",
            "method",
            "expected_behavior",
            "status",
            "severity",
            "confidence",
            "cwe_id",
            "owasp_category",
            "recommendation",
            "source",
            "executions",
        )
        read_only_fields = fields


class PentestTestProposalSerializer(serializers.ModelSerializer):
    class Meta:
        model = PentestTestProposal
        fields = (
            "id",
            "proposal_key",
            "test_type",
            "title",
            "endpoint",
            "method",
            "required_role",
            "expected_property",
            "safe_method",
            "required_test_data",
            "parameter_schema",
            "safe_parameters",
            "estimated_cost",
            "cwe_id",
            "owasp_category",
            "severity",
            "confidence",
            "rationale",
            "limitations",
            "execution_mode",
            "executable",
            "approval_status",
            "source",
            "test_case",
        )
        read_only_fields = tuple(set(fields) - {"safe_parameters"})

    def validate_safe_parameters(self, value):
        if not isinstance(value, dict) or len(value) > 20:
            raise serializers.ValidationError("Provide a bounded object of safe parameter values.")
        schema = self.instance.parameter_schema if self.instance else {}
        if not set(value).issubset(schema):
            raise serializers.ValidationError("Only planner-declared safe parameters may be edited.")
        for name, selected in value.items():
            definition = schema[name]
            kind = definition.get("type")
            if kind == "enum":
                valid = selected in definition.get("values", [])
            elif kind == "integer":
                valid = isinstance(selected, int) and not isinstance(selected, bool) and -100000 <= selected <= 100000
            elif kind == "boolean":
                valid = isinstance(selected, bool)
            else:
                valid = False
            if not valid:
                raise serializers.ValidationError({name: "Value is not in the safe parameter schema."})
        return value


class PentestScopeSerializer(serializers.ModelSerializer):
    class Meta:
        model = PentestScope
        fields = ("scheme", "host", "port")

    def validate_host(self, value):
        host = value.strip().lower().rstrip(".")
        if not host or "*" in host or "/" in host or "://" in host:
            raise serializers.ValidationError("Provide one exact approved hostname or IP address.")
        try:
            ipaddress.ip_address(host)
        except ValueError:
            valid_hostname = re.fullmatch(
                r"(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)(?:\.(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?))*",
                host,
            )
        else:
            valid_hostname = True
        if not valid_hostname:
            raise serializers.ValidationError("The approved host is not a valid hostname or IP address.")
        return host

    def validate_port(self, value):
        if not 1 <= value <= 65535:
            raise serializers.ValidationError("Approved ports must be between 1 and 65535.")
        return value


class PentestSessionSerializer(serializers.ModelSerializer):
    scope = PentestScopeSerializer(many=True)
    auth_config = serializers.JSONField(write_only=True, required=False)
    retest_of = serializers.PrimaryKeyRelatedField(
        queryset=PentestSession.objects.all(), required=False, allow_null=True
    )
    test_cases = PentestTestCaseSerializer(many=True, read_only=True)
    organization = serializers.PrimaryKeyRelatedField(read_only=True)
    unified_scan = serializers.PrimaryKeyRelatedField(read_only=True)
    status = serializers.CharField(read_only=True)
    progress = serializers.IntegerField(read_only=True)
    error_message = serializers.SerializerMethodField()
    proposals = PentestTestProposalSerializer(many=True, read_only=True)
    security_inventory = serializers.JSONField(read_only=True)
    coverage = serializers.SerializerMethodField()
    retest_comparison = serializers.SerializerMethodField()

    class Meta:
        model = PentestSession
        fields = (
            "id",
            "organization",
            "project",
            "repository",
            "retest_of",
            "authorization_confirmed",
            "authorization_reference",
            "mode",
            "auth_config",
            "unified_scan",
            "status",
            "progress",
            "scope",
            "test_cases",
            "proposals",
            "security_inventory",
            "coverage",
            "retest_comparison",
            "error_message",
            "timeout_seconds",
            "requests_per_minute",
            "started_at",
            "completed_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "organization",
            "status",
            "progress",
            "test_cases",
            "error_message",
            "started_at",
            "completed_at",
            "created_at",
            "updated_at",
        )

    def validate(self, attrs):
        if not attrs.get("authorization_confirmed"):
            raise serializers.ValidationError({"authorization_confirmed": "Explicit authorization is required."})
        if len(attrs.get("authorization_reference", "").strip()) < 8:
            raise serializers.ValidationError(
                {"authorization_reference": "Provide a meaningful authorization record or approval reference."}
            )
        scopes = attrs.get("scope", [])
        if not scopes or len(scopes) > 20:
            raise serializers.ValidationError({"scope": "Provide between 1 and 20 exact approved host/port entries."})
        project = attrs["project"]
        repository = attrs["repository"]
        if repository.organization_id != project.organization_id or repository.project_id != project.id:
            raise serializers.ValidationError(
                {"repository": "The repository must be associated with this project and organization."}
            )
        scope_keys = [(entry["scheme"], entry["host"], entry["port"]) for entry in scopes]
        if len(scope_keys) != len(set(scope_keys)):
            raise serializers.ValidationError({"scope": "Approved scope entries must be unique."})
        retest_of = attrs.get("retest_of")
        if retest_of and (
            retest_of.project_id != project.id
            or retest_of.repository_id != repository.id
            or retest_of.organization_id != project.organization_id
        ):
            raise serializers.ValidationError(
                {"retest_of": "A retest must use the same project, repository, and organization."}
            )
        if not 1 <= attrs.get("timeout_seconds", 900) <= 900:
            raise serializers.ValidationError(
                {"timeout_seconds": "Assessment timeouts must be between 1 and 900 seconds."}
            )
        if not 1 <= attrs.get("requests_per_minute", 30) <= 60:
            raise serializers.ValidationError(
                {"requests_per_minute": "Assessment rates must be between 1 and 60 requests per minute."}
            )
        mode = attrs.get("mode", "passive")
        if mode == "approved_tests":
            raise serializers.ValidationError(
                {"mode": "Approved tests can only be queued through the proposal approval workflow."}
            )
        auth_config = attrs.get("auth_config", {})
        auth_mode = mode
        if mode == "security_planning":
            if (
                not isinstance(auth_config, dict)
                or auth_config.get("type") != "planner"
                or auth_config.get("execution_mode") not in {"authenticated_api", "authenticated_browser"}
                or not isinstance(auth_config.get("ai_enabled", False), bool)
                or not isinstance(auth_config.get("credentials"), dict)
            ):
                raise serializers.ValidationError(
                    {"auth_config": "Planning requires a supported execution mode and synthetic test credentials."}
                )
            auth_mode = auth_config["execution_mode"]
            auth_config = auth_config["credentials"]
        if auth_mode == "authenticated_api":
            if (
                not isinstance(auth_config, dict)
                or auth_config.get("type") != "bearer"
                or not isinstance(auth_config.get("users"), list)
                or len(auth_config["users"]) < 2
            ):
                raise serializers.ValidationError(
                    {
                        "auth_config": "Authenticated API mode requires bearer credentials for at least two synthetic users."
                    }
                )
            users = auth_config["users"]
            labels = set()
            subjects = set()
            tokens = set()
            for user in users:
                if (
                    not isinstance(user, dict)
                    or not all(
                        isinstance(user.get(field), str) and user[field].strip()
                        for field in ("label", "subject", "role", "token")
                    )
                    or len(user["token"]) > 4096
                ):
                    raise serializers.ValidationError(
                        {
                            "auth_config": "Each test identity needs a label, subject, role, and token no longer than 4096 characters."
                        }
                    )
                labels.add(user["label"])
                subjects.add(user["subject"])
                tokens.add(user["token"])
            if len(labels) != len(users) or len(subjects) != len(users) or len(tokens) != len(users):
                raise serializers.ValidationError(
                    {"auth_config": "Test identity labels, subjects, and tokens must be unique."}
                )
            if len(users) > 10:
                raise serializers.ValidationError({"auth_config": "At most 10 synthetic test identities are allowed."})
            if any(
                entry["scheme"] != "http" or entry["host"] not in {"127.0.0.1", "::1", "localhost"} for entry in scopes
            ):
                raise serializers.ValidationError(
                    {"scope": "Authenticated live tests are restricted to approved loopback fixture runtimes."}
                )
        elif auth_mode == "authenticated_browser":
            allowed_journeys = {
                "protected-page",
                "cross-user-resource",
                "role-boundary",
                "logout",
                "session-expiration",
                "session-cookie",
            }
            users = auth_config.get("users") if isinstance(auth_config, dict) else None
            journeys = auth_config.get("journeys") if isinstance(auth_config, dict) else None
            if (
                not isinstance(auth_config, dict)
                or auth_config.get("type") != "browser"
                or not isinstance(users, list)
                or len(users) < 2
            ):
                raise serializers.ValidationError(
                    {"auth_config": "Browser mode requires credentials for at least two synthetic users."}
                )
            if (
                not isinstance(journeys, list)
                or not journeys
                or len(journeys) > len(allowed_journeys)
                or any(journey not in allowed_journeys for journey in journeys)
                or len(journeys) != len(set(journeys))
            ):
                raise serializers.ValidationError(
                    {"auth_config": "Select one or more supported deterministic browser journeys."}
                )
            labels = set()
            subjects = set()
            usernames = set()
            for user in users:
                if (
                    not isinstance(user, dict)
                    or not all(
                        isinstance(user.get(field), str) and user[field].strip()
                        for field in ("label", "subject", "role", "username", "password")
                    )
                    or len(user["username"]) > 200
                    or len(user["password"]) > 4096
                ):
                    raise serializers.ValidationError(
                        {"auth_config": "Each browser identity needs a label, subject, role, username and password."}
                    )
                labels.add(user["label"])
                subjects.add(user["subject"])
                usernames.add(user["username"])
            if len(labels) != len(users) or len(subjects) != len(users) or len(usernames) != len(users):
                raise serializers.ValidationError(
                    {"auth_config": "Browser identity labels, subjects, and usernames must be unique."}
                )
            if len(users) > 10:
                raise serializers.ValidationError(
                    {"auth_config": "At most 10 synthetic browser identities are allowed."}
                )
            if any(
                entry["scheme"] != "http" or entry["host"] not in {"127.0.0.1", "::1", "localhost"} for entry in scopes
            ):
                raise serializers.ValidationError(
                    {"scope": "Browser tests are restricted to approved loopback fixture runtimes."}
                )
        return attrs

    def get_coverage(self, obj):
        coverage = dict((obj.security_inventory or {}).get("coverage", {}))
        executed = obj.test_cases.exclude(status="planned")
        coverage.update(
            {
                "executed_tests": executed.count(),
                "confirmed_findings": executed.filter(status="confirmed_vulnerability").count(),
                "passed_tests": executed.filter(status="passed").count(),
                "skipped_or_unsupported": obj.proposals.filter(approval_status="unsupported").count()
                + executed.filter(status="not_executed").count(),
                "untested_routes": max(
                    0,
                    coverage.get("discovered_routes", coverage.get("discovered_endpoints", 0))
                    - executed.values("endpoint").distinct().count(),
                ),
            }
        )
        return coverage

    def get_retest_comparison(self, obj):
        baseline = obj.retest_of
        if baseline is None:
            return None
        baseline_cases = {case.test_key: case for case in baseline.test_cases.all()}
        current_cases = {case.test_key: case for case in obj.test_cases.all()}
        fixed = []
        still_confirmed = []
        suspected = []
        newly_confirmed = []
        not_retested = []
        for key, previous in baseline_cases.items():
            current = current_cases.get(key)
            if previous.status == "confirmed_vulnerability":
                if current is None or current.status in {"not_executed", "inconclusive"}:
                    not_retested.append(key)
                elif current.status == "passed":
                    fixed.append(key)
                elif current.status == "confirmed_vulnerability":
                    still_confirmed.append(key)
                elif current.status == "suspected_vulnerability":
                    suspected.append(key)
        for key, current in current_cases.items():
            previous = baseline_cases.get(key)
            if current.status == "confirmed_vulnerability" and (
                previous is None or previous.status != "confirmed_vulnerability"
            ):
                newly_confirmed.append(key)
        return {
            "baseline_session_id": str(baseline.id),
            "baseline_cases": len(baseline_cases),
            "retest_cases": len(current_cases),
            "fixed": fixed,
            "still_confirmed": still_confirmed,
            "suspected": suspected,
            "newly_confirmed": newly_confirmed,
            "not_retested": not_retested,
        }

    def create(self, validated_data):
        scopes = validated_data.pop("scope")
        auth_config = validated_data.pop("auth_config", {})
        retest_of = validated_data.pop("retest_of", None)
        project = validated_data["project"]
        session = PentestSession.objects.create(
            organization=project.organization,
            status="queued",
            created_by=self.context["request"].user,
            retest_of=retest_of,
            **validated_data,
        )
        if auth_config:
            session.set_auth_config(auth_config)
            session.save(update_fields=["_encrypted_auth_config"])
        PentestScope.objects.bulk_create([PentestScope(session=session, **scope) for scope in scopes])
        return session

    def get_error_message(self, obj):
        return redact_secrets(tail_lines(obj.error_message or "", max_lines=80))[:4000]


# ---------------------------------------------------------------------------
# Finding
# ---------------------------------------------------------------------------


class SecureWiseFindingSerializer(serializers.ModelSerializer):
    reviewed_by_detail = MinimalUserSerializer(source="reviewed_by", read_only=True)
    ai_fix_suggestion_parsed = serializers.SerializerMethodField()

    def get_ai_fix_suggestion_parsed(self, obj):
        if not obj.ai_fix_suggestion:
            return None
        try:
            return json.loads(obj.ai_fix_suggestion)
        except (TypeError, ValueError):
            return None

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
            "code_snippet",
            "ticket_url",
            "ticket_created_at",
            "pr_url",
            "pr_created_at",
            "evidence",
            "fingerprint",
            "ai_fix_suggestion",
            "ai_fix_suggestion_parsed",
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
            "code_snippet",
            "ticket_url",
            "ticket_created_at",
            "pr_url",
            "pr_created_at",
            "ai_fix_suggestion",
            "ai_fix_suggestion_parsed",
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

    def validate(self, attrs):
        organization = attrs.get("organization", getattr(self.instance, "organization", None))
        project = attrs.get("project", getattr(self.instance, "project", None))
        scan = attrs.get("scan", getattr(self.instance, "scan", None))
        if organization and project and project.organization_id != organization.id:
            raise serializers.ValidationError({"project": "The project must belong to the selected organization."})
        if scan and organization and scan.organization_id != organization.id:
            raise serializers.ValidationError({"scan": "The scan must belong to the selected organization."})
        if scan and project and scan.project_id != project.id:
            raise serializers.ValidationError({"scan": "The scan must belong to the selected project."})
        return attrs


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
