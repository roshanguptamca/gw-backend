"""Organization-scoped registration and approval APIs for passive URL scans."""

from __future__ import annotations

import hashlib
import ipaddress
import logging
from datetime import datetime, timedelta
from urllib.parse import urlsplit

from django.utils import timezone
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    SecureWiseApplicationTarget,
    SecureWiseMembership,
    SecureWiseOwnershipChallenge,
    SecureWiseProject,
    SecureWiseTestingAuthorization,
)
from .permissions import ADMIN_ROLES, WRITE_ROLES, _membership
from .services import url_security
from .views import _audit, _get_user_org_ids, _parse_uuid

logger = logging.getLogger(__name__)


def _target_payload(target):
    return {
        "id": str(target.id),
        "organization": str(target.organization_id),
        "project": str(target.project_id),
        "url": f"{target.scheme}://{target.hostname}:{target.port}{target.base_path}",
        "hostname": target.hostname,
        "port": target.port,
        "base_path": target.base_path,
        "verified": target.verified_at is not None and target.ownership_revoked_at is None,
        "verified_at": target.verified_at,
        "ownership_revoked_at": target.ownership_revoked_at,
        "created_at": target.created_at,
    }


def _authorization_payload(authorization):
    return {
        "id": str(authorization.id),
        "organization": str(authorization.organization_id),
        "target": str(authorization.target_id),
        "authorized_hosts": authorization.authorized_hosts,
        "allowed_ports": authorization.allowed_ports,
        "allowed_paths": authorization.allowed_paths,
        "excluded_paths": authorization.excluded_paths,
        "approved_scan_methods": authorization.approved_scan_methods,
        "testing_environment": authorization.testing_environment,
        "starts_at": authorization.starts_at,
        "expires_at": authorization.expires_at,
        "approved_by": authorization.approved_by_id,
        "revoked_at": authorization.revoked_at,
        "active": url_security.authorization_is_active(authorization),
    }


def _challenge_payload(challenge, token, hostname):
    return {
        "id": str(challenge.id),
        "method": challenge.method,
        "token": token,
        "expires_at": challenge.expires_at,
        "dns_name": f"_securewise-verification.{hostname}",
        "https_path": "/.well-known/securewise-verification.txt",
    }


def _create_challenge(target, method):
    if method not in {"dns_txt", "https_well_known"}:
        raise ValueError("Choose dns_txt or https_well_known verification.")
    token, digest = url_security.create_challenge_token()
    challenge = SecureWiseOwnershipChallenge.objects.create(
        target=target,
        method=method,
        challenge_digest=digest,
        expires_at=timezone.now() + timedelta(hours=24),
    )
    return challenge, token


def _scope_paths(value, default, *, allow_empty=False):
    if value is None:
        value = default
    if allow_empty and value == []:
        return []
    if not isinstance(value, list) or not value or len(value) > 50:
        raise ValueError("Provide between 1 and 50 explicit absolute path prefixes.")
    result = []
    for path in value:
        if not isinstance(path, str) or "?" in path or "#" in path or "*" in path:
            raise ValueError("Scope paths must be literal paths without query, fragment, or wildcard.")
        normalized = url_security.normalize_request_path(path)
        normalized = normalized.rstrip("/") or "/"
        if normalized not in result:
            result.append(normalized)
    return result


class ApplicationTargetView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        targets = SecureWiseApplicationTarget.objects.filter(
            organization_id__in=_get_user_org_ids(request.user)
        ).order_by("hostname")
        return Response([_target_payload(target) for target in targets])

    def post(self, request):
        from rest_framework.exceptions import PermissionDenied

        project_id = _parse_uuid(request.data.get("project"))
        if project_id is None:
            return Response({"detail": "A valid project is required."}, status=400)
        project = (
            SecureWiseProject.objects.filter(
                id=project_id,
                organization_id__in=_get_user_org_ids(request.user),
            )
            .select_related("organization")
            .first()
        )
        if project is None:
            return Response({"detail": "Project not found."}, status=404)
        membership = _membership(request.user, project.organization)
        if membership is None or membership.role not in WRITE_ROLES:
            raise PermissionDenied("You do not have permission to register targets in this organization.")
        try:
            scheme, hostname, port, base_path = url_security.parse_https_url(request.data.get("url", ""))
            parsed = urlsplit(request.data["url"])
            if parsed.query or parsed.fragment:
                raise url_security.URLSecurityError("Target registration URLs cannot include query or fragment values.")
            try:
                ipaddress.ip_address(hostname)
            except ValueError:
                pass
            else:
                raise url_security.URLSecurityError("Register a DNS hostname, not an IP address.")
        except (KeyError, url_security.URLSecurityError) as exc:
            return Response({"detail": str(exc)}, status=400)
        target, created = SecureWiseApplicationTarget.objects.get_or_create(
            organization=project.organization,
            hostname=hostname,
            port=port,
            defaults={
                "project": project,
                "scheme": scheme,
                "base_path": base_path,
                "created_by": request.user,
            },
        )
        if not created and target.project_id != project.id:
            return Response({"detail": "This hostname is already registered to another project."}, status=409)
        try:
            challenge, token = _create_challenge(target, request.data.get("verification_method", "dns_txt"))
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        _audit(
            request.user,
            "application_target_registered",
            org=project.organization,
            target_type="SecureWiseApplicationTarget",
            target_id=target.id,
            detail={"hostname": hostname, "created": created},
            request=request,
        )
        _audit(
            request.user,
            "application_target_challenge_created",
            org=project.organization,
            target_type="SecureWiseOwnershipChallenge",
            target_id=challenge.id,
            detail={"method": challenge.method, "expires_at": challenge.expires_at.isoformat()},
            request=request,
        )
        return Response(
            {"target": _target_payload(target), "challenge": _challenge_payload(challenge, token, hostname)},
            status=201 if created else 200,
        )


class ApplicationTargetActionView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, target_id, action):
        from rest_framework.exceptions import PermissionDenied

        target_uuid = _parse_uuid(target_id)
        target = (
            SecureWiseApplicationTarget.objects.filter(
                id=target_uuid,
                organization_id__in=_get_user_org_ids(request.user),
            )
            .select_related("organization", "project")
            .first()
        )
        if target is None:
            return Response({"detail": "Target not found."}, status=404)
        membership = _membership(request.user, target.organization)
        if membership is None or membership.role not in ADMIN_ROLES:
            raise PermissionDenied("Organization admin approval is required.")

        if action == "challenge":
            try:
                challenge, token = _create_challenge(target, request.data.get("verification_method", "dns_txt"))
            except ValueError as exc:
                return Response({"detail": str(exc)}, status=400)
            _audit(
                request.user,
                "application_target_challenge_created",
                org=target.organization,
                target_type="SecureWiseOwnershipChallenge",
                target_id=challenge.id,
                detail={"method": challenge.method, "expires_at": challenge.expires_at.isoformat()},
                request=request,
            )
            return Response(_challenge_payload(challenge, token, target.hostname), status=201)

        if action == "verify":
            challenge_id = _parse_uuid(request.data.get("challenge"))
            challenge = SecureWiseOwnershipChallenge.objects.filter(
                id=challenge_id,
                target=target,
                verified_at__isnull=True,
                expires_at__gt=timezone.now(),
            ).first()
            if challenge is None:
                return Response({"detail": "Ownership challenge is invalid, expired, or already used."}, status=400)
            try:
                import dns.exception

                url_security.resolve_public_addresses(target.hostname)
                if challenge.method == "dns_txt":
                    verified = url_security.verify_dns_txt(target.hostname, challenge.challenge_digest)
                else:
                    verified = url_security.verify_https_well_known(
                        target.hostname, challenge.challenge_digest, port=target.port
                    )
            except (dns.exception.DNSException, OSError, url_security.URLSecurityError) as exc:
                logger.warning("Ownership verification failed for target %s: %s", target.id, exc)
                verified = False
            if not verified:
                return Response({"detail": "Ownership challenge could not be verified."}, status=400)
            challenge.verified_at = timezone.now()
            challenge.save(update_fields=["verified_at"])
            target.verified_at = challenge.verified_at
            target.ownership_revoked_at = None
            target.save(update_fields=["verified_at", "ownership_revoked_at", "updated_at"])
            _audit(
                request.user,
                "application_target_verified",
                org=target.organization,
                target_type="SecureWiseApplicationTarget",
                target_id=target.id,
                detail={"method": challenge.method},
                request=request,
            )
            return Response(_target_payload(target))

        if action == "revoke-ownership":
            now = timezone.now()
            target.ownership_revoked_at = now
            target.save(update_fields=["ownership_revoked_at", "updated_at"])
            SecureWiseTestingAuthorization.objects.filter(target=target, revoked_at__isnull=True).update(revoked_at=now)
            _audit(
                request.user,
                "testing_authorization_revoked",
                org=target.organization,
                target_type="SecureWiseApplicationTarget",
                target_id=target.id,
                detail={"reason": "ownership_revoked"},
                request=request,
            )
            return Response(_target_payload(target))

        if action == "authorize":
            return self._authorize(request, target)
        return Response({"detail": "Unknown target action."}, status=404)

    def _authorize(self, request, target):
        if target.verified_at is None or target.ownership_revoked_at is not None:
            return Response({"detail": "Verify current ownership before approving testing."}, status=400)
        if request.data.get("explicit_authorization") is not True:
            return Response({"detail": "Explicit testing authorization is required."}, status=400)
        environment = request.data.get("testing_environment")
        if environment not in {"production", "staging", "test"}:
            return Response({"detail": "Choose a testing environment."}, status=400)
        expiry_value = request.data.get("expires_at")
        try:
            expires_at = datetime.fromisoformat(expiry_value) if isinstance(expiry_value, str) else None
        except ValueError:
            expires_at = None
        now = timezone.now()
        if expires_at is None or timezone.is_naive(expires_at):
            return Response({"detail": "Provide an ISO-8601 expiry with timezone."}, status=400)
        if expires_at <= now or expires_at > now + timedelta(days=30):
            return Response({"detail": "Authorization expiry must be within the next 30 days."}, status=400)
        try:
            allowed_paths = _scope_paths(request.data.get("allowed_paths"), [target.base_path])
            excluded_paths = _scope_paths(request.data.get("excluded_paths", []), [], allow_empty=True)
        except (ValueError, url_security.URLSecurityError) as exc:
            return Response({"detail": str(exc)}, status=400)
        if not url_security.path_is_allowed(target.base_path, allowed_paths, excluded_paths):
            return Response({"detail": "The registered target path must be within the approved scope."}, status=400)
        authorization = SecureWiseTestingAuthorization.objects.create(
            organization=target.organization,
            target=target,
            authorized_hosts=[target.hostname],
            allowed_ports=[target.port],
            allowed_paths=allowed_paths,
            excluded_paths=excluded_paths,
            approved_scan_methods=["passive_http"],
            testing_environment=environment,
            starts_at=now,
            expires_at=expires_at,
            approved_by=request.user,
        )
        _audit(
            request.user,
            "testing_authorization_approved",
            org=target.organization,
            target_type="SecureWiseTestingAuthorization",
            target_id=authorization.id,
            detail={"hostname": target.hostname, "methods": ["passive_http"]},
            request=request,
        )
        return Response(_authorization_payload(authorization), status=201)


class TestingAuthorizationView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        authorizations = SecureWiseTestingAuthorization.objects.filter(
            organization_id__in=_get_user_org_ids(request.user)
        ).select_related("target", "approved_by")
        return Response([_authorization_payload(item) for item in authorizations])

    def post(self, request, authorization_id):
        from rest_framework.exceptions import PermissionDenied

        auth_uuid = _parse_uuid(authorization_id)
        authorization = (
            SecureWiseTestingAuthorization.objects.filter(
                id=auth_uuid,
                organization_id__in=_get_user_org_ids(request.user),
            )
            .select_related("target", "organization")
            .first()
        )
        if authorization is None:
            return Response({"detail": "Authorization not found."}, status=404)
        membership = _membership(request.user, authorization.organization)
        if membership is None or membership.role not in ADMIN_ROLES:
            raise PermissionDenied("Organization admin approval is required.")
        if authorization.revoked_at is None:
            authorization.revoked_at = timezone.now()
            authorization.save(update_fields=["revoked_at"])
            _audit(
                request.user,
                "testing_authorization_revoked",
                org=authorization.organization,
                target_type="SecureWiseTestingAuthorization",
                target_id=authorization.id,
                request=request,
            )
        return Response(_authorization_payload(authorization))
