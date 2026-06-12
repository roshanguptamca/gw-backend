import hashlib
import re

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import AnonymousResumeIdentity


def normalize_email(value):
    return (value or "").strip().casefold() or None


def normalize_phone(value):
    raw = (value or "").strip()
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw)
    return f"+{digits}" if digits else None


def get_client_ip(request):
    # Django only exposes proxy-derived REMOTE_ADDR when the deployment has been
    # configured to trust its proxy. Do not trust arbitrary X-Forwarded-For here.
    return request.META.get("REMOTE_ADDR") or None


def _hash(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest() if value else None


def _ensure_session_key(request):
    if not request.session.session_key:
        request.session.create()
    return request.session.session_key


def _merge_identities(primary, duplicates):
    from apps.files.models import UserFile
    from apps.jobs.models import ATSReport, JobDescription, JobMatch, TemporaryJobDescription
    from apps.resumes.models import (
        OptimizedResume,
        Resume,
        ResumeUpload,
        TemporaryGeneratedResume,
        TemporaryResumeUpload,
    )

    duplicate_ids = [item.id for item in duplicates]
    if not duplicate_ids:
        return primary
    Resume.objects.filter(anonymous_identity_id__in=duplicate_ids).update(anonymous_identity=primary)
    ResumeUpload.objects.filter(anonymous_identity_id__in=duplicate_ids).update(anonymous_identity=primary)
    TemporaryGeneratedResume.objects.filter(anonymous_identity_id__in=duplicate_ids).update(anonymous_identity=primary)
    TemporaryResumeUpload.objects.filter(anonymous_identity_id__in=duplicate_ids).update(anonymous_identity=primary)
    OptimizedResume.objects.filter(anonymous_identity_id__in=duplicate_ids).update(anonymous_identity=primary)
    UserFile.objects.filter(anonymous_identity_id__in=duplicate_ids).update(anonymous_identity=primary)
    JobDescription.objects.filter(anonymous_identity_id__in=duplicate_ids).update(anonymous_identity=primary)
    TemporaryJobDescription.objects.filter(anonymous_identity_id__in=duplicate_ids).update(anonymous_identity=primary)
    JobMatch.objects.filter(anonymous_identity_id__in=duplicate_ids).update(anonymous_identity=primary)
    ATSReport.objects.filter(anonymous_identity_id__in=duplicate_ids).update(anonymous_identity=primary)
    AnonymousResumeIdentity.objects.filter(id__in=duplicate_ids).delete()
    return primary


@transaction.atomic
def resolve_anonymous_identity(request, email=None, phone_number=None, create=True):
    if request.user.is_authenticated:
        return None
    email = normalize_email(email)
    phone = normalize_phone(phone_number)
    session_key = _ensure_session_key(request) if create else request.session.session_key
    ip_address = get_client_ip(request)
    request_data = getattr(request, "data", {})
    fingerprint = request.headers.get("X-Resume-Fingerprint") or request_data.get("fingerprint_hash")
    fingerprint_hash = _hash(str(fingerprint)) if fingerprint else None
    user_agent_hash = _hash(request.META.get("HTTP_USER_AGENT", ""))

    query = Q()
    for key, value in (
        ("email", email),
        ("phone_number", phone),
        ("session_key", session_key),
        ("ip_address", ip_address),
        ("fingerprint_hash", fingerprint_hash),
    ):
        if value:
            query |= Q(**{key: value})
    queryset = AnonymousResumeIdentity.objects.filter(query).order_by("created_at") if query else None
    if queryset is None:
        matches = []
    else:
        matches = list(queryset.select_for_update() if create else queryset)
    if not matches and not create:
        return None
    identity = matches[0] if matches else AnonymousResumeIdentity()
    if not create:
        return identity
    if len(matches) > 1:
        identity = _merge_identities(identity, matches[1:])
    changed = []
    for field, value in (
        ("email", email),
        ("phone_number", phone),
        ("session_key", session_key),
        ("ip_address", ip_address),
        ("fingerprint_hash", fingerprint_hash),
        ("user_agent_hash", user_agent_hash),
    ):
        if value and not getattr(identity, field):
            setattr(identity, field, value)
            changed.append(field)
    identity.last_seen_at = timezone.now()
    changed.append("last_seen_at")
    identity.save(update_fields=changed if identity.pk else None)
    return identity
