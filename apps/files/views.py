from django.http import Http404, HttpResponse
from django.utils import timezone

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny

from apps.resumes.anonymous_identity import resolve_anonymous_identity

from .models import UserFile


@extend_schema(responses={(200, "application/octet-stream"): OpenApiTypes.BINARY})
@api_view(["GET"])
@permission_classes([AllowAny])
def download(request, file_id):
    owner_filter = (
        {"user": request.user}
        if request.user.is_authenticated
        else {"anonymous_identity": resolve_anonymous_identity(request, create=False)}
    )
    try:
        user_file = UserFile.objects.get(id=file_id, **owner_filter)
    except UserFile.DoesNotExist as exc:
        raise Http404 from exc
    if user_file.expires_at and user_file.expires_at <= timezone.now():
        raise Http404
    response = HttpResponse(bytes(user_file.file_data), content_type=user_file.content_type)
    response["Content-Disposition"] = f'attachment; filename="{user_file.filename}"'
    response["Content-Length"] = user_file.file_size
    response["X-Content-Type-Options"] = "nosniff"
    return response
