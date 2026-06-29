from django.shortcuts import get_object_or_404

import requests
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.resumes.anonymous_identity import resolve_anonymous_identity
from apps.resumes.limits import (
    REGISTERED_MAX_RESUMES,
    active_resume_count,
    can_edit_resume,
    get_owned_resume,
    increment_resume_edit_count,
    usage_for_request,
)
from apps.resumes.models import Resume
from apps.resumes.serializers import ResumeSerializer

from .models import JobDescription, JobMatch
from .serializers import JobDescriptionSerializer, JobMatchSerializer, OptimizeRequestSerializer
from .services import analyze_match, optimize_match, parse_job_text, parse_job_url, store_temporary_job


@extend_schema(request=OpenApiTypes.OBJECT, responses={201: JobDescriptionSerializer})
@api_view(["POST"])
@permission_classes([AllowAny])
def parse_text(request):
    text = request.data.get("text", "").strip()
    if not text:
        return Response({"error": "Job description text is required."}, status=status.HTTP_400_BAD_REQUEST)
    language = request.data.get("language", "en")
    if language not in {"en", "nl"}:
        return Response({"language": ["Language must be 'en' or 'nl'."]}, status=status.HTTP_400_BAD_REQUEST)
    parsed = parse_job_text(text)
    identity = None if request.user.is_authenticated else resolve_anonymous_identity(request)
    user = request.user if request.user.is_authenticated else None
    temporary = store_temporary_job(user, parsed, anonymous_identity=identity)
    job = JobDescription.objects.create(
        user=user,
        anonymous_identity=identity,
        title=request.data.get("title") or parsed["title"],
        company=request.data.get("company", ""),
        raw_text=text,
        parsed_json=parsed,
        language=language,
    )
    return Response(
        {"job_description": JobDescriptionSerializer(job).data, "temporary_id": temporary.id},
        status=status.HTTP_201_CREATED,
    )


@extend_schema(request=OpenApiTypes.OBJECT, responses={201: JobDescriptionSerializer})
@api_view(["POST"])
@permission_classes([AllowAny])
def parse_url(request):
    url = request.data.get("url", "").strip()
    if not url:
        return Response({"error": "A job URL is required."}, status=status.HTTP_400_BAD_REQUEST)
    language = request.data.get("language", "en")
    if language not in {"en", "nl"}:
        return Response({"language": ["Language must be 'en' or 'nl'."]}, status=status.HTTP_400_BAD_REQUEST)
    try:
        parsed = parse_job_url(url)
    except (ValueError, requests.RequestException) as exc:
        return Response(
            {
                "success": False,
                "error": "We could not read this job page. Please paste the job description manually.",
                "message": "We could not read this job page. Please paste the job description manually.",
                "detail": str(exc),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
    identity = None if request.user.is_authenticated else resolve_anonymous_identity(request)
    user = request.user if request.user.is_authenticated else None
    temporary = store_temporary_job(user, parsed, url, anonymous_identity=identity)
    job = JobDescription.objects.create(
        user=user,
        anonymous_identity=identity,
        title=request.data.get("title") or parsed.get("title", ""),
        company=request.data.get("company") or parsed.get("company", ""),
        source_url=url,
        raw_text=parsed["raw_text"],
        parsed_json=parsed,
        language=language,
    )
    return Response(
        {
            "success": True,
            "job_title": job.title,
            "company": job.company,
            "location": parsed.get("location", ""),
            "raw_text": job.raw_text,
            "parsed_json": {
                "required_skills": parsed.get("required_skills", []),
                "preferred_skills": parsed.get("preferred_skills", []),
                "responsibilities": parsed.get("responsibilities", []),
                "education": parsed.get("education", []),
                "certifications": parsed.get("certifications", []),
                "keywords": parsed.get("keywords", []),
            },
            "job_description": JobDescriptionSerializer(job).data,
            "temporary_id": temporary.id,
        },
        status=status.HTTP_201_CREATED,
    )


@extend_schema(request=OpenApiTypes.OBJECT, responses={201: JobMatchSerializer})
@api_view(["POST"])
@permission_classes([AllowAny])
def analyze(request):
    resume = get_owned_resume(request, id=request.data.get("resume_id"))
    job_filter = (
        {"user": request.user} if request.user.is_authenticated else {"anonymous_identity": resume.anonymous_identity}
    )
    job = get_object_or_404(JobDescription, id=request.data.get("job_description_id"), **job_filter)
    language = request.data.get("language", resume.locale)
    if language not in {"en", "nl"}:
        return Response({"language": ["Language must be 'en' or 'nl'."]}, status=status.HTTP_400_BAD_REQUEST)
    match = analyze_match(
        resume,
        job,
        request.user if request.user.is_authenticated else None,
        report_language=language,
    )
    return Response(JobMatchSerializer(match).data, status=status.HTTP_201_CREATED)


@extend_schema(request=OptimizeRequestSerializer, responses={201: OpenApiTypes.OBJECT})
@api_view(["POST"])
@permission_classes([AllowAny])
def optimize(request, match_id):
    if request.user.is_authenticated:
        match = get_object_or_404(JobMatch, id=match_id, user=request.user)
    else:
        identity = resolve_anonymous_identity(request, create=False)
        match = get_object_or_404(JobMatch, id=match_id, anonymous_identity=identity)
    can_edit_resume(match.resume, request)
    if request.user.is_authenticated and active_resume_count(user=request.user) >= REGISTERED_MAX_RESUMES:
        return Response(
            {"error": "Free accounts can create up to 3 resumes."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    serializer = OptimizeRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    result = optimize_match(match, **serializer.validated_data)
    if match.resume.anonymous_identity_id:
        match.resume.is_archived = True
        match.resume.save(update_fields=["is_archived", "updated_at"])
        result["optimized_resume"].edit_count = match.resume.edit_count
        result["optimized_resume"].save(update_fields=["edit_count", "updated_at"])
        increment_resume_edit_count(result["optimized_resume"], request)
    else:
        increment_resume_edit_count(match.resume, request)
    optimized = result["optimized"]
    return Response(
        {
            "success": True,
            "id": optimized.id,
            "original_score": float(match.overall_score),
            "new_score": float(result["new_match"].overall_score),
            "target_score": serializer.validated_data["target_score"],
            "optimized_resume_id": result["optimized_resume"].id,
            "optimized_version_id": result["optimized_version"].id,
            "optimized_resume_record": ResumeSerializer(result["optimized_resume"], context={"request": request}).data,
            "changes": result["changes"],
            "remaining_gaps": result["remaining_gaps"],
            "optimized_resume": optimized.optimized_json,
            "confirmation_required_skills": optimized.confirmation_required_skills,
            "usage": usage_for_request(request, result["optimized_resume"]),
        },
        status=status.HTTP_201_CREATED,
    )
