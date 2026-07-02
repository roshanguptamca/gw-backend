import uuid

from django.conf import settings
from django.core.validators import URLValidator
from django.db import models

from cryptography.fernet import Fernet


def _get_fernet():
    key = getattr(settings, "SECUREWISE_ENCRYPTION_KEY", None)
    if not key:
        # Fallback: derive from Django SECRET_KEY (dev only)
        import base64
        import hashlib

        raw = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
        key = base64.urlsafe_b64encode(raw)
    if isinstance(key, str):
        key = key.encode()
    return Fernet(key)


# ---------------------------------------------------------------------------
# Choices
# ---------------------------------------------------------------------------

ROLE_CHOICES = [
    ("owner", "Owner"),
    ("admin", "Admin"),
    ("security_engineer", "Security Engineer"),
    ("developer", "Developer"),
    ("auditor", "Auditor"),
]

SCAN_STATUS_CHOICES = [
    ("pending", "Pending"),
    ("queued", "Queued"),
    ("running", "Running"),
    ("cloning", "Cloning Repository"),
    ("running_sast", "Running SAST"),
    ("running_sca", "Running SCA"),
    ("running_secrets", "Running Secret Scan"),
    ("running_iac", "Running IaC Scan"),
    ("running_container", "Running Container Scan"),
    ("running_api", "Running API Scan"),
    ("running_dast", "Running DAST"),
    ("normalizing", "Normalizing Results"),
    ("completed", "Completed"),
    ("completed_with_warnings", "Completed with Warnings"),
    ("failed", "Failed"),
    ("cancelled", "Cancelled"),
]

ENGINE_CHOICES = [
    ("sast", "SAST"),
    ("sca", "SCA"),
    ("secrets", "Secret Scanning"),
    ("dast", "DAST"),
    ("iac", "IaC"),
    ("container", "Container"),
    ("api", "API Security"),
]

ENGINE_STATUS_CHOICES = [
    ("pending", "Pending"),
    ("running", "Running"),
    ("completed", "Completed"),
    ("skipped", "Skipped"),
    ("failed", "Failed"),
]

SCAN_TYPE_CHOICES = [
    ("sast", "SAST"),
    ("dast", "DAST"),
    ("sca", "SCA"),
    ("secrets", "Secret Scanning"),
    ("iac", "IaC"),
    ("container", "Container"),
    ("api", "API Security"),
    ("full", "Full Scan"),
]

SEVERITY_CHOICES = [
    ("critical", "Critical"),
    ("high", "High"),
    ("medium", "Medium"),
    ("low", "Low"),
    ("info", "Info"),
]

CONFIDENCE_CHOICES = [
    ("very_high", "Very High"),
    ("high", "High"),
    ("medium", "Medium"),
    ("low", "Low"),
]

FINDING_STATUS_CHOICES = [
    ("open", "Open"),
    ("fixed", "Fixed"),
    ("accepted_risk", "Accepted Risk"),
    ("false_positive", "False Positive"),
    ("ignored", "Ignored"),
]

GIT_PROVIDER_CHOICES = [
    ("github", "GitHub"),
    ("gitlab", "GitLab"),
    ("bitbucket", "Bitbucket"),
    ("azure_devops", "Azure DevOps"),
]

GIT_AUTH_TYPE_CHOICES = [
    ("public", "Public"),
    ("personal_access_token", "Personal Access Token"),
    ("oauth", "OAuth"),
    ("github_app", "GitHub App"),
]

GIT_INTEGRATION_STATUS_CHOICES = [
    ("active", "Active"),
    ("expired", "Expired"),
    ("revoked", "Revoked"),
    ("error", "Error"),
]

VISIBILITY_CHOICES = [
    ("public", "Public"),
    ("private", "Private"),
    ("internal", "Internal"),
]

ACCESS_MODE_CHOICES = [
    ("public", "Public"),
    ("integration", "Integration"),
]

LAST_ACCESS_STATUS_CHOICES = [
    ("accessible", "Accessible"),
    ("forbidden", "Forbidden"),
    ("not_found", "Not Found"),
    ("error", "Error"),
]

AUDIT_EVENT_CHOICES = [
    ("organization_created", "Organization Created"),
    ("project_created", "Project Created"),
    ("scan_started", "Scan Started"),
    ("scan_completed", "Scan Completed"),
    ("scan_failed", "Scan Failed"),
    ("finding_status_changed", "Finding Status Changed"),
    ("report_generated", "Report Generated"),
    ("git_integration_created", "Git Integration Created"),
    ("git_integration_updated", "Git Integration Updated"),
    ("git_integration_deleted", "Git Integration Deleted"),
    ("token_used_for_scan", "Token Used for Scan"),
    ("token_failed", "Token Failed"),
    ("repository_added", "Repository Added"),
    ("scan_engine_started", "Scan Engine Started"),
    ("scan_engine_completed", "Scan Engine Completed"),
    ("finding_created", "Finding Created"),
    ("finding_ticket_created", "Finding Ticket Created"),
    ("finding_ticket_failed", "Finding Ticket Failed"),
    ("finding_pr_created", "Finding PR Created"),
    ("finding_pr_failed", "Finding PR Failed"),
    ("scan_policy_updated", "Scan Policy Updated"),
    ("scan_policy_deleted", "Scan Policy Deleted"),
]


# ---------------------------------------------------------------------------
# Organization & Membership
# ---------------------------------------------------------------------------


class SecureWiseOrganization(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=150)
    slug = models.SlugField(unique=True, max_length=100)
    description = models.TextField(blank=True)
    website = models.URLField(blank=True)
    logo_url = models.URLField(blank=True)
    is_active = models.BooleanField(default=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="owned_sw_orgs",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Organization"
        verbose_name_plural = "Organizations"
        ordering = ["-created_at"]

    def __str__(self):
        return self.name


class SecureWiseMembership(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(SecureWiseOrganization, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sw_memberships")
    role = models.CharField(max_length=30, choices=ROLE_CHOICES, default="developer")
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sw_invitations_sent",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("organization", "user")
        verbose_name = "Membership"

    def __str__(self):
        return f"{self.user} @ {self.organization} ({self.role})"


# ---------------------------------------------------------------------------
# Git Integration
# ---------------------------------------------------------------------------


class SecureWiseGitIntegration(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(SecureWiseOrganization, on_delete=models.CASCADE, related_name="git_integrations")
    provider = models.CharField(max_length=30, choices=GIT_PROVIDER_CHOICES)
    auth_type = models.CharField(max_length=30, choices=GIT_AUTH_TYPE_CHOICES, default="personal_access_token")
    name = models.CharField(max_length=150)
    base_url = models.URLField(default="https://github.com")
    # Token is stored encrypted; never returned in API responses
    _encrypted_access_token = models.BinaryField(null=True, blank=True, db_column="encrypted_access_token")
    token_last_four = models.CharField(max_length=4, blank=True)
    scopes = models.JSONField(default=list, blank=True)
    connected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="sw_git_integrations_connected",
    )
    connected_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=GIT_INTEGRATION_STATUS_CHOICES, default="active")
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Git Integration"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.provider})"

    def set_token(self, raw_token: str):
        """Encrypt and store token; save last four digits."""
        if not raw_token:
            return
        f = _get_fernet()
        self._encrypted_access_token = f.encrypt(raw_token.encode())
        self.token_last_four = raw_token[-4:] if len(raw_token) >= 4 else raw_token

    def get_token(self) -> str | None:
        """Decrypt and return token. Never log the result."""
        if not self._encrypted_access_token:
            return None
        f = _get_fernet()
        raw = bytes(self._encrypted_access_token)
        return f.decrypt(raw).decode()


# ---------------------------------------------------------------------------
# Project
# ---------------------------------------------------------------------------


class SecureWiseProject(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(SecureWiseOrganization, on_delete=models.CASCADE, related_name="projects")
    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=100)
    description = models.TextField(blank=True)
    tags = models.JSONField(default=list, blank=True)
    risk_level = models.CharField(
        max_length=20,
        choices=SEVERITY_CHOICES,
        default="medium",
        help_text="Overall risk classification for this project.",
    )
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="sw_created_projects",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("organization", "slug")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.organization.name} / {self.name}"


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------


class SecureWiseRepository(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(SecureWiseOrganization, on_delete=models.CASCADE, related_name="repositories")
    project = models.ForeignKey(
        SecureWiseProject,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="repositories",
    )
    integration = models.ForeignKey(
        SecureWiseGitIntegration,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="repositories",
        help_text="Git integration used for private repo access.",
    )
    name = models.CharField(max_length=200)
    provider = models.CharField(max_length=30, choices=GIT_PROVIDER_CHOICES, blank=True)
    repository_url = models.CharField(max_length=500, validators=[URLValidator()])
    clone_url = models.CharField(max_length=500, blank=True)
    default_branch = models.CharField(max_length=100, default="main")
    visibility = models.CharField(max_length=20, choices=VISIBILITY_CHOICES, default="public")
    access_mode = models.CharField(max_length=20, choices=ACCESS_MODE_CHOICES, default="public")
    last_access_check_at = models.DateTimeField(null=True, blank=True)
    last_access_status = models.CharField(max_length=20, choices=LAST_ACCESS_STATUS_CHOICES, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="sw_created_repositories",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name


# ---------------------------------------------------------------------------
# Scan Policy
# ---------------------------------------------------------------------------


class SecureWiseScanPolicy(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(SecureWiseOrganization, on_delete=models.CASCADE, related_name="scan_policies")
    project = models.ForeignKey(
        SecureWiseProject,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="scan_policies",
    )
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    scan_types = models.JSONField(
        default=list,
        help_text="List of scan type keys, e.g. ['sast','sca']",
    )
    # Quality gate configuration
    fail_on_severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default="high")
    max_critical = models.IntegerField(default=0)
    max_high = models.IntegerField(default=5)
    max_medium = models.IntegerField(default=-1, help_text="-1 = unlimited.")
    fail_on_secrets = models.BooleanField(default=True, help_text="Fail the gate if any open secret finding exists.")
    fail_on_new_findings_only = models.BooleanField(
        default=False,
        help_text="Only evaluate findings first discovered by this scan, ignoring pre-existing recurring issues.",
    )
    allow_accepted_risks = models.BooleanField(
        default=True, help_text="Findings marked 'Accepted Risk' don't count against the gate."
    )
    allow_false_positives = models.BooleanField(
        default=True, help_text="Findings marked 'False Positive' don't count against the gate."
    )
    is_default = models.BooleanField(
        default=False,
        help_text="Automatically applied to new scans in this organization when no policy is explicitly chosen.",
    )
    schedule_cron = models.CharField(max_length=100, blank=True, help_text="Cron expression for auto-scheduling.")
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="sw_created_policies",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Scan Policy"
        verbose_name_plural = "Scan Policies"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.is_default:
            # Only one default policy per organization — demote any others.
            SecureWiseScanPolicy.objects.filter(organization=self.organization, is_default=True).exclude(
                pk=self.pk
            ).update(is_default=False)


# ---------------------------------------------------------------------------
# Scan
# ---------------------------------------------------------------------------


class SecureWiseScan(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(SecureWiseOrganization, on_delete=models.CASCADE, related_name="scans")
    project = models.ForeignKey(SecureWiseProject, on_delete=models.CASCADE, related_name="scans")
    repository = models.ForeignKey(
        SecureWiseRepository,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="scans",
    )
    policy = models.ForeignKey(
        SecureWiseScanPolicy,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="scans",
    )
    scan_type = models.CharField(max_length=20, choices=SCAN_TYPE_CHOICES, default="full")
    branch = models.CharField(max_length=200, blank=True)
    commit_sha = models.CharField(max_length=64, blank=True)
    status = models.CharField(max_length=30, choices=SCAN_STATUS_CHOICES, default="pending")
    triggered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="sw_triggered_scans",
    )
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.IntegerField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    scanner_metadata = models.JSONField(default=dict, blank=True)
    # Quality gate result
    quality_gate_passed = models.BooleanField(null=True, blank=True)
    bypass_quality_gate = models.BooleanField(
        default=False, help_text="User explicitly opted out of quality gate enforcement for this scan."
    )
    bypass_reason = models.TextField(blank=True, help_text="Why the quality gate was bypassed for this scan.")

    # A scan created via the "Retry" action points back at the scan it retried, for audit history.
    retry_of = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="retries",
    )

    progress = models.PositiveSmallIntegerField(default=0, help_text="Scan progress percentage (0-100).")
    selected_engines = models.JSONField(
        default=list, blank=True, help_text="Resolved list of engines this scan will run/ran, e.g. ['sast','sca']."
    )
    target_url = models.URLField(blank=True, help_text="Target URL for DAST scanning.")
    api_spec_url = models.CharField(
        max_length=500, blank=True, help_text="Path or URL to an OpenAPI/Swagger spec for API scanning."
    )
    docker_image = models.CharField(max_length=300, blank=True, help_text="Docker image reference for container scanning.")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Scan {self.id} [{self.scan_type}] - {self.status}"


class SecureWiseScanEngineResult(models.Model):
    """Per-engine result for a scan (e.g. sast/sca/secrets/dast/iac/container/api)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    scan = models.ForeignKey(SecureWiseScan, on_delete=models.CASCADE, related_name="engine_results")
    engine = models.CharField(max_length=20, choices=ENGINE_CHOICES)
    status = models.CharField(max_length=20, choices=ENGINE_STATUS_CHOICES, default="pending")
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.IntegerField(null=True, blank=True)
    findings_count = models.IntegerField(default=0)
    skipped_reason = models.TextField(blank=True)
    raw_summary = models.JSONField(default=dict, blank=True, help_text="Tool used, files scanned, deps parsed, etc.")
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.engine} [{self.status}] for scan {self.scan_id}"


# ---------------------------------------------------------------------------
# Finding
# ---------------------------------------------------------------------------


class SecureWiseFinding(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # `scan` always points at the MOST RECENT scan that (re-)detected this issue, so
    # `GET /scans/{id}/findings/` reflects "everything this scan run currently sees".
    scan = models.ForeignKey(SecureWiseScan, on_delete=models.CASCADE, related_name="findings")
    # `first_seen_scan` never changes after creation — it's when this issue (by fingerprint)
    # was first discovered for this project. Used for "new vs recurring" reporting and for
    # policies with fail_on_new_findings_only.
    first_seen_scan = models.ForeignKey(
        SecureWiseScan,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="findings_first_seen",
    )
    last_seen_at = models.DateTimeField(null=True, blank=True, help_text="When this issue was last re-detected.")
    occurrence_count = models.PositiveIntegerField(
        default=1, help_text="Number of scans (across time) that have re-detected this issue."
    )
    project = models.ForeignKey(SecureWiseProject, on_delete=models.CASCADE, related_name="findings")
    organization = models.ForeignKey(SecureWiseOrganization, on_delete=models.CASCADE, related_name="findings")

    title = models.CharField(max_length=500)
    description = models.TextField(blank=True)
    file_path = models.CharField(max_length=500, blank=True)
    line_number = models.IntegerField(null=True, blank=True)
    endpoint = models.CharField(max_length=500, blank=True)
    cwe_id = models.CharField(max_length=20, blank=True, help_text="e.g. CWE-79")
    owasp_category = models.CharField(max_length=50, blank=True, help_text="e.g. A01:2021")

    scanner_type = models.CharField(max_length=20, choices=SCAN_TYPE_CHOICES, blank=True)
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default="medium")
    confidence = models.CharField(max_length=20, choices=CONFIDENCE_CHOICES, default="medium")
    status = models.CharField(max_length=20, choices=FINDING_STATUS_CHOICES, default="open")

    risk = models.TextField(blank=True)
    impact = models.TextField(blank=True)
    recommendation = models.TextField(blank=True)
    bad_code_example = models.TextField(blank=True)
    fixed_code_example = models.TextField(blank=True)
    code_snippet = models.TextField(blank=True)
    ticket_url = models.URLField(max_length=500, blank=True)
    ticket_created_at = models.DateTimeField(null=True, blank=True)
    pr_url = models.URLField(max_length=500, blank=True)
    pr_created_at = models.DateTimeField(null=True, blank=True)
    evidence = models.JSONField(default=dict, blank=True)
    fingerprint = models.CharField(max_length=128, blank=True, db_index=True)

    # AI placeholder
    ai_fix_suggestion = models.TextField(
        blank=True,
        help_text="AI-generated fix recommendation. TODO: integrate LLM.",
    )

    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sw_reviewed_findings",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.severity.upper()}] {self.title}"

    @staticmethod
    def for_scan_q(scan_id):
        """
        Findings "belonging" to a scan run = anything first discovered in it OR
        still re-detected (last_seen) as of it. This lets a rescan of unchanged
        code keep showing pre-existing issues in the new scan's findings list,
        without creating duplicate rows for the same fingerprint.
        """
        from django.db.models import Q

        return Q(scan_id=scan_id) | Q(first_seen_scan_id=scan_id)


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


class SecureWiseReport(models.Model):
    REPORT_FORMAT_CHOICES = [
        ("json", "JSON"),
        ("html", "HTML"),
        ("pdf", "PDF"),
    ]
    REPORT_STATUS_CHOICES = [
        ("generating", "Generating"),
        ("ready", "Ready"),
        ("failed", "Failed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(SecureWiseOrganization, on_delete=models.CASCADE, related_name="reports")
    project = models.ForeignKey(SecureWiseProject, on_delete=models.CASCADE, related_name="reports")
    scan = models.ForeignKey(
        SecureWiseScan,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reports",
    )
    title = models.CharField(max_length=200)
    format = models.CharField(max_length=10, choices=REPORT_FORMAT_CHOICES, default="json")
    status = models.CharField(max_length=20, choices=REPORT_STATUS_CHOICES, default="generating")
    # Stores the full JSON report payload
    report_data = models.JSONField(default=dict, blank=True)
    quality_gate_passed = models.BooleanField(null=True, blank=True)
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="sw_generated_reports",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


# ---------------------------------------------------------------------------
# Integration (external tools: Jira, Slack, etc.)
# ---------------------------------------------------------------------------


class SecureWiseIntegration(models.Model):
    INTEGRATION_TYPE_CHOICES = [
        ("jira", "Jira"),
        ("slack", "Slack"),
        ("github_issues", "GitHub Issues"),
        ("pagerduty", "PagerDuty"),
        ("webhook", "Webhook"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(SecureWiseOrganization, on_delete=models.CASCADE, related_name="integrations")
    integration_type = models.CharField(max_length=30, choices=INTEGRATION_TYPE_CHOICES)
    name = models.CharField(max_length=150)
    config = models.JSONField(default=dict, blank=True, help_text="Non-sensitive config values.")
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="sw_created_integrations",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.integration_type})"


# ---------------------------------------------------------------------------
# Audit Log
# ---------------------------------------------------------------------------


class SecureWiseAuditLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        SecureWiseOrganization,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sw_audit_logs",
    )
    event = models.CharField(max_length=60, choices=AUDIT_EVENT_CHOICES)
    target_type = models.CharField(max_length=60, blank=True)
    target_id = models.CharField(max_length=64, blank=True)
    detail = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.event}] by {self.user} at {self.created_at}"
