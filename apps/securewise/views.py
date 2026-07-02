"""
SecureWise SASP — API views.

All endpoints require authentication.
Users can only access organizations where they are members.
"""

from __future__ import annotations

import logging
import threading

from django.db.models import Q
from django.utils import timezone

from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

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
from .permissions import ADMIN_ROLES, WRITE_ROLES, _membership
from .serializers import (
    SecureWiseAuditLogSerializer,
    SecureWiseFindingSerializer,
    SecureWiseGitIntegrationSerializer,
    SecureWiseIntegrationSerializer,
    SecureWiseMembershipSerializer,
    SecureWiseOrganizationSerializer,
    SecureWiseProjectSerializer,
    SecureWiseReportSerializer,
    SecureWiseRepositorySerializer,
    SecureWiseScanPolicySerializer,
    SecureWiseScanSerializer,
    ScanEngineResultSerializer,
)
from .services.report import generate_report
from .services.repository import (
    check_private_access,
    check_public_access,
    detect_provider,
    normalize_url,
    validate_url_format,
)
from .services.scanner import ScannerRunner

logger = logging.getLogger(__name__)


def _get_user_org_ids(user):
    """Return queryset of org IDs where the user is a member."""
    return SecureWiseMembership.objects.filter(user=user).values_list("organization_id", flat=True)


def _audit(user, event, org=None, target_type="", target_id="", detail=None, request=None):
    ip = None
    if request:
        x_fwd = request.META.get("HTTP_X_FORWARDED_FOR", "")
        ip = x_fwd.split(",")[0].strip() if x_fwd else request.META.get("REMOTE_ADDR")
    SecureWiseAuditLog.objects.create(
        organization=org,
        user=user,
        event=event,
        target_type=target_type,
        target_id=str(target_id),
        detail=detail or {},
        ip_address=ip,
    )


# ---------------------------------------------------------------------------
# Organization
# ---------------------------------------------------------------------------


class OrganizationViewSet(viewsets.ModelViewSet):
    serializer_class = SecureWiseOrganizationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return SecureWiseOrganization.objects.filter(id__in=_get_user_org_ids(self.request.user)).prefetch_related(
            "memberships"
        )

    def perform_create(self, serializer):
        org = serializer.save(owner=self.request.user)
        # Auto-create owner membership
        SecureWiseMembership.objects.create(organization=org, user=self.request.user, role="owner")
        _audit(
            self.request.user,
            "organization_created",
            org=org,
            target_type="SecureWiseOrganization",
            target_id=org.id,
            detail={"name": org.name},
            request=self.request,
        )

    def perform_update(self, serializer):
        instance = serializer.instance
        m = _membership(self.request.user, instance)
        if m is None or m.role not in ADMIN_ROLES:
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("Only org owners/admins can update this organization.")
        serializer.save()

    def perform_destroy(self, instance):
        m = _membership(self.request.user, instance)
        if m is None or m.role != "owner":
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("Only the owner can delete this organization.")
        instance.delete()


# ---------------------------------------------------------------------------
# Membership
# ---------------------------------------------------------------------------


class MembershipViewSet(viewsets.ModelViewSet):
    serializer_class = SecureWiseMembershipSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return SecureWiseMembership.objects.filter(
            organization_id__in=_get_user_org_ids(self.request.user)
        ).select_related("user", "invited_by")

    def perform_create(self, serializer):
        org = serializer.validated_data["organization"]
        m = _membership(self.request.user, org)
        if m is None or m.role not in ADMIN_ROLES:
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("Only org admins can add members.")
        serializer.save(invited_by=self.request.user)


# ---------------------------------------------------------------------------
# Git Integration
# ---------------------------------------------------------------------------


class GitIntegrationViewSet(viewsets.ModelViewSet):
    serializer_class = SecureWiseGitIntegrationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return SecureWiseGitIntegration.objects.filter(
            organization_id__in=_get_user_org_ids(self.request.user)
        ).select_related("connected_by")

    def perform_create(self, serializer):
        org = serializer.validated_data["organization"]
        m = _membership(self.request.user, org)
        if m is None or m.role not in ADMIN_ROLES:
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("Only org owners/admins can create Git integrations.")
        instance = serializer.save(connected_by=self.request.user)
        _audit(
            self.request.user,
            "git_integration_created",
            org=org,
            target_type="SecureWiseGitIntegration",
            target_id=instance.id,
            detail={"provider": instance.provider, "name": instance.name},
            request=self.request,
        )

    def perform_update(self, serializer):
        org = serializer.instance.organization
        m = _membership(self.request.user, org)
        if m is None or m.role not in ADMIN_ROLES:
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("Only org owners/admins can update Git integrations.")
        instance = serializer.save()
        _audit(
            self.request.user,
            "git_integration_updated",
            org=org,
            target_type="SecureWiseGitIntegration",
            target_id=instance.id,
            request=self.request,
        )

    def perform_destroy(self, instance):
        m = _membership(self.request.user, instance.organization)
        if m is None or m.role not in ADMIN_ROLES:
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("Only org owners/admins can delete Git integrations.")
        _audit(
            self.request.user,
            "git_integration_deleted",
            org=instance.organization,
            target_type="SecureWiseGitIntegration",
            target_id=instance.id,
            request=self.request,
        )
        instance.delete()

    @action(detail=True, methods=["post"])
    def test(self, request, pk=None):
        """Test connectivity for this Git integration."""
        integration = self.get_object()
        token = integration.get_token()
        if not token:
            return Response({"detail": "No token stored for this integration."}, status=400)
        # Use a well-known API endpoint to verify token validity
        import ssl
        import urllib.error
        import urllib.request

        import certifi

        # Build an explicit SSL context backed by certifi's CA bundle instead of
        # relying on the OS trust store. This avoids "CERTIFICATE_VERIFY_FAILED:
        # unable to get local issuer certificate" errors that are common with
        # python.org / pyenv / some Homebrew Python builds on macOS that don't
        # have the system CA bundle wired up for the Python `ssl` module.
        ssl_context = ssl.create_default_context(cafile=certifi.where())

        headers = {"Authorization": f"token {token}", "User-Agent": "SecureWise-SASP/1.0"}
        base_url = integration.base_url.rstrip("/")
        if "github" in integration.provider:
            # github.com (SaaS) is served from api.github.com, NOT <base>/api/v3.
            # /api/v3 is only valid for GitHub Enterprise Server installations.
            if base_url in ("https://github.com", "http://github.com"):
                url = "https://api.github.com/user"
            else:
                url = f"{base_url}/api/v3/user"
        elif "gitlab" in integration.provider:
            gitlab_base = "https://gitlab.com" if base_url in ("https://gitlab.com", "http://gitlab.com") else base_url
            url = f"{gitlab_base}/api/v4/user"
            headers["Authorization"] = f"Bearer {token}"
        else:
            url = base_url

        success = False
        error_detail = ""
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10, context=ssl_context) as resp:
                success = resp.status == 200
        except urllib.error.HTTPError as e:
            # Surface enough info to debug without ever logging the token itself.
            if e.code in (401, 403):
                error_detail = "Authentication failed: token is invalid, expired, or lacks required scopes."
            elif e.code == 404:
                error_detail = "API endpoint not found. Check the integration's base URL."
            else:
                error_detail = f"Provider returned HTTP {e.code}."
            logger.warning(
                "SecureWise git integration test failed for integration=%s provider=%s: HTTP %s",
                integration.id,
                integration.provider,
                e.code,
            )
        except urllib.error.URLError as e:
            if isinstance(e.reason, ssl.SSLCertVerificationError) or "CERTIFICATE_VERIFY_FAILED" in str(e.reason):
                error_detail = (
                    "SSL certificate verification failed while contacting the provider. "
                    "This is usually a local Python/OS trust-store issue, not an invalid token. "
                    "Ensure the 'certifi' package is installed and up to date in this environment."
                )
            else:
                error_detail = f"Could not reach provider: {e.reason}"
            logger.warning(
                "SecureWise git integration test failed for integration=%s provider=%s: %s",
                integration.id,
                integration.provider,
                e.reason,
            )
        except Exception as e:
            error_detail = "Unexpected error while testing connection."
            logger.exception(
                "SecureWise git integration test raised unexpected error for integration=%s", integration.id
            )
        finally:
            del token  # always remove token from memory

        if success:
            integration.last_used_at = timezone.now()
            integration.status = "active"
            integration.save(update_fields=["last_used_at", "status"])
            return Response({"detail": "Connection successful.", "status": "active"})

        integration.status = "error"
        integration.save(update_fields=["status"])
        return Response(
            {"detail": error_detail or "Connection test failed. Verify token and permissions."},
            status=400,
        )

    @action(detail=True, methods=["post"], url_path="list-repositories")
    def list_repositories(self, request, pk=None):
        """List repositories accessible via this integration (MVP: returns placeholder)."""
        # TODO: Use provider API to list repos (GitHub API /user/repos, GitLab /projects, etc.)
        return Response(
            {
                "detail": "Repository listing via provider API coming soon.",
                "repositories": [],
            }
        )


# ---------------------------------------------------------------------------
# Project
# ---------------------------------------------------------------------------


class ProjectViewSet(viewsets.ModelViewSet):
    serializer_class = SecureWiseProjectSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = SecureWiseProject.objects.filter(organization_id__in=_get_user_org_ids(self.request.user)).select_related(
            "created_by"
        )
        org_id = self.request.query_params.get("organization")
        if org_id:
            qs = qs.filter(organization_id=org_id)
        return qs

    def perform_create(self, serializer):
        org = serializer.validated_data["organization"]
        m = _membership(self.request.user, org)
        if m is None or m.role not in WRITE_ROLES:
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("You do not have permission to create projects in this organization.")
        project = serializer.save(created_by=self.request.user)
        _audit(
            self.request.user,
            "project_created",
            org=org,
            target_type="SecureWiseProject",
            target_id=project.id,
            detail={"name": project.name},
            request=self.request,
        )

    def perform_update(self, serializer):
        org = serializer.instance.organization
        m = _membership(self.request.user, org)
        if m is None or m.role not in WRITE_ROLES:
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("You do not have permission to update this project.")
        serializer.save()

    def perform_destroy(self, instance):
        m = _membership(self.request.user, instance.organization)
        if m is None or m.role not in ADMIN_ROLES:
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("Only org admins can delete projects.")
        instance.delete()


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------


class RepositoryValidateThrottle(UserRateThrottle):
    scope = "sw_repo_validate"


class RepositoryViewSet(viewsets.ModelViewSet):
    serializer_class = SecureWiseRepositorySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = SecureWiseRepository.objects.filter(
            organization_id__in=_get_user_org_ids(self.request.user)
        ).select_related("project", "integration", "created_by")
        project_id = self.request.query_params.get("project")
        if project_id:
            qs = qs.filter(project_id=project_id)
        return qs

    def perform_create(self, serializer):
        org = serializer.validated_data["organization"]
        m = _membership(self.request.user, org)
        if m is None or m.role not in WRITE_ROLES:
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("You do not have permission to add repositories.")
        raw_url = serializer.validated_data.get("repository_url", "")
        url = normalize_url(raw_url)
        provider = detect_provider(url)
        clone_url = url + ".git"
        instance = serializer.save(
            created_by=self.request.user,
            repository_url=url,
            clone_url=clone_url,
            provider=provider,
        )
        _audit(
            self.request.user,
            "repository_added",
            org=org,
            target_type="SecureWiseRepository",
            target_id=instance.id,
            detail={"url": url},
            request=self.request,
        )

    @action(detail=False, methods=["post"], throttle_classes=[RepositoryValidateThrottle])
    def validate(self, request):
        """Pre-flight URL validation before saving a repository."""
        url_raw = request.data.get("repository_url", "").strip()
        access_mode = request.data.get("access_mode", "public")
        integration_id = request.data.get("integration_id")

        valid, err = validate_url_format(url_raw)
        if not valid:
            return Response({"accessible": False, "message": err}, status=400)

        url = normalize_url(url_raw)

        if access_mode == "public":
            accessible, msg = check_public_access(url)
        else:
            integration = None
            if integration_id:
                try:
                    integration = SecureWiseGitIntegration.objects.get(
                        id=integration_id,
                        organization_id__in=_get_user_org_ids(request.user),
                    )
                except SecureWiseGitIntegration.DoesNotExist:
                    return Response({"accessible": False, "message": "Integration not found."}, status=404)
            if integration:
                token = integration.get_token()
                accessible, msg = check_private_access(url, token)
                del token
            else:
                accessible, msg = False, "No integration provided for private repository."

        return Response(
            {
                "accessible": accessible,
                "message": msg,
                "provider": detect_provider(url),
            }
        )

    @action(detail=True, methods=["post"], url_path="test-access")
    def test_access(self, request, pk=None):
        repo = self.get_object()
        if repo.access_mode == "public":
            accessible, msg = check_public_access(repo.repository_url)
        elif repo.integration:
            token = repo.integration.get_token()
            accessible, msg = check_private_access(repo.repository_url, token)
            del token
        else:
            accessible, msg = False, "No integration configured for this private repository."

        repo.last_access_check_at = timezone.now()
        repo.last_access_status = "accessible" if accessible else "error"
        repo.save(update_fields=["last_access_check_at", "last_access_status"])
        return Response({"accessible": accessible, "message": msg})


# ---------------------------------------------------------------------------
# Scan Policy
# ---------------------------------------------------------------------------


class ScanPolicyViewSet(viewsets.ModelViewSet):
    serializer_class = SecureWiseScanPolicySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = SecureWiseScanPolicy.objects.filter(
            organization_id__in=_get_user_org_ids(self.request.user)
        ).select_related("created_by")
        project_id = self.request.query_params.get("project")
        if project_id:
            qs = qs.filter(project_id=project_id)
        return qs

    def perform_create(self, serializer):
        org = serializer.validated_data["organization"]
        m = _membership(self.request.user, org)
        if m is None or m.role not in WRITE_ROLES:
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("You do not have permission to create scan policies.")
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=["post"], url_path="set-default")
    def set_default(self, request, pk=None):
        policy = self.get_object()
        m = _membership(request.user, policy.organization)
        if m is None or m.role not in WRITE_ROLES:
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("You do not have permission to change the default policy.")
        policy.is_default = True
        policy.save(update_fields=["is_default"])  # save() demotes any other default for this org
        return Response(self.get_serializer(policy).data)


# ---------------------------------------------------------------------------
# Scan
# ---------------------------------------------------------------------------


class ScanViewSet(viewsets.ModelViewSet):
    serializer_class = SecureWiseScanSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "post", "head", "options"]  # No PATCH/DELETE on scans

    def get_queryset(self):
        qs = SecureWiseScan.objects.filter(organization_id__in=_get_user_org_ids(self.request.user)).select_related(
            "project", "repository", "policy", "triggered_by"
        )
        project_id = self.request.query_params.get("project")
        if project_id:
            qs = qs.filter(project_id=project_id)
        scan_type = self.request.query_params.get("scan_type")
        if scan_type:
            qs = qs.filter(scan_type=scan_type)
        scan_status = self.request.query_params.get("status")
        if scan_status:
            qs = qs.filter(status=scan_status)
        return qs

    def perform_create(self, serializer):
        org = serializer.validated_data["organization"]
        m = _membership(self.request.user, org)
        if m is None or m.role not in WRITE_ROLES:
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("You do not have permission to create scans.")
        scan = serializer.save(triggered_by=self.request.user, status="pending")
        # If the user didn't pick a policy and didn't explicitly bypass the gate,
        # auto-attach the organization's default policy (if one is configured) so
        # quality gate evaluation "just works" without extra clicks.
        if not scan.policy_id and not scan.bypass_quality_gate:
            default_policy = SecureWiseScanPolicy.objects.filter(
                organization=org, is_default=True, is_active=True
            ).first()
            if default_policy:
                scan.policy = default_policy
                scan.save(update_fields=["policy"])
        return scan

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    @action(detail=True, methods=["post"])
    def start(self, request, pk=None):
        scan = self.get_object()
        if scan.status not in ("pending", "failed"):
            return Response(
                {"detail": f"Cannot start a scan with status '{scan.status}'."},
                status=400,
            )
        scan.status = "queued"
        scan.save(update_fields=["status"])
        # Run scanner in background thread (MVP — use Celery/RQ in production)
        # TODO: Replace threading with Celery task for production
        runner = ScannerRunner()
        t = threading.Thread(target=runner.run_scan, args=(str(scan.id),), daemon=True)
        t.start()
        serializer = self.get_serializer(scan)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        scan = self.get_object()
        if scan.status not in ("pending", "queued") and not scan.status.startswith("running"):
            return Response(
                {"detail": f"Cannot cancel a scan with status '{scan.status}'."},
                status=400,
            )
        scan.status = "cancelled"
        scan.save(update_fields=["status"])
        return Response({"detail": "Scan cancelled.", "status": "cancelled"})

    @action(detail=True, methods=["post"])
    def retry(self, request, pk=None):
        """
        Re-run a scan that failed, was cancelled, or completed with warnings —
        using the exact same configuration. Clears any partial per-engine
        results from the previous attempt before re-running, so progress/
        engine-status reflect only the new attempt. The scan keeps its
        original id, so its finding history (first_seen/last_seen) carries
        over cleanly — a retry after a real fix will correctly auto-resolve
        findings that no longer reproduce.
        """
        scan = self.get_object()
        if scan.status not in ("failed", "cancelled", "completed_with_warnings", "completed"):
            return Response(
                {"detail": f"Cannot retry a scan with status '{scan.status}'."},
                status=400,
            )
        scan.engine_results.all().delete()
        scan.status = "queued"
        scan.progress = 0
        scan.error_message = ""
        scan.started_at = None
        scan.completed_at = None
        scan.duration_seconds = None
        scan.quality_gate_passed = None
        scan.save(
            update_fields=[
                "status",
                "progress",
                "error_message",
                "started_at",
                "completed_at",
                "duration_seconds",
                "quality_gate_passed",
            ]
        )
        SecureWiseAuditLog.objects.create(
            organization=scan.organization,
            user=request.user,
            event="scan_retried",
            target_type="SecureWiseScan",
            target_id=str(scan.id),
            detail={"scan_type": scan.scan_type},
        )
        runner = ScannerRunner()
        t = threading.Thread(target=runner.run_scan, args=(str(scan.id),), daemon=True)
        t.start()
        serializer = self.get_serializer(scan)
        return Response(serializer.data)

    @action(detail=True, methods=["get"])
    def progress(self, request, pk=None):
        scan = self.get_object()
        elapsed_seconds = None
        if scan.started_at:
            end = scan.completed_at or timezone.now()
            elapsed_seconds = int((end - scan.started_at).total_seconds())
        engines = [
            {
                "engine": er.engine,
                "status": er.status,
                "findings_count": er.findings_count,
                "skipped_reason": er.skipped_reason,
            }
            for er in scan.engine_results.all()
        ]
        return Response(
            {
                "id": str(scan.id),
                "status": scan.status,
                "progress": scan.progress,
                "elapsed_seconds": elapsed_seconds,
                "findings_count": scan.findings.count(),
                "engines": engines,
            }
        )

    @action(detail=True, methods=["get"], url_path="engine-results")
    def engine_results(self, request, pk=None):
        scan = self.get_object()
        serializer = ScanEngineResultSerializer(scan.engine_results.all(), many=True)
        return Response(serializer.data)


# ---------------------------------------------------------------------------
# Finding
# ---------------------------------------------------------------------------


class FindingViewSet(viewsets.ModelViewSet):
    serializer_class = SecureWiseFindingSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "patch", "post", "head", "options"]

    def get_queryset(self):
        qs = SecureWiseFinding.objects.filter(organization_id__in=_get_user_org_ids(self.request.user)).select_related(
            "scan", "project", "reviewed_by"
        )
        project_id = self.request.query_params.get("project")
        if project_id:
            qs = qs.filter(project_id=project_id)
        scan_id = self.request.query_params.get("scan")
        if scan_id:
            qs = qs.filter(scan_id=scan_id)
        severity = self.request.query_params.get("severity")
        if severity:
            qs = qs.filter(severity=severity)
        finding_status = self.request.query_params.get("status")
        if finding_status:
            qs = qs.filter(status=finding_status)
        search = self.request.query_params.get("search")
        if search:
            qs = qs.filter(Q(title__icontains=search) | Q(cwe_id__icontains=search))
        return qs

    def perform_update(self, serializer):
        old_status = serializer.instance.status
        instance = serializer.save()
        if instance.status != old_status:
            _audit(
                self.request.user,
                "finding_status_changed",
                org=instance.organization,
                target_type="SecureWiseFinding",
                target_id=instance.id,
                detail={"old_status": old_status, "new_status": instance.status},
                request=self.request,
            )

    @action(detail=True, methods=["post"], url_path="accept-risk")
    def accept_risk(self, request, pk=None):
        finding = self.get_object()
        old_status = finding.status
        finding.status = "accepted_risk"
        finding.reviewed_by = request.user
        finding.reviewed_at = timezone.now()
        finding.review_note = request.data.get("note", "")
        finding.save(update_fields=["status", "reviewed_by", "reviewed_at", "review_note"])
        _audit(
            request.user,
            "finding_status_changed",
            org=finding.organization,
            target_type="SecureWiseFinding",
            target_id=finding.id,
            detail={"old_status": old_status, "new_status": "accepted_risk", "note": finding.review_note},
            request=request,
        )
        return Response(self.get_serializer(finding).data)

    @action(detail=True, methods=["post"], url_path="mark-false-positive")
    def mark_false_positive(self, request, pk=None):
        finding = self.get_object()
        old_status = finding.status
        finding.status = "false_positive"
        finding.reviewed_by = request.user
        finding.reviewed_at = timezone.now()
        finding.review_note = request.data.get("note", "")
        finding.save(update_fields=["status", "reviewed_by", "reviewed_at", "review_note"])
        _audit(
            request.user,
            "finding_status_changed",
            org=finding.organization,
            target_type="SecureWiseFinding",
            target_id=finding.id,
            detail={"old_status": old_status, "new_status": "false_positive", "note": finding.review_note},
            request=request,
        )
        return Response(self.get_serializer(finding).data)


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


class ReportViewSet(viewsets.ModelViewSet):
    serializer_class = SecureWiseReportSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        qs = SecureWiseReport.objects.filter(organization_id__in=_get_user_org_ids(self.request.user)).select_related(
            "project", "scan", "generated_by"
        )
        project_id = self.request.query_params.get("project")
        if project_id:
            qs = qs.filter(project_id=project_id)
        return qs

    def perform_create(self, serializer):
        org = serializer.validated_data["organization"]
        m = _membership(self.request.user, org)
        if m is None:
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("You are not a member of this organization.")

        scan = serializer.validated_data.get("scan")
        report = serializer.save(generated_by=self.request.user, status="generating")
        report_type = self.request.data.get("report_type", "")

        # Generate report data synchronously for MVP
        # TODO: Move to background task for large scans
        try:
            if scan:
                report.report_data = generate_report(scan, report_type)
                report.quality_gate_passed = scan.quality_gate_passed
            report.status = "ready"
        except Exception as exc:
            logger.exception("Report generation failed for report %s", report.id)
            report.status = "failed"
            report.report_data = {"error": str(exc)}

        report.save(update_fields=["report_data", "quality_gate_passed", "status"])

        _audit(
            self.request.user,
            "report_generated",
            org=org,
            target_type="SecureWiseReport",
            target_id=report.id,
            detail={"title": report.title},
            request=self.request,
        )


# ---------------------------------------------------------------------------
# Integrations (Jira, Slack, etc.)
# ---------------------------------------------------------------------------


class IntegrationViewSet(viewsets.ModelViewSet):
    serializer_class = SecureWiseIntegrationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return SecureWiseIntegration.objects.filter(organization_id__in=_get_user_org_ids(self.request.user))

    def perform_create(self, serializer):
        org = serializer.validated_data["organization"]
        m = _membership(self.request.user, org)
        if m is None or m.role not in ADMIN_ROLES:
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("Only org admins can manage integrations.")
        serializer.save(created_by=self.request.user)


# ---------------------------------------------------------------------------
# Audit Log (read-only)
# ---------------------------------------------------------------------------


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = SecureWiseAuditLogSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = SecureWiseAuditLog.objects.filter(organization_id__in=_get_user_org_ids(self.request.user)).select_related(
            "user"
        )
        org_id = self.request.query_params.get("organization")
        if org_id:
            qs = qs.filter(organization_id=org_id)
        return qs


# ---------------------------------------------------------------------------
# Dashboard summary
# ---------------------------------------------------------------------------


class DashboardSummaryView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        org_ids = list(_get_user_org_ids(request.user))

        total_projects = SecureWiseProject.objects.filter(organization_id__in=org_ids).count()
        total_scans = SecureWiseScan.objects.filter(organization_id__in=org_ids).count()

        findings_qs = SecureWiseFinding.objects.filter(organization_id__in=org_ids, status="open")
        open_findings = findings_qs.count()
        critical_high = findings_qs.filter(severity__in=["critical", "high"]).count()

        # Severity breakdown
        severity_counts = {}
        for sev in ("critical", "high", "medium", "low", "info"):
            severity_counts[sev] = findings_qs.filter(severity=sev).count()

        # Recent scans (last 10)
        recent_scans = (
            SecureWiseScan.objects.filter(organization_id__in=org_ids)
            .select_related("project")
            .order_by("-created_at")[:10]
        )

        from .serializers import SecureWiseScanSerializer

        recent_scans_data = SecureWiseScanSerializer(recent_scans, many=True).data

        # Top risky projects (by open critical/high findings)
        from django.db.models import Count

        risky_projects = (
            SecureWiseFinding.objects.filter(
                organization_id__in=org_ids,
                status="open",
                severity__in=["critical", "high"],
            )
            .values("project__id", "project__name")
            .annotate(risk_count=Count("id"))
            .order_by("-risk_count")[:5]
        )

        # Simple security score (0–100, higher = fewer critical issues)
        security_score = 100
        if total_projects > 0:
            critical_count = severity_counts.get("critical", 0)
            high_count = severity_counts.get("high", 0)
            deduct = min(100, (critical_count * 10) + (high_count * 5))
            security_score = max(0, 100 - deduct)

        # OWASP Top 10 (2021) coverage across open findings
        from .services.report import _CWE_TOP25, _OWASP_TOP10_LABELS

        owasp_coverage = {
            code: findings_qs.filter(owasp_category=code).count() for code in _OWASP_TOP10_LABELS
        }
        cwe_top25_coverage = findings_qs.filter(cwe_id__in=list(_CWE_TOP25)).count()

        # Quality gate pass/fail counts across recent scans
        recent_scan_qs = SecureWiseScan.objects.filter(
            organization_id__in=org_ids, quality_gate_passed__isnull=False
        )
        quality_gate_counts = {
            "passed": recent_scan_qs.filter(quality_gate_passed=True).count(),
            "failed": recent_scan_qs.filter(quality_gate_passed=False).count(),
        }

        return Response(
            {
                "total_projects": total_projects,
                "total_scans": total_scans,
                "open_findings": open_findings,
                "critical_high_count": critical_high,
                "security_score": security_score,
                "severity_counts": severity_counts,
                "recent_scans": recent_scans_data,
                "top_risky_projects": list(risky_projects),
                "owasp_top10_coverage": owasp_coverage,
                "cwe_top25_coverage_count": cwe_top25_coverage,
                "quality_gate_counts": quality_gate_counts,
            }
        )
