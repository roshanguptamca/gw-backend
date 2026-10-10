"""
SecureWise SASP — API views.

All endpoints require authentication.
Users can only access organizations where they are members.
"""

from __future__ import annotations

import json
import logging
import os
import re
import secrets
import hashlib
from datetime import timedelta
from uuid import UUID

from django.db import IntegrityError, transaction
from django.db.models import Avg, Count, Q
from django.http import HttpResponse
from django.utils.decorators import method_decorator
from django.utils import timezone
from django.utils.text import slugify
from django.views.generic import TemplateView
from django.views.decorators.csrf import csrf_exempt

from rest_framework import mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from .models import (
    PentestSession,
    PentestTestProposal,
    SecureWiseAuditLog,
    SecureWiseFinding,
    SecureWiseGitIntegration,
    SecureWiseGitHubAppInstallation,
    SecureWiseGitHubAppState,
    SecureWiseGitHubWebhookDelivery,
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
    SecureWiseWorkerRegistration,
)
from .permissions import ADMIN_ROLES, WRITE_ROLES, _membership
from .runtime.logs import redact_secrets, tail_lines
from .scanners.cwe_mapping import SECURITY_TAXONOMY, taxonomy_metadata
from .scanners.repository import validate_local_repository_path
from .serializers import (
    PentestSessionSerializer,
    PentestTestProposalSerializer,
    ScanEngineResultSerializer,
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
    SecureWiseScanPolicyTemplateSerializer,
    SecureWiseScanSerializer,
)
from .services.ai_recommendation import generate_ai_fix_suggestion
from .services import github_app
from .services.github_actions import GitHubActionError, create_github_issue, create_github_pr
from .services.report import generate_report
from .services.report_render import render_report_html, render_report_pdf
from .services.worker import _SCAN_ACTIVE_STATUSES
from .services.repository import (
    check_private_access,
    check_public_access,
    detect_provider,
    normalize_url,
    validate_url_format,
)

logger = logging.getLogger(__name__)


class SecureWiseDocumentationView(TemplateView):
    template_name = "securewise/docs/documentation.html"


class SecureWiseUserManualView(TemplateView):
    template_name = "securewise/docs/user_manual.html"


def _get_user_org_ids(user):
    """Return queryset of org IDs where the user is a member."""
    return SecureWiseMembership.objects.filter(user=user).values_list("organization_id", flat=True)


def _parse_uuid(value):
    try:
        return UUID(str(value))
    except (AttributeError, TypeError, ValueError):
        return None


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


class GitHubAppConnectView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        organization_id = _parse_uuid(request.data.get("organization"))
        if organization_id is None:
            return Response({"detail": "A valid organization ID is required."}, status=400)
        membership = SecureWiseMembership.objects.filter(
            organization_id=organization_id,
            user=request.user,
            role__in=ADMIN_ROLES,
        ).select_related("organization").first()
        if membership is None:
            return Response({"detail": "Organization admin access is required."}, status=403)
        if not github_app.app_configured():
            return Response({"detail": "GitHub App credentials are not configured."}, status=503)
        try:
            slug = github_app.app_slug()
        except github_app.GitHubAppError as exc:
            return Response({"detail": str(exc)}, status=503)
        now = timezone.now()
        SecureWiseGitHubAppState.objects.filter(
            Q(expires_at__lt=now) | Q(consumed_at__lt=now - timedelta(hours=1))
        ).delete()
        raw_state = secrets.token_urlsafe(32)
        SecureWiseGitHubAppState.objects.create(
            state_digest=github_app.state_digest(raw_state),
            organization=membership.organization,
            user=request.user,
            expires_at=now + timedelta(minutes=10),
        )
        return Response(
            {
                "installation_url": f"https://github.com/apps/{slug}/installations/new?state={raw_state}",
                "expires_in_seconds": 600,
            }
        )


class GitHubAppCallbackView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        state = request.query_params.get("state", "")
        installation_id = request.query_params.get("installation_id", "")
        setup_action = request.query_params.get("setup_action", "")
        if (
            not state
            or len(state) > 256
            or setup_action not in ("install", "update")
            or not installation_id.isdecimal()
            or len(installation_id) > 20
            or int(installation_id) <= 0
            or int(installation_id) > 2**63 - 1
        ):
            return Response({"detail": "Invalid GitHub App callback."}, status=400)
        if not github_app.app_configured():
            return Response({"detail": "GitHub App credentials are not configured."}, status=503)

        with transaction.atomic():
            state_row = (
                SecureWiseGitHubAppState.objects.select_for_update()
                .filter(state_digest=github_app.state_digest(state), user=request.user)
                .select_related("organization")
                .first()
            )
            if (
                state_row is None
                or state_row.consumed_at is not None
                or state_row.expires_at <= timezone.now()
                or not SecureWiseMembership.objects.filter(
                    organization=state_row.organization, user=request.user, role__in=ADMIN_ROLES
                ).exists()
            ):
                return Response({"detail": "GitHub App state is invalid, expired, or already used."}, status=400)
            state_row.consumed_at = timezone.now()
            state_row.save(update_fields=["consumed_at"])

        try:
            details = github_app.get_installation(int(installation_id))
        except github_app.GitHubAppError as exc:
            return Response({"detail": str(exc)}, status=502)
        account = details.get("account") or {}
        if (
            details.get("id") != int(installation_id)
            or not isinstance(account, dict)
            or not isinstance(account.get("login"), str)
            or not account["login"]
            or not isinstance(account.get("id"), int)
            or isinstance(account.get("id"), bool)
            or account["id"] <= 0
            or account["id"] > 2**63 - 1
            or int(installation_id) > 2**63 - 1
        ):
            return Response({"detail": "GitHub returned invalid installation details."}, status=502)
        existing_installation = SecureWiseGitHubAppInstallation.objects.filter(
            installation_id=int(installation_id)
        ).first()
        if existing_installation and existing_installation.organization_id != state_row.organization_id:
            return Response({"detail": "This installation is already connected to another organization."}, status=409)
        if existing_installation is None:
            from django.utils.dateparse import parse_datetime

            created_at = details.get("created_at")
            installed_at = parse_datetime(created_at) if isinstance(created_at, str) else None
            if (
                setup_action != "install"
                or installed_at is None
                or not timezone.is_aware(installed_at)
                or installed_at < state_row.created_at - timedelta(minutes=2)
                or installed_at > timezone.now() + timedelta(minutes=2)
            ):
                return Response(
                    {"detail": "A new GitHub installation must be created from this authorization flow."},
                    status=400,
                )
        installed_permissions = details.get("permissions") or {}
        if (
            not isinstance(installed_permissions, dict)
            or installed_permissions.get("contents") != "read"
            or any(
                permission != "read" for permission in installed_permissions.values()
            )
        ):
            return Response(
                {"detail": "The GitHub App must have read-only contents access and no write permissions."},
                status=403,
            )
        try:
            installation, created = SecureWiseGitHubAppInstallation.objects.update_or_create(
                installation_id=int(installation_id),
                defaults={
                    "organization": state_row.organization,
                    "account_id": int(account["id"]),
                    "account_login": str(account["login"])[:200],
                    "account_type": str(account.get("type", ""))[:30],
                    "permissions": details.get("permissions") or {},
                    "suspended_at": (
                        timezone.now()
                        if details.get("suspended_at") or details.get("suspended_by")
                        else None
                    ),
                    "removed_at": None,
                    "created_by": request.user,
                },
            )
        except IntegrityError:
            return Response(
                {"detail": "This GitHub account is already connected to the organization."},
                status=409,
            )
        _audit(
            request.user,
            "github_app_installation_created",
            org=state_row.organization,
            target_type="SecureWiseGitHubAppInstallation",
            target_id=installation.id,
            detail={"account": installation.account_login, "installation_id": installation.installation_id},
            request=request,
        )
        frontend_url = os.environ.get("SECUREWISE_FRONTEND_URL", "").rstrip("/")
        if frontend_url.startswith("https://") or frontend_url.startswith("http://localhost"):
            from django.http import HttpResponseRedirect

            return HttpResponseRedirect(f"{frontend_url}/repositories?github_app=connected")
        return Response(
            {
                "detail": "GitHub App installation connected.",
                "installation": str(installation.id),
                "created": created,
            }
        )


class GitHubAppInstallationView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        installations = SecureWiseGitHubAppInstallation.objects.filter(
            organization_id__in=_get_user_org_ids(request.user)
        ).order_by("account_login")
        return Response(
            [
                {
                    "id": str(item.id),
                    "organization": str(item.organization_id),
                    "installation_id": item.installation_id,
                    "account_login": item.account_login,
                    "account_type": item.account_type,
                    "permissions": item.permissions,
                    "suspended": item.suspended_at is not None,
                    "removed": item.removed_at is not None,
                    "available": github_app.installation_is_active(item),
                }
                for item in installations
            ]
        )

    def post(self, request):
        installation_id = request.data.get("installation")
        if not installation_id:
            return Response({"detail": "Installation is required."}, status=400)
        installation_uuid = _parse_uuid(installation_id)
        if installation_uuid is None:
            return Response({"detail": "A valid installation ID is required."}, status=400)
        installation = SecureWiseGitHubAppInstallation.objects.filter(
            id=installation_uuid,
            organization_id__in=_get_user_org_ids(request.user),
            removed_at__isnull=True,
            suspended_at__isnull=True,
        ).first()
        if installation is None or not github_app.installation_is_active(installation):
            return Response({"detail": "Installation not found or unavailable."}, status=404)
        try:
            repositories = github_app.list_installation_repositories(installation.installation_id)
        except github_app.GitHubAppError as exc:
            return Response({"detail": str(exc)}, status=502)
        return Response(
            [
                {
                    "id": item.get("id"),
                    "full_name": item.get("full_name"),
                    "private": bool(item.get("private")),
                    "default_branch": item.get("default_branch", "main"),
                    "html_url": f"https://github.com/{item.get('full_name', '')}",
                }
                for item in repositories
                if isinstance(item.get("id"), int)
                and not isinstance(item.get("id"), bool)
                and isinstance(item.get("full_name"), str)
                and re.fullmatch(r"[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}", item["full_name"])
            ]
        )


class GitHubAppRepositorySelectionView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        installation_uuid = _parse_uuid(request.data.get("installation"))
        if installation_uuid is None:
            return Response({"detail": "A valid installation ID is required."}, status=400)
        installation = SecureWiseGitHubAppInstallation.objects.filter(
            id=installation_uuid,
            organization_id__in=_get_user_org_ids(request.user),
            removed_at__isnull=True,
            suspended_at__isnull=True,
        ).select_related("organization").first()
        if installation is None or not github_app.installation_is_active(installation):
            return Response({"detail": "Installation not found or unavailable."}, status=404)
        if not SecureWiseMembership.objects.filter(
            organization=installation.organization, user=request.user, role__in=ADMIN_ROLES
        ).exists():
            return Response({"detail": "Organization admin access is required."}, status=403)
        repository_ids = request.data.get("repository_ids")
        if (
            not isinstance(repository_ids, list)
            or not repository_ids
            or len(repository_ids) > 100
            or any(not isinstance(value, int) or isinstance(value, bool) or value <= 0 for value in repository_ids)
        ):
            return Response({"detail": "Select between 1 and 100 repository IDs."}, status=400)
        project_id = request.data.get("project")
        project = None
        if project_id:
            project_uuid = _parse_uuid(project_id)
            if project_uuid is None:
                return Response({"detail": "A valid project ID is required."}, status=400)
            project = SecureWiseProject.objects.filter(
                id=project_uuid, organization=installation.organization
            ).first()
            if project is None:
                return Response({"detail": "Project not found in this organization."}, status=400)
        try:
            available = github_app.list_installation_repositories(installation.installation_id)
        except github_app.GitHubAppError as exc:
            return Response({"detail": str(exc)}, status=502)
        by_id = {
            item.get("id"): item
            for item in available
            if isinstance(item.get("id"), int)
            and not isinstance(item.get("id"), bool)
            and 0 < item["id"] <= 2**63 - 1
        }
        if len(set(repository_ids)) != len(repository_ids) or any(repo_id not in by_id for repo_id in repository_ids):
            return Response({"detail": "A selected repository is not available to this installation."}, status=400)

        synced = []
        for repo_id in repository_ids:
            details = by_id[repo_id]
            full_name = details.get("full_name", "")
            if not isinstance(full_name, str) or not re.fullmatch(
                r"[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}", full_name
            ):
                return Response({"detail": "GitHub returned an invalid repository identifier."}, status=502)
            defaults = {
                "github_app_installation": installation,
                "project": project,
                "name": full_name,
                "provider": "github",
                "repository_url": f"https://github.com/{full_name}",
                "clone_url": "",
                "default_branch": str(details.get("default_branch") or "main")[:100],
                "visibility": "private" if details.get("private") else "public",
                "access_mode": "github_app",
                "created_by": request.user,
            }
            repository, created = SecureWiseRepository.objects.get_or_create(
                organization=installation.organization,
                provider_repository_id=repo_id,
                defaults=defaults,
            )
            if not created and repository.github_app_installation_id != installation.id:
                return Response({"detail": "Repository is linked to another installation."}, status=409)
            if not created:
                changed = []
                for field, value in defaults.items():
                    if field == "project" and value is None:
                        continue
                    current = (
                        repository.github_app_installation_id
                        if field == "github_app_installation"
                        else getattr(repository, field)
                    )
                    expected = value.id if field == "github_app_installation" else value
                    if current != expected:
                        setattr(repository, field, value)
                        changed.append(field)
                if changed:
                    repository.save(update_fields=changed + ["updated_at"])
            _audit(
                request.user,
                "github_app_repository_synced",
                org=installation.organization,
                target_type="SecureWiseRepository",
                target_id=repository.id,
                detail={"repository": full_name, "created": created},
                request=request,
            )
            synced.append(repository)
        return Response(SecureWiseRepositorySerializer(synced, many=True).data, status=200)


@method_decorator(csrf_exempt, name="dispatch")
class GitHubAppWebhookView(APIView):
    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        content_length = request.headers.get("Content-Length", "")
        if content_length.isdecimal() and int(content_length) > 1024 * 1024:
            return Response({"detail": "Webhook payload exceeds the size limit."}, status=413)
        body = request.body
        if len(body) > 1024 * 1024:
            return Response({"detail": "Webhook payload exceeds the size limit."}, status=413)
        signature = request.headers.get("X-Hub-Signature-256", "")
        secret = os.environ.get("SECUREWISE_GITHUB_APP_WEBHOOK_SECRET", "")
        if not github_app.verify_webhook_signature(secret, body, signature):
            return Response({"detail": "Invalid webhook signature."}, status=401)
        delivery_id = request.headers.get("X-GitHub-Delivery", "")
        event_type = request.headers.get("X-GitHub-Event", "")
        if not delivery_id or len(delivery_id) > 200 or not event_type or len(event_type) > 100:
            return Response({"detail": "Missing or invalid webhook headers."}, status=400)
        try:
            payload = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return Response({"detail": "Invalid webhook payload."}, status=400)
        if not isinstance(payload, dict):
            return Response({"detail": "Invalid webhook payload."}, status=400)
        payload_hash = hashlib.sha256(body).hexdigest()
        try:
            with transaction.atomic():
                SecureWiseGitHubWebhookDelivery.objects.create(
                    delivery_id=delivery_id,
                    event_type=event_type,
                    payload_sha256=payload_hash,
                )
                installation_data = payload.get("installation") or {}
                installation_id = installation_data.get("id")
                if isinstance(installation_id, int):
                    linked = SecureWiseGitHubAppInstallation.objects.select_for_update().filter(
                        installation_id=installation_id
                    ).select_related("organization").first()
                    if linked:
                        github_app.mark_installation_event(linked, f"{event_type}.{payload.get('action', '')}", payload)
                        _audit(
                            None,
                            "github_app_webhook_received",
                            org=linked.organization,
                            target_type="SecureWiseGitHubAppInstallation",
                            target_id=linked.id,
                            detail={"event": event_type, "action": payload.get("action", "")},
                        )
        except IntegrityError:
            return Response({"detail": "Webhook delivery already processed."}, status=202)
        return Response({"detail": "Webhook accepted."}, status=202)


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
        if serializer.validated_data.get("role") == "owner" and self.request.user.id != org.owner_id:
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("Only the organization owner can assign the owner role.")
        serializer.save(invited_by=self.request.user)

    def perform_update(self, serializer):
        instance = serializer.instance
        membership = _membership(self.request.user, instance.organization)
        if membership is None or membership.role not in ADMIN_ROLES:
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("Only org admins can update memberships.")
        if instance.user_id == instance.organization.owner_id:
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("The organization owner's membership cannot be changed.")
        if (
            serializer.validated_data.get("organization", instance.organization).id != instance.organization_id
            or serializer.validated_data.get("user", instance.user).id != instance.user_id
        ):
            from rest_framework.exceptions import ValidationError

            raise ValidationError({"detail": "Membership organization and user cannot be changed."})
        if serializer.validated_data.get("role") == "owner" and self.request.user.id != instance.organization.owner_id:
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("Only the organization owner can assign the owner role.")
        serializer.save()

    def perform_destroy(self, instance):
        membership = _membership(self.request.user, instance.organization)
        if membership is None or membership.role not in ADMIN_ROLES:
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("Only org admins can remove memberships.")
        if instance.user_id == instance.organization.owner_id:
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("The organization owner's membership cannot be removed.")
        instance.delete()


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
        membership = _membership(request.user, integration.organization)
        if membership is None or membership.role not in ADMIN_ROLES:
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("Only organization admins can test Git integrations.")
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
        except Exception:
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


class AIRecommendationThrottle(UserRateThrottle):
    scope = "securewise_ai_suggestion"
    rate = "20/hour"


class GitHubActionThrottle(UserRateThrottle):
    scope = "securewise_github_action"


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
        access_mode = serializer.validated_data.get("access_mode", "public")
        if access_mode == "local_path":
            local_path = serializer.validated_data.get("local_path", "")
            valid, message, resolved_path = validate_local_repository_path(local_path)
            if not valid or resolved_path is None:
                from rest_framework.exceptions import ValidationError

                raise ValidationError({"local_path": message})
            instance = serializer.save(
                created_by=self.request.user,
                repository_url="",
                clone_url="",
                local_path=str(resolved_path),
                provider="",
                visibility="private",
            )
            audit_detail = {"access_mode": "local_path", "name": instance.name}
        else:
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
            audit_detail = {"url": url}
        _audit(
            self.request.user,
            "repository_added",
            org=org,
            target_type="SecureWiseRepository",
            target_id=instance.id,
            detail=audit_detail,
            request=self.request,
        )

    def perform_update(self, serializer):
        repository = serializer.instance
        membership = _membership(self.request.user, repository.organization)
        if membership is None or membership.role not in WRITE_ROLES:
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("You do not have permission to update this repository.")
        organization = serializer.validated_data.get("organization", repository.organization)
        if organization.id != repository.organization_id:
            from rest_framework.exceptions import ValidationError

            raise ValidationError({"organization": "Repositories cannot be moved to another organization."})
        serializer.save()

    def perform_destroy(self, instance):
        membership = _membership(self.request.user, instance.organization)
        if membership is None or membership.role not in ADMIN_ROLES:
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("Only org admins can delete repositories.")
        instance.delete()

    @action(detail=False, methods=["post"], throttle_classes=[RepositoryValidateThrottle])
    def validate(self, request):
        """Pre-flight URL validation before saving a repository."""
        url_raw = request.data.get("repository_url", "").strip()
        local_path = request.data.get("local_path", "").strip()
        access_mode = request.data.get("access_mode", "public")
        integration_id = request.data.get("integration_id")

        if access_mode == "local_path":
            valid, msg, resolved_path = validate_local_repository_path(local_path)
            return Response(
                {
                    "accessible": valid,
                    "message": msg,
                    "provider": "",
                    "local_path": str(resolved_path) if resolved_path else "",
                },
                status=200 if valid else 400,
            )

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
        if repo.access_mode == "local_path":
            accessible, msg, _resolved_path = validate_local_repository_path(repo.local_path)
        elif repo.access_mode == "public":
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

    @action(detail=True, methods=["post"], url_path="discovery-preview", throttle_classes=[RepositoryValidateThrottle])
    def discovery_preview(self, request, pk=None):
        """
        Clone the repository into a temporary, isolated workspace and run
        ApplicationDiscoveryEngine — no engines run and no scan is created.
        Used by the "Run Scan" wizard to show a live preview of detected
        language/framework, whether a runtime can be auto-started, and
        whether DAST will be possible before the user commits to a scan.
        """
        import tempfile
        import types
        from pathlib import Path

        from .discovery.engine import ApplicationDiscoveryEngine
        from .scanners.repository import clone_repository

        repo = self.get_object()

        try:
            with tempfile.TemporaryDirectory(prefix="sw_preview_") as tmpdir:
                repo_path = Path(tmpdir) / "repo"
                fake_scan = types.SimpleNamespace(repository=repo)
                clone_repository(fake_scan, repo_path, allowed_root=Path(tmpdir))
                plan = ApplicationDiscoveryEngine().discover(repo_path)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Discovery preview failed for repository %s: %s", repo.id, exc)
            return Response(
                {"error": "Could not clone or analyze this repository for a preview.", "detail": str(exc)},
                status=422,
            )

        return Response(plan.to_dict())


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

    def perform_update(self, serializer):
        org = serializer.instance.organization
        m = _membership(self.request.user, org)
        if m is None or m.role not in WRITE_ROLES:
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("You do not have permission to edit scan policies.")
        new_org = serializer.validated_data.get("organization")
        if new_org is not None and new_org.id != org.id:
            from rest_framework.exceptions import ValidationError

            raise ValidationError({"organization": "Cannot move a policy to a different organization."})
        instance = serializer.save()
        _audit(
            self.request.user,
            "scan_policy_updated",
            org=org,
            target_type="SecureWiseScanPolicy",
            target_id=instance.id,
            detail={"name": instance.name},
            request=self.request,
        )

    def perform_destroy(self, instance):
        m = _membership(self.request.user, instance.organization)
        if m is None or m.role not in WRITE_ROLES:
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("You do not have permission to delete scan policies.")
        _audit(
            self.request.user,
            "scan_policy_deleted",
            org=instance.organization,
            target_type="SecureWiseScanPolicy",
            target_id=instance.id,
            detail={"name": instance.name},
            request=self.request,
        )
        instance.delete()

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


class ScanPolicyTemplateViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = SecureWiseScanPolicyTemplateSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return SecureWiseScanPolicyTemplate.objects.filter(is_active=True)

    @action(detail=True, methods=["post"], url_path="create-policy")
    def create_policy(self, request, pk=None):
        template = self.get_object()
        org_id = request.data.get("organization")
        if not org_id:
            return Response({"organization": "This field is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            org = SecureWiseOrganization.objects.get(id=org_id, id__in=_get_user_org_ids(request.user))
        except SecureWiseOrganization.DoesNotExist:
            return Response({"organization": "Organization not found."}, status=status.HTTP_404_NOT_FOUND)

        m = _membership(request.user, org)
        if m is None or m.role not in WRITE_ROLES:
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("You do not have permission to create scan policies.")

        project = None
        project_id = request.data.get("project")
        if project_id:
            try:
                project = SecureWiseProject.objects.get(id=project_id, organization=org)
            except SecureWiseProject.DoesNotExist:
                return Response(
                    {"project": "Project not found in this organization."}, status=status.HTTP_400_BAD_REQUEST
                )

        set_as_default = bool(request.data.get("set_as_default", False))
        name = (request.data.get("name") or template.name).strip()
        name = self._unique_policy_name(org, name)
        policy = SecureWiseScanPolicy.objects.create(
            organization=org,
            project=project,
            name=name,
            description=template.description,
            scan_types=template.scan_types,
            fail_on_severity=template.fail_on_severity,
            max_critical=template.max_critical,
            max_high=template.max_high,
            max_medium=template.max_medium,
            fail_on_secrets=template.fail_on_secrets,
            fail_on_new_findings_only=template.fail_on_new_findings_only,
            allow_accepted_risks=template.allow_accepted_risks,
            allow_false_positives=template.allow_false_positives,
            is_default=set_as_default,
            is_active=True,
            created_by=request.user,
        )
        return Response(SecureWiseScanPolicySerializer(policy, context={"request": request}).data, status=201)

    def _unique_policy_name(self, org, base_name: str) -> str:
        if not SecureWiseScanPolicy.objects.filter(organization=org, name=base_name).exists():
            return base_name
        n = 2
        while SecureWiseScanPolicy.objects.filter(organization=org, name=f"{base_name} ({n})").exists():
            n += 1
        return f"{base_name} ({n})"


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

    def _require_write_membership(self, request, scan):
        membership = _membership(request.user, scan.organization)
        if membership is None or membership.role not in WRITE_ROLES:
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("You do not have permission to manage scans.")

    @action(detail=False, methods=["get"], url_path="worker-status")
    def worker_status(self, request):
        """Return tenant-scoped queue and execution metrics plus sanitized readiness."""
        organization_ids = _get_user_org_ids(request.user)
        if not organization_ids.exists():
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("Organization membership is required to view worker status.")
        is_org_admin = SecureWiseMembership.objects.filter(
            organization_id__in=organization_ids,
            user=request.user,
            role__in=ADMIN_ROLES,
        ).exists()
        now = timezone.now()
        recent_cutoff = now - timedelta(days=7)
        stale_cutoff = now - timedelta(minutes=30)
        scans = SecureWiseScan.objects.filter(organization_id__in=organization_ids)
        pentests = PentestSession.objects.filter(organization_id__in=organization_ids)
        active_scans = scans.filter(status__in=_SCAN_ACTIVE_STATUSES)
        active_pentests = pentests.filter(status__in=("worker_claimed", "running"))
        stale_jobs = active_scans.filter(worker_claimed_at__lt=stale_cutoff).count() + active_pentests.filter(
            worker_claimed_at__lt=stale_cutoff
        ).count()
        worker = SecureWiseWorkerRegistration.objects.filter(status="online").order_by("-last_seen_at").first()
        worker_available = bool(worker and worker.last_seen_at >= now - timedelta(seconds=45))
        capabilities = set(worker.capabilities if worker_available else ())
        engine_metrics = list(
            SecureWiseScanEngineResult.objects.filter(
                scan__organization_id__in=organization_ids,
                scan__created_at__gte=recent_cutoff,
            )
            .values("engine", "status")
            .annotate(count=Count("id"), average_duration_seconds=Avg("duration_seconds"))
            .order_by("engine", "status")
        )
        metrics = worker.metrics if worker_available and isinstance(worker.metrics, dict) else {}
        return Response(
            {
                "worker_available": worker_available,
                "docker_ready": "docker_daemon" in capabilities,
                "capabilities": sorted(capabilities),
                "heartbeat_age_seconds": (
                    max(0, int((now - worker.last_seen_at).total_seconds())) if worker_available else None
                ),
                "resources": {
                    key: metrics[key]
                    for key in (
                        "vmrss_kb",
                        "vmhwm_kb",
                        "temp_disk_free_bytes",
                        "temp_disk_total_bytes",
                        "load_average_1m",
                    )
                    if key in metrics
                } if is_org_admin else {},
                "queue": {
                    "queued_scans": scans.filter(status="queued").count(),
                    "queued_pentests": pentests.filter(status="queued").count(),
                    "stale_jobs": stale_jobs,
                    "failed_scans": scans.filter(status="failed", created_at__gte=recent_cutoff).count(),
                    "failed_pentests": pentests.filter(status="failed", created_at__gte=recent_cutoff).count(),
                    "average_scan_duration_seconds": scans.filter(
                        status__in=("completed", "completed_with_warnings", "completed_partial"),
                        duration_seconds__isnull=False,
                        completed_at__gte=recent_cutoff,
                    ).aggregate(value=Avg("duration_seconds"))["value"],
                },
                "engine_executions_last_7_days": engine_metrics,
            }
        )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    @action(detail=True, methods=["post"])
    def start(self, request, pk=None):
        scan = self.get_object()
        self._require_write_membership(request, scan)
        if scan.status not in ("pending", "failed"):
            return Response(
                {"detail": f"Cannot start a scan with status '{scan.status}'."},
                status=400,
            )
        scan.status = "queued"
        scan.save(update_fields=["status"])
        serializer = self.get_serializer(scan)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        scan = self.get_object()
        self._require_write_membership(request, scan)
        if scan.status not in ("pending", "queued", "worker_claimed") and not scan.status.startswith("running"):
            return Response(
                {"detail": f"Cannot cancel a scan with status '{scan.status}'."},
                status=400,
            )
        scan.status = "cancelled"
        scan.worker_claimed_at = None
        scan.save(update_fields=["status", "worker_claimed_at"])
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
        self._require_write_membership(request, scan)
        if scan.status not in ("failed", "cancelled", "completed_with_warnings", "completed", "completed_partial"):
            return Response(
                {"detail": f"Cannot retry a scan with status '{scan.status}'."},
                status=400,
            )
        scan.engine_results.all().delete()
        scan.status = "queued"
        scan.worker_claimed_at = None
        scan.progress = 0
        scan.error_message = ""
        scan.started_at = None
        scan.completed_at = None
        scan.duration_seconds = None
        scan.quality_gate_passed = None
        scan.save(
            update_fields=[
                "status",
                "worker_claimed_at",
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
        serializer = self.get_serializer(scan)
        return Response(serializer.data)

    @action(detail=True, methods=["get"])
    def progress(self, request, pk=None):
        scan = self.get_object()
        elapsed_seconds = None
        if scan.started_at:
            end = scan.completed_at or timezone.now()
            elapsed_seconds = int((end - scan.started_at).total_seconds())
        results = list(scan.engine_results.all())
        engines = []
        for er in results:
            raw_summary = er.raw_summary or {}
            log_excerpt = (
                raw_summary.get("dast_runtime_logs")
                or raw_summary.get("stdout")
                or raw_summary.get("stderr")
                or er.error_message
                or er.skipped_reason
                or ""
            )
            engines.append(
                {
                    "engine": er.engine,
                    "status": er.status,
                    "findings_count": er.findings_count,
                    "skipped_reason": er.skipped_reason,
                    "diagnostics": {
                        "log_excerpt": redact_secrets(tail_lines(str(log_excerpt), max_lines=80))[:4000],
                        "mode": raw_summary.get("mode", ""),
                        "execution_mode": raw_summary.get("execution_mode", ""),
                        "coverage": raw_summary.get("coverage", {}),
                    },
                }
            )
        coverage = {
            "requested_engines": len(scan.selected_engines or []),
            "completed_engines": sum(er.status == "completed" for er in results),
            "skipped_engines": sum(er.status == "skipped" for er in results),
            "failed_engines": sum(er.status == "failed" for er in results),
            "total_findings": scan.findings.count(),
        }
        worker = SecureWiseWorkerRegistration.objects.order_by("-last_seen_at").first()
        worker_available = bool(
            worker and worker.status == "online" and worker.last_seen_at >= timezone.now() - timedelta(seconds=45)
        )
        capabilities = set(worker.capabilities if worker_available else ())
        readiness_diagnostics = []
        if not worker_available:
            readiness_diagnostics.append(
                "No worker has checked in within the last 45 seconds."
                if worker
                else "No SecureWise worker has registered."
            )
        else:
            if "docker_daemon" not in capabilities:
                readiness_diagnostics.append("Docker daemon is unavailable on the worker.")
            if "trivy" not in capabilities:
                readiness_diagnostics.append("Trivy is not installed on the worker.")
            if not {"zap_baseline_cli", "zap_baseline_docker"} & capabilities:
                readiness_diagnostics.append("Neither ZAP baseline nor Docker-based ZAP is available.")
        worker_readiness = {
            "worker_available": worker_available,
            "docker_ready": "docker_daemon" in capabilities,
            "trivy_available": "trivy" in capabilities,
            "zap_available": bool({"zap_baseline_cli", "zap_baseline_docker"} & capabilities),
            "worker_id": worker.worker_id if worker_available else "",
            "last_seen_at": worker.last_seen_at.isoformat() if worker else None,
            "diagnostics": readiness_diagnostics,
        }
        return Response(
            {
                "id": str(scan.id),
                "status": scan.status,
                "progress": scan.progress,
                "elapsed_seconds": elapsed_seconds,
                "findings_count": scan.findings.count(),
                "coverage": coverage,
                "worker_readiness": worker_readiness,
                "engines": engines,
            }
        )

    @action(detail=True, methods=["get"], url_path="engine-results")
    def engine_results(self, request, pk=None):
        scan = self.get_object()
        serializer = ScanEngineResultSerializer(scan.engine_results.all(), many=True)
        return Response(serializer.data)


class PentestSessionViewSet(viewsets.ModelViewSet):
    serializer_class = PentestSessionSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        return (
            PentestSession.objects.filter(organization_id__in=_get_user_org_ids(self.request.user))
            .select_related("organization", "project", "repository", "created_by")
            .prefetch_related("scope", "test_cases__executions__evidence", "proposals")
        )

    def perform_create(self, serializer):
        project = serializer.validated_data["project"]
        membership = _membership(self.request.user, project.organization)
        if membership is None or membership.role not in WRITE_ROLES:
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("You do not have permission to create AutoPentest sessions.")
        session = serializer.save()
        _audit(
            self.request.user,
            "pentest_session_created",
            org=session.organization,
            target_type="PentestSession",
            target_id=session.id,
            detail={"repository": session.repository.name, "mode": session.mode},
            request=self.request,
        )

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        session = self.get_object()
        membership = _membership(request.user, session.organization)
        if membership is None or membership.role not in WRITE_ROLES:
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("You do not have permission to cancel AutoPentest sessions.")
        if session.status not in ("pending", "queued", "worker_claimed", "running"):
            return Response({"detail": f"Cannot cancel a session with status '{session.status}'."}, status=400)
        session.status = "cancelled"
        session.worker_claimed_at = None
        session.save(update_fields=["status", "worker_claimed_at"])
        if session.unified_scan_id:
            SecureWiseScan.objects.filter(
                id=session.unified_scan_id,
                status__in=("queued", "worker_claimed", "running", "running_api"),
            ).update(status="cancelled", worker_claimed_at=None, completed_at=timezone.now())
        return Response({"detail": "AutoPentest session cancelled.", "status": session.status})

    @action(detail=True, methods=["post"], url_path="execute-approved")
    def execute_approved(self, request, pk=None):
        session = self.get_object()
        membership = _membership(request.user, session.organization)
        if membership is None or membership.role not in WRITE_ROLES:
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("You do not have permission to execute AutoPentest proposals.")
        if session.mode != "security_planning" or session.status not in {"completed", "completed_with_warnings"}:
            return Response({"detail": "Only a completed planning session can execute approved tests."}, status=400)
        approved = session.proposals.filter(approval_status="approved", executable=True)
        if not approved.exists():
            return Response({"detail": "Approve at least one supported proposal before execution."}, status=400)
        session.mode = "approved_tests"
        session.status = "queued"
        session.progress = 0
        session.started_at = None
        session.completed_at = None
        session.worker_claimed_at = None
        session.error_message = ""
        session.save(
            update_fields=[
                "mode",
                "status",
                "progress",
                "started_at",
                "completed_at",
                "worker_claimed_at",
                "error_message",
                "updated_at",
            ]
        )
        _audit(
            request.user,
            "pentest_execution_queued",
            org=session.organization,
            target_type="PentestSession",
            target_id=session.id,
            detail={"approved_proposals": approved.count()},
            request=request,
        )
        return Response(PentestSessionSerializer(session, context={"request": request}).data, status=202)

    @action(detail=True, methods=["get"])
    def report(self, request, pk=None):
        session = self.get_object()
        cases = list(session.test_cases.all())
        proposal_counts = {
            outcome: session.proposals.filter(approval_status=outcome).count()
            for outcome in ("pending", "approved", "rejected", "unsupported", "executed")
        }
        counts = (
            {
                outcome: sum(case.status == outcome for case in cases)
                for outcome, _ in cases[0]._meta.get_field("status").choices
            }
            if cases
            else {}
        )
        return Response(
            {
                "session": PentestSessionSerializer(session, context={"request": request}).data,
                "summary": {
                    "test_cases": len(cases),
                    "outcomes": counts,
                    "proposals": proposal_counts,
                    "coverage": PentestSessionSerializer(session, context={"request": request}).data["coverage"],
                    "status": session.status,
                    "unified_findings_scan": str(session.unified_scan_id) if session.unified_scan_id else None,
                    "limitations": (
                        [
                            "This session performs passive OpenAPI contract checks only.",
                            "No application runtime, authenticated user flow, or active test was executed.",
                        ]
                        if session.mode == "passive"
                        else (
                            [
                                "This session inventoried static metadata and generated proposals only.",
                                "No proposal was executed during planning; human approval is required.",
                                "Inventory and AI annotations are not security findings or assurance.",
                            ]
                            if session.mode == "security_planning"
                            else [
                                "Only human-approved and supported proposals are eligible for execution.",
                                "Authenticated API requests are read-only and remain on the isolated repository runtime.",
                                "Browser tests execute only the selected fixed journeys using synthetic users.",
                                "Discovered route counts do not indicate security assurance; unsupported proposals remain unexecuted.",
                            ]
                        )
                    ),
                },
            }
        )


class PentestTestProposalViewSet(mixins.UpdateModelMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = PentestTestProposalSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "patch", "post", "head", "options"]

    def get_queryset(self):
        return PentestTestProposal.objects.filter(
            session__organization_id__in=_get_user_org_ids(self.request.user),
            session__mode="security_planning",
        ).select_related("session", "session__organization")

    def partial_update(self, request, *args, **kwargs):
        if set(request.data) != {"safe_parameters"}:
            return Response(
                {"detail": "Only planner-declared safe_parameters may be edited."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        proposal = self.get_object()
        self._require_write_membership(request, proposal)
        if proposal.approval_status != "pending":
            return Response({"detail": "Only pending proposals may be edited."}, status=400)
        serializer = self.get_serializer(proposal, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def _require_write_membership(self, request, proposal):
        membership = _membership(request.user, proposal.session.organization)
        if membership is None or membership.role not in WRITE_ROLES:
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("You do not have permission to review AutoPentest proposals.")

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        proposal = self.get_object()
        self._require_write_membership(request, proposal)
        if proposal.session.status not in {"completed", "completed_with_warnings"}:
            return Response({"detail": "Planning must finish before proposal review."}, status=400)
        if not proposal.executable or proposal.approval_status != "pending":
            return Response({"detail": "Only pending supported proposals can be approved."}, status=400)
        proposal.approval_status = "approved"
        proposal.approved_by = request.user
        proposal.approved_at = timezone.now()
        proposal.save(update_fields=["approval_status", "approved_by", "approved_at", "updated_at"])
        _audit(
            request.user,
            "pentest_proposal_approved",
            org=proposal.session.organization,
            target_type="PentestTestProposal",
            target_id=proposal.id,
            detail={"proposal_key": proposal.proposal_key},
            request=request,
        )
        return Response(self.get_serializer(proposal).data)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        proposal = self.get_object()
        self._require_write_membership(request, proposal)
        if proposal.session.status not in {"completed", "completed_with_warnings"}:
            return Response({"detail": "Planning must finish before proposal review."}, status=400)
        if proposal.approval_status != "pending":
            return Response({"detail": "Only pending proposals can be rejected."}, status=400)
        proposal.approval_status = "rejected"
        proposal.save(update_fields=["approval_status", "updated_at"])
        _audit(
            request.user,
            "pentest_proposal_rejected",
            org=proposal.session.organization,
            target_type="PentestTestProposal",
            target_id=proposal.id,
            detail={"proposal_key": proposal.proposal_key},
            request=request,
        )
        return Response(self.get_serializer(proposal).data)


# ---------------------------------------------------------------------------
# Finding
# ---------------------------------------------------------------------------


class FindingViewSet(viewsets.ModelViewSet):
    serializer_class = SecureWiseFindingSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "patch", "post", "head", "options"]

    def get_queryset(self):
        qs = SecureWiseFinding.objects.filter(organization_id__in=_get_user_org_ids(self.request.user)).select_related(
            "scan__repository", "project", "reviewed_by", "organization"
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

    def create(self, request, *args, **kwargs):
        return Response(
            {"detail": "Findings can only be created by a SecureWise scan execution."},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def perform_update(self, serializer):
        old_status = serializer.instance.status
        membership = _membership(self.request.user, serializer.instance.organization)
        if membership is None or membership.role not in WRITE_ROLES:
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("You do not have permission to update findings.")
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

    @action(detail=True, methods=["post"], url_path="ai-suggestion", throttle_classes=[AIRecommendationThrottle])
    def ai_suggestion(self, request, pk=None):
        finding = self.get_object()
        if _membership(request.user, finding.organization) is None:
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("You are not a member of this organization.")

        force = request.query_params.get("force", "").strip().lower() in {"1", "true", "yes"}
        if finding.ai_fix_suggestion and not force:
            try:
                cached_value = json.loads(finding.ai_fix_suggestion)
            except (TypeError, ValueError):
                cached_value = finding.ai_fix_suggestion
            return Response({"ai_fix_suggestion": cached_value, "cached": True})

        suggestion = generate_ai_fix_suggestion(finding)
        if suggestion is None:
            return Response(
                {
                    "ai_fix_suggestion": None,
                    "engine_unavailable": True,
                    "detail": "AI recommendation engine is not available right now.",
                }
            )

        finding.ai_fix_suggestion = json.dumps(suggestion)
        finding.save(update_fields=["ai_fix_suggestion", "updated_at"])
        _audit(
            request.user,
            "ai_suggestion_generated",
            org=finding.organization,
            target_type="SecureWiseFinding",
            target_id=finding.id,
            detail={"finding_id": str(finding.id), "confidence": suggestion["confidence"]},
            request=request,
        )
        return Response({"ai_fix_suggestion": suggestion, "cached": False})

    @action(detail=True, methods=["post"], url_path="create-ticket", throttle_classes=[GitHubActionThrottle])
    def create_ticket(self, request, pk=None):
        finding = self.get_object()
        if _membership(request.user, finding.organization) is None:
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("You are not a member of this organization.")

        try:
            ticket_url = create_github_issue(finding)
        except GitHubActionError as exc:
            _audit(
                request.user,
                "finding_ticket_failed",
                org=finding.organization,
                target_type="SecureWiseFinding",
                target_id=finding.id,
                detail={"error": str(exc)},
                request=request,
            )
            return Response({"detail": str(exc)}, status=400)

        finding.ticket_url = ticket_url
        finding.ticket_created_at = timezone.now()
        finding.save(update_fields=["ticket_url", "ticket_created_at", "updated_at"])
        _audit(
            request.user,
            "finding_ticket_created",
            org=finding.organization,
            target_type="SecureWiseFinding",
            target_id=finding.id,
            detail={"ticket_url": ticket_url},
            request=request,
        )
        return Response({"ticket_url": ticket_url})

    @action(detail=True, methods=["post"], url_path="create-pr", throttle_classes=[GitHubActionThrottle])
    def create_pr(self, request, pk=None):
        finding = self.get_object()
        if _membership(request.user, finding.organization) is None:
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("You are not a member of this organization.")

        try:
            pr_url = create_github_pr(finding)
        except GitHubActionError as exc:
            _audit(
                request.user,
                "finding_pr_failed",
                org=finding.organization,
                target_type="SecureWiseFinding",
                target_id=finding.id,
                detail={"error": str(exc)},
                request=request,
            )
            return Response({"detail": str(exc)}, status=400)

        finding.pr_url = pr_url
        finding.pr_created_at = timezone.now()
        finding.save(update_fields=["pr_url", "pr_created_at", "updated_at"])
        _audit(
            request.user,
            "finding_pr_created",
            org=finding.organization,
            target_type="SecureWiseFinding",
            target_id=finding.id,
            detail={"pr_url": pr_url},
            request=request,
        )
        return Response({"pr_url": pr_url})

    @action(detail=True, methods=["post"], url_path="accept-risk")
    def accept_risk(self, request, pk=None):
        finding = self.get_object()
        membership = _membership(request.user, finding.organization)
        if membership is None or membership.role not in WRITE_ROLES:
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("You do not have permission to change finding status.")
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
        membership = _membership(request.user, finding.organization)
        if membership is None or membership.role not in WRITE_ROLES:
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("You do not have permission to change finding status.")
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

    @action(detail=True, methods=["get"], url_path="html")
    def html(self, request, pk=None):
        report = self.get_object()
        if report.status != "ready":
            return Response({"detail": "Report is not ready yet."}, status=400)
        return HttpResponse(render_report_html(report), content_type="text/html")

    @action(detail=True, methods=["get"], url_path="pdf")
    def pdf(self, request, pk=None):
        report = self.get_object()
        if report.status != "ready":
            return Response({"detail": "Report is not ready yet."}, status=400)
        pdf_bytes = render_report_pdf(report)
        safe_title = slugify(report.title) or "securewise-report"
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{safe_title}.pdf"'
        return response


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

    def perform_update(self, serializer):
        integration = serializer.instance
        membership = _membership(self.request.user, integration.organization)
        if membership is None or membership.role not in ADMIN_ROLES:
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("Only org admins can manage integrations.")
        organization = serializer.validated_data.get("organization", integration.organization)
        if organization.id != integration.organization_id:
            from rest_framework.exceptions import ValidationError

            raise ValidationError({"organization": "Integrations cannot be moved to another organization."})
        serializer.save()

    def perform_destroy(self, instance):
        membership = _membership(self.request.user, instance.organization)
        if membership is None or membership.role not in ADMIN_ROLES:
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("Only org admins can manage integrations.")
        instance.delete()


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

        # Coverage across open findings uses the versioned taxonomy dataset.
        from .services.report import _CWE_TOP25, _OWASP_TOP10_LABELS

        owasp_coverage = {code: findings_qs.filter(owasp_category=code).count() for code in _OWASP_TOP10_LABELS}
        cwe_ids_covered = list(
            findings_qs.filter(cwe_id__in=list(_CWE_TOP25)).values_list("cwe_id", flat=True).distinct()
        )

        # Quality gate pass/fail counts across recent scans
        recent_scan_qs = SecureWiseScan.objects.filter(organization_id__in=org_ids, quality_gate_passed__isnull=False)
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
                "cwe_ids_covered": cwe_ids_covered,
                "cwe_coverage": SECURITY_TAXONOMY["cwe_coverage"],
                "security_taxonomy": taxonomy_metadata(),
                "quality_gate_counts": quality_gate_counts,
            }
        )
