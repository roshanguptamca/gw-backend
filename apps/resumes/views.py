import io

from django.conf import settings
from django.db import IntegrityError, transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from PIL import Image, UnidentifiedImageError
from rest_framework import status, viewsets
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from apps.exports.services import get_template_settings, render_resume_html, save_export
from apps.files.models import UserFile
from apps.templates_app.serializers import (
    PreviewTemplateSerializer,
    ResumeTemplateSerializer,
    SelectTemplateSerializer,
)

from .models import (
    Award,
    Certification,
    Education,
    PersonalDetail,
    Project,
    Reference,
    Resume,
    ResumeLanguage,
    ResumeUpload,
    Skill,
    WorkExperience,
)
from .serializers import (
    AwardSerializer,
    CertificationSerializer,
    EducationSerializer,
    PersonalDetailSerializer,
    ProjectSerializer,
    ReferenceSerializer,
    ResumeLanguageSerializer,
    ResumeSerializer,
    ResumeSummarySerializer,
    ResumeUploadSerializer,
    SkillSerializer,
    WorkExperienceSerializer,
)
from .services import apply_parsed_resume, create_version, parse_upload
from .anonymous_identity import resolve_anonymous_identity
from .limits import (
    active_resume_count,
    can_create_resume,
    can_edit_resume,
    data_changes,
    get_owned_resume,
    increment_resume_edit_count,
    owned_resumes,
    usage_for_request,
    REGISTERED_MAX_RESUMES,
)


class ResumeViewSet(viewsets.ModelViewSet):
    queryset = Resume.objects.all()
    serializer_class = ResumeSerializer
    permission_classes = [AllowAny]
    lookup_value_converter = "int"

    def get_queryset(self):
        return owned_resumes(self.request)

    def perform_create(self, serializer):
        email = self.request.data.get("owner_email") or self.request.data.get("email")
        phone = self.request.data.get("owner_phone") or self.request.data.get("phone")
        identity = can_create_resume(self.request, email=email, phone=phone)
        owner = (
            {"user": self.request.user, "source": "registered"}
            if self.request.user.is_authenticated
            else {"anonymous_identity": identity, "source": "anonymous"}
        )
        resume = serializer.save(**owner)
        create_version(resume)

    def perform_update(self, serializer):
        resume = serializer.instance
        changed = data_changes(resume, serializer.validated_data)
        if changed:
            can_edit_resume(resume, self.request)
        resume = serializer.save()
        if changed:
            increment_resume_edit_count(resume, self.request)
            create_version(resume)

    def perform_destroy(self, instance):
        can_edit_resume(instance, self.request)
        super().perform_destroy(instance)


@extend_schema(request=PersonalDetailSerializer, responses=PersonalDetailSerializer)
@api_view(["PUT"])
@permission_classes([AllowAny])
def update_personal(request, resume_id):
    resume = get_owned_resume(request, id=resume_id)
    instance = getattr(resume, "personal", None)
    serializer = PersonalDetailSerializer(instance, data=request.data)
    serializer.is_valid(raise_exception=True)
    changed = data_changes(instance, serializer.validated_data)
    if changed:
        can_edit_resume(resume, request)
    with transaction.atomic():
        personal = serializer.save(resume=resume)
        resume.include_photo = personal.include_photo
        resume.save(update_fields=["include_photo", "updated_at"])
        if changed:
            increment_resume_edit_count(resume, request)
            create_version(resume)
    return Response({**serializer.data, "usage": usage_for_request(request, resume)})


@extend_schema(request=ResumeSummarySerializer, responses=ResumeSummarySerializer)
@api_view(["PUT"])
@permission_classes([AllowAny])
def update_summary(request, resume_id):
    resume = get_owned_resume(request, id=resume_id)
    instance = getattr(resume, "summary", None)
    payload = request.data if "text" in request.data else {"text": request.data.get("summary", "")}
    serializer = ResumeSummarySerializer(instance, data=payload)
    serializer.is_valid(raise_exception=True)
    changed = data_changes(instance, serializer.validated_data)
    if changed:
        can_edit_resume(resume, request)
    with transaction.atomic():
        serializer.save(resume=resume)
        if changed:
            increment_resume_edit_count(resume, request)
            create_version(resume)
    return Response({**serializer.data, "usage": usage_for_request(request, resume)})


def create_section_view(model, serializer_class):
    @extend_schema(request=serializer_class, responses={201: serializer_class})
    @api_view(["POST"])
    @permission_classes([AllowAny])
    def view(request, resume_id):
        resume = get_owned_resume(request, id=resume_id)
        can_edit_resume(resume, request)
        serializer = serializer_class(data=request.data, context={"resume": resume, "request": request})
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                serializer.save(resume=resume)
                increment_resume_edit_count(resume, request)
                create_version(resume)
        except IntegrityError:
            messages = {
                Skill: "This skill is already added.",
                Education: "This education entry already exists.",
                WorkExperience: "This experience entry already exists.",
                Project: "This project is already added.",
            }
            return Response(
                {"error": messages.get(model, "This entry already exists.")}, status=status.HTTP_400_BAD_REQUEST
            )
        return Response(
            {**serializer.data, "usage": usage_for_request(request, resume)},
            status=status.HTTP_201_CREATED,
        )

    return view


create_experience = create_section_view(WorkExperience, WorkExperienceSerializer)
create_education = create_section_view(Education, EducationSerializer)
create_project = create_section_view(Project, ProjectSerializer)
create_skill = create_section_view(Skill, SkillSerializer)
create_certification = create_section_view(Certification, CertificationSerializer)
create_language = create_section_view(ResumeLanguage, ResumeLanguageSerializer)
create_award = create_section_view(Award, AwardSerializer)
create_reference = create_section_view(Reference, ReferenceSerializer)


SECTION_DETAILS = {
    "experiences": (WorkExperience, WorkExperienceSerializer),
    "education": (Education, EducationSerializer),
    "projects": (Project, ProjectSerializer),
    "skills": (Skill, SkillSerializer),
    "certifications": (Certification, CertificationSerializer),
    "languages": (ResumeLanguage, ResumeLanguageSerializer),
    "awards": (Award, AwardSerializer),
    "references": (Reference, ReferenceSerializer),
}


@extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
@api_view(["PUT", "DELETE"])
@permission_classes([AllowAny])
def section_detail(request, section, item_id):
    model, serializer_class = SECTION_DETAILS.get(section, (None, None))
    if not model:
        return Response({"error": "Unknown resume section."}, status=status.HTTP_404_NOT_FOUND)
    item = get_object_or_404(model, id=item_id, resume__in=owned_resumes(request))
    resume = item.resume
    if request.method == "DELETE":
        can_edit_resume(resume, request)
        with transaction.atomic():
            item.delete()
            increment_resume_edit_count(resume, request)
            create_version(resume)
        return Response(status=status.HTTP_204_NO_CONTENT)
    serializer = serializer_class(item, data=request.data, context={"resume": resume, "request": request})
    serializer.is_valid(raise_exception=True)
    changed = data_changes(item, serializer.validated_data)
    if changed:
        can_edit_resume(resume, request)
    try:
        with transaction.atomic():
            serializer.save()
            if changed:
                increment_resume_edit_count(resume, request)
                create_version(resume)
    except IntegrityError:
        messages = {
            Skill: "This skill is already added.",
            Education: "This education entry already exists.",
            WorkExperience: "This experience entry already exists.",
            Project: "This project is already added.",
        }
        return Response(
            {"error": messages.get(model, "This entry already exists.")}, status=status.HTTP_400_BAD_REQUEST
        )
    return Response({**serializer.data, "usage": usage_for_request(request, resume)})


@extend_schema(request=OpenApiTypes.BINARY, responses={201: PersonalDetailSerializer})
@api_view(["POST"])
@permission_classes([AllowAny])
@parser_classes([MultiPartParser, FormParser])
def resume_photo(request, resume_id):
    resume = get_owned_resume(request, id=resume_id)
    can_edit_resume(resume, request)
    uploaded = request.FILES.get("photo")
    if not uploaded:
        return Response({"error": "A photo file is required."}, status=status.HTTP_400_BAD_REQUEST)
    if uploaded.size > 5 * 1024 * 1024:
        return Response({"error": "Profile photo must be 5 MB or smaller."}, status=status.HTTP_400_BAD_REQUEST)
    content = uploaded.read()
    try:
        image = Image.open(io.BytesIO(content))
        image.verify()
        image_format = (image.format or "").upper()
    except (UnidentifiedImageError, OSError):
        return Response({"error": "Upload a valid JPG, PNG, or WebP image."}, status=status.HTTP_400_BAD_REQUEST)
    content_types = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}
    if image_format not in content_types:
        return Response(
            {"error": "Supported photo formats are JPG, PNG, and WebP."}, status=status.HTTP_400_BAD_REQUEST
        )
    personal, _ = PersonalDetail.objects.get_or_create(resume=resume)
    previous_file = personal.profile_photo
    user_file = UserFile.objects.create(
        user=resume.user,
        anonymous_identity=resume.anonymous_identity,
        filename=uploaded.name,
        content_type=content_types[image_format],
        file_size=len(content),
        file_data=content,
        purpose="resume_profile_photo",
    )
    personal.profile_photo = user_file
    personal.include_photo = True
    personal.save(update_fields=["profile_photo", "include_photo"])
    resume.include_photo = True
    resume.save(update_fields=["include_photo", "updated_at"])
    if previous_file:
        previous_file.delete()
    increment_resume_edit_count(resume, request)
    create_version(resume)
    return Response(
        {
            **PersonalDetailSerializer(personal, context={"request": request}).data,
            "usage": usage_for_request(request, resume),
        },
        status=status.HTTP_201_CREATED,
    )


@extend_schema(responses={(200, "image/*"): OpenApiTypes.BINARY})
@api_view(["GET", "DELETE"])
@permission_classes([AllowAny])
def resume_photo_detail(request, resume_id):
    resume = get_owned_resume(request, id=resume_id)
    personal = get_object_or_404(PersonalDetail, resume=resume, profile_photo__isnull=False)
    if request.method == "DELETE":
        can_edit_resume(resume, request)
        user_file = personal.profile_photo
        personal.profile_photo = None
        personal.include_photo = False
        personal.save(update_fields=["profile_photo", "include_photo"])
        resume.include_photo = False
        resume.save(update_fields=["include_photo", "updated_at"])
        user_file.delete()
        increment_resume_edit_count(resume, request)
        create_version(resume)
        return Response(status=status.HTTP_204_NO_CONTENT)
    user_file = personal.profile_photo
    response = HttpResponse(bytes(user_file.file_data), content_type=user_file.content_type)
    response["Content-Disposition"] = f'inline; filename="{user_file.filename}"'
    response["Cache-Control"] = "private, max-age=300"
    response["X-Content-Type-Options"] = "nosniff"
    return response


@extend_schema(request=OpenApiTypes.OBJECT, responses={201: ResumeUploadSerializer})
@api_view(["POST"])
@permission_classes([AllowAny])
@parser_classes([MultiPartParser, FormParser])
def upload_resume(request):
    uploaded_file = request.FILES.get("file")
    if not uploaded_file:
        return Response({"error": "A resume file is required."}, status=status.HTTP_400_BAD_REQUEST)
    extension = uploaded_file.name.rsplit(".", 1)[-1].lower()
    if extension not in {"pdf", "docx", "txt"}:
        return Response({"error": "Supported formats are PDF, DOCX, and TXT."}, status=status.HTTP_400_BAD_REQUEST)
    if uploaded_file.size > 10 * 1024 * 1024:
        return Response({"error": "Maximum upload size is 10 MB."}, status=status.HTTP_400_BAD_REQUEST)
    identity = (
        None
        if request.user.is_authenticated
        else resolve_anonymous_identity(
            request,
            email=request.data.get("email"),
            phone_number=request.data.get("phone"),
        )
    )
    upload = ResumeUpload.objects.create(
        user=request.user if request.user.is_authenticated else None,
        anonymous_identity=identity,
        filename=uploaded_file.name,
        content_type=uploaded_file.content_type or "",
        file_size=uploaded_file.size,
        file_data=uploaded_file.read(),
    )
    if settings.CAREER_SUITE_RUN_JOBS_INLINE:
        parse_upload(upload)
        upload.refresh_from_db()
    return Response(ResumeUploadSerializer(upload).data, status=status.HTTP_201_CREATED)


@extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
@api_view(["POST"])
@permission_classes([AllowAny])
def parse_resume(request):
    identity = None if request.user.is_authenticated else resolve_anonymous_identity(request, create=False)
    owner_filter = {"user": request.user} if request.user.is_authenticated else {"anonymous_identity": identity}
    upload = get_object_or_404(ResumeUpload, id=request.data.get("upload_id"), **owner_filter)
    parsed = upload.parsed_json if upload.status == "completed" else parse_upload(upload)
    response = {"upload_id": upload.id, "parsed_json": parsed}
    if request.data.get("create_resume"):
        identity = can_create_resume(
            request,
            email=request.data.get("email"),
            phone=request.data.get("phone"),
        )
        locale = request.data.get("locale", "en")
        if locale not in {"en", "nl"}:
            return Response({"locale": ["Language must be 'en' or 'nl'."]}, status=status.HTTP_400_BAD_REQUEST)
        resume = Resume.objects.create(
            user=request.user if request.user.is_authenticated else None,
            anonymous_identity=identity,
            source="registered" if request.user.is_authenticated else "anonymous",
            title=request.data.get("title") or f"Resume from {upload.filename}",
            locale=locale,
        )
        apply_parsed_resume(resume, parsed)
        response["resume"] = ResumeSerializer(resume, context={"request": request}).data
    return Response(response)


@extend_schema(request=SelectTemplateSerializer, responses=OpenApiTypes.OBJECT)
@api_view(["POST"])
@permission_classes([AllowAny])
def select_template(request, resume_id):
    resume = get_owned_resume(request, id=resume_id)
    serializer = SelectTemplateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    template = serializer.validated_data["template"]
    requested_settings = serializer.validated_data.get("template_settings", {})
    resolved_settings = {**(template.default_settings or {}), **requested_settings}
    include_photo = resolved_settings.get("include_photo", resume.include_photo)
    if not template.supports_photo:
        include_photo = False
        resolved_settings["include_photo"] = False
    unchanged = (
        resume.template_id == template.id
        and resume.template_settings == resolved_settings
        and resume.include_photo == include_photo
    )
    if not unchanged:
        can_edit_resume(resume, request)
    with transaction.atomic():
        if not unchanged:
            resume.template = template
            resume.template_settings = resolved_settings
            resume.include_photo = include_photo
            resume.save(update_fields=["template", "template_settings", "include_photo", "updated_at"])
        if hasattr(resume, "personal") and resume.personal.include_photo != include_photo:
            resume.personal.include_photo = include_photo
            resume.personal.save(update_fields=["include_photo"])
        if not unchanged:
            increment_resume_edit_count(resume, request)
            create_version(resume, source="template_selection")
    return Response(
        {
            "success": True,
            "resume_id": resume.id,
            "template": ResumeTemplateSerializer(template).data,
            "template_settings": get_template_settings(resume),
            "usage": usage_for_request(request, resume),
        }
    )


@extend_schema(request=PreviewTemplateSerializer, responses=OpenApiTypes.OBJECT)
@api_view(["POST"])
@permission_classes([AllowAny])
def preview_resume(request, resume_id):
    resume = get_owned_resume(request, id=resume_id)
    serializer = PreviewTemplateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    template = serializer.validated_data.get("template") or resume.template
    if not template:
        return Response(
            {"error": "Please select a resume template before generating your CV."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    settings_data = serializer.validated_data.get("template_settings", {})
    return Response({"html": render_resume_html(resume, template=template, settings=settings_data)})


@extend_schema(request=None, responses={201: OpenApiTypes.OBJECT})
@api_view(["POST"])
@permission_classes([AllowAny])
def export_resume(request, resume_id, output_format):
    resume = get_owned_resume(request, id=resume_id)
    try:
        user_file = save_export(resume, output_format)
    except ValueError as exc:
        return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    return Response(
        {
            "file_id": user_file.id,
            "filename": user_file.filename,
            "download_url": f"/api/files/download/{user_file.id}/",
        },
        status=status.HTTP_201_CREATED,
    )


@extend_schema(responses=OpenApiTypes.OBJECT)
@api_view(["GET"])
@permission_classes([AllowAny])
def my_anonymous_resume(request):
    if request.user.is_authenticated:
        return Response({"exists": False, "usage": usage_for_request(request)})
    identity = resolve_anonymous_identity(request, create=False)
    resume = Resume.objects.filter(anonymous_identity=identity, is_archived=False).first() if identity else None
    if not resume:
        return Response({"exists": False, "usage": usage_for_request(request)})
    return Response(
        {
            "exists": True,
            "resume": ResumeSerializer(resume, context={"request": request}).data,
            **usage_for_request(request, resume),
        }
    )


@extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def claim_anonymous_resume(request):
    from apps.files.models import UserFile
    from apps.jobs.models import ATSReport, JobDescription, JobMatch, TemporaryJobDescription

    identity = resolve_anonymous_identity(
        request,
        email=request.data.get("email"),
        phone_number=request.data.get("phone"),
        create=False,
    )
    # resolve_anonymous_identity intentionally returns None for authenticated
    # requests, so locate the pre-login identity using the supplied aliases and
    # the current network/session values.
    if identity is None:
        from .anonymous_identity import get_client_ip, normalize_email, normalize_phone
        from .models import AnonymousResumeIdentity, OptimizedResume, TemporaryGeneratedResume
        from django.db.models import Q

        query = Q()
        email = normalize_email(request.data.get("email") or getattr(request.user, "email", ""))
        phone = normalize_phone(request.data.get("phone"))
        session_key = request.session.session_key
        ip_address = get_client_ip(request)
        for key, value in (
            ("email", email),
            ("phone_number", phone),
            ("session_key", session_key),
            ("ip_address", ip_address),
        ):
            if value:
                query |= Q(**{key: value})
        identity = AnonymousResumeIdentity.objects.filter(query).order_by("created_at").first() if query else None
    if not identity:
        return Response({"success": True, "claimed_resumes": [], "usage": usage_for_request(request)})

    resumes = list(Resume.objects.filter(anonymous_identity=identity).order_by("created_at"))
    active_resumes = [resume for resume in resumes if not resume.is_archived]
    if active_resume_count(user=request.user) + len(active_resumes) > REGISTERED_MAX_RESUMES:
        return Response(
            {"error": "Your account already has 3 resumes. Please delete one before claiming this resume."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    with transaction.atomic():
        resume_ids = [resume.id for resume in active_resumes]
        Resume.objects.filter(id__in=resume_ids).update(
            user=request.user,
            anonymous_identity=None,
            source="registered",
            is_claimed=True,
        )
        UserFile.objects.filter(anonymous_identity=identity).update(user=request.user, anonymous_identity=None)
        JobDescription.objects.filter(anonymous_identity=identity).update(user=request.user, anonymous_identity=None)
        TemporaryJobDescription.objects.filter(anonymous_identity=identity).update(
            user=request.user, anonymous_identity=None
        )
        JobMatch.objects.filter(anonymous_identity=identity).update(user=request.user, anonymous_identity=None)
        ATSReport.objects.filter(anonymous_identity=identity).update(user=request.user, anonymous_identity=None)
        TemporaryGeneratedResume.objects.filter(anonymous_identity=identity).update(
            user=request.user, anonymous_identity=None
        )
        OptimizedResume.objects.filter(anonymous_identity=identity).update(user=request.user, anonymous_identity=None)
    claimed = Resume.objects.filter(id__in=resume_ids)
    return Response(
        {
            "success": True,
            "claimed_resumes": ResumeSerializer(claimed, many=True, context={"request": request}).data,
            "usage": usage_for_request(request),
        }
    )
