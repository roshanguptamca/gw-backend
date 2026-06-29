from django.db import transaction
from django.db.models import F

from rest_framework.exceptions import PermissionDenied, ValidationError

from .anonymous_identity import resolve_anonymous_identity
from .models import Resume

ANONYMOUS_MAX_RESUMES = 1
ANONYMOUS_MAX_EDITS = 10
REGISTERED_MAX_RESUMES = 3
ANON_CREATE_ERROR = "Anonymous users can create only 1 resume. Please create an account to save up to 3 resumes."
ANON_EDIT_ERROR = "Anonymous resume edit limit reached. Please create an account to continue editing."
USER_CREATE_ERROR = "Free accounts can create up to 3 resumes."


def active_resume_count(*, user=None, identity=None):
    queryset = Resume.objects.filter(is_archived=False)
    if user and user.is_authenticated:
        return queryset.filter(user=user).count()
    return queryset.filter(anonymous_identity=identity).count()


def can_create_resume(request, email=None, phone=None):
    if request.user.is_authenticated:
        if active_resume_count(user=request.user) >= REGISTERED_MAX_RESUMES:
            raise ValidationError({"error": USER_CREATE_ERROR, "code": "REGISTERED_RESUME_LIMIT"})
        return None
    identity = resolve_anonymous_identity(request, email=email, phone_number=phone)
    if active_resume_count(identity=identity) >= ANONYMOUS_MAX_RESUMES:
        raise ValidationError({"error": ANON_CREATE_ERROR, "code": "ANONYMOUS_RESUME_LIMIT"})
    return identity


def can_edit_resume(resume, request):
    if resume.user_id:
        if not request.user.is_authenticated or resume.user_id != request.user.id:
            raise PermissionDenied("You do not have access to this resume.")
        return
    request_data = getattr(request, "data", {})
    identity = resolve_anonymous_identity(
        request,
        email=request_data.get("email"),
        phone_number=request_data.get("phone"),
        create=False,
    )
    if not identity or resume.anonymous_identity_id != identity.id:
        raise PermissionDenied("You do not have access to this resume.")
    if resume.edit_count >= resume.max_edit_count:
        raise ValidationError({"error": ANON_EDIT_ERROR, "code": "ANONYMOUS_EDIT_LIMIT"})


@transaction.atomic
def increment_resume_edit_count(resume, request):
    if resume.user_id:
        return resume
    locked = Resume.objects.select_for_update().get(pk=resume.pk)
    can_edit_resume(locked, request)
    Resume.objects.filter(pk=locked.pk).update(edit_count=F("edit_count") + 1)
    locked.refresh_from_db(fields=["edit_count"])
    resume.edit_count = locked.edit_count
    return locked


def request_identity(request, create=False):
    if request.user.is_authenticated:
        return None
    return resolve_anonymous_identity(request, create=create)


def owned_resumes(request):
    if request.user.is_authenticated:
        return Resume.objects.filter(user=request.user, is_archived=False)
    identity = request_identity(request, create=False)
    return Resume.objects.filter(anonymous_identity=identity, is_archived=False) if identity else Resume.objects.none()


def get_owned_resume(request, **lookup):
    from django.shortcuts import get_object_or_404

    return get_object_or_404(owned_resumes(request), **lookup)


def usage_for_request(request, resume=None):
    if request.user.is_authenticated:
        return {
            "is_anonymous": False,
            "resume_count": active_resume_count(user=request.user),
            "max_resumes": REGISTERED_MAX_RESUMES,
        }
    identity = resume.anonymous_identity if resume and resume.anonymous_identity_id else request_identity(request)
    count = active_resume_count(identity=identity) if identity else 0
    edit_count = resume.edit_count if resume else 0
    max_edits = resume.max_edit_count if resume else ANONYMOUS_MAX_EDITS
    return {
        "is_anonymous": True,
        "resume_count": count,
        "max_resumes": ANONYMOUS_MAX_RESUMES,
        "edit_count": edit_count,
        "max_edits": max_edits,
        "remaining_edits": max(max_edits - edit_count, 0),
    }


def data_changes(instance, validated_data):
    if instance is None:
        return bool(validated_data)
    return any(getattr(instance, key) != value for key, value in validated_data.items())
