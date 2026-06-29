import logging

from django.utils import timezone
from rest_framework import permissions

from .models import SecureWiseMembership, SecureWiseOrganization

logger = logging.getLogger(__name__)

WRITE_ROLES = {"owner", "admin", "security_engineer"}
ADMIN_ROLES = {"owner", "admin"}


def _get_org_from_obj(obj):
    """Best-effort extraction of the organization from any SecureWise object."""
    if isinstance(obj, SecureWiseOrganization):
        return obj
    return getattr(obj, "organization", None)


def _membership(user, org):
    if org is None or not user or not user.is_authenticated:
        return None
    return SecureWiseMembership.objects.filter(organization=org, user=user).first()


class IsSecureWiseMember(permissions.BasePermission):
    """User must be a member of the object's organization."""

    message = "You are not a member of this organization."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        org = _get_org_from_obj(obj)
        return _membership(request.user, org) is not None


class IsSecureWiseWriteMember(permissions.BasePermission):
    """User must have owner/admin/security_engineer role."""

    message = "You do not have write access to this organization."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        org = _get_org_from_obj(obj)
        m = _membership(request.user, org)
        if m is None:
            return False
        if request.method in permissions.SAFE_METHODS:
            return True
        return m.role in WRITE_ROLES


class IsSecureWiseAdmin(permissions.BasePermission):
    """User must have owner or admin role."""

    message = "You must be an organization owner or admin."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        org = _get_org_from_obj(obj)
        m = _membership(request.user, org)
        return m is not None and m.role in ADMIN_ROLES


class IsOrganizationOwnerOrAdmin(permissions.BasePermission):
    """For git integrations — only owner/admin can manage them."""

    message = "Only organization owners and admins can manage Git integrations."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        org = _get_org_from_obj(obj)
        if request.method in permissions.SAFE_METHODS:
            m = _membership(request.user, org)
            return m is not None
        m = _membership(request.user, org)
        return m is not None and m.role in ADMIN_ROLES
