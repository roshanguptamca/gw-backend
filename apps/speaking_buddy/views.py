import logging
from datetime import timedelta

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import BuddyAvatar, BuddyMemory, BuddyMessage, BuddyProfile, BuddySession, BuddySettings
from .serializers import (
    BuddyAvatarSerializer,
    BuddyMemorySerializer,
    BuddyProfileSerializer,
    BuddyRealtimeTokenSerializer,
    BuddySessionEndSerializer,
    BuddySessionMessageSerializer,
    BuddySessionSerializer,
    BuddySessionStartSerializer,
    BuddySettingsSerializer,
)
from .services.context_builder import build_session_context
from .services.memory_service import update_session_insights
from .services.openai_buddy import SpeakingBuddyError, create_realtime_client_secret, generate_buddy_reply, summarize_session

logger = logging.getLogger(__name__)


def _ensure_profile(user):
    profile, created = BuddyProfile.objects.get_or_create(user=user)
    if created:
        try:
            user_profile = user.profile
            if user_profile.preferred_language in {"en", "nl"}:
                profile.native_language = user_profile.preferred_language
                profile.target_language = user_profile.preferred_language
                profile.save(update_fields=["native_language", "target_language", "updated_at"])
        except Exception:
            pass
    BuddySettings.objects.get_or_create(profile=profile)
    return profile


def _profile_payload(profile):
    settings_obj = BuddySettings.objects.filter(profile=profile).first()
    avatars = BuddyAvatar.objects.filter(profile=profile).order_by("-is_active", "-updated_at")
    sessions = BuddySession.objects.filter(profile=profile).order_by("-started_at")[:10]
    memories = BuddyMemory.objects.filter(profile=profile, is_active=True).order_by("-updated_at")[:20]
    return {
        "profile": BuddyProfileSerializer(profile).data,
        "settings": BuddySettingsSerializer(settings_obj).data if settings_obj else None,
        "avatars": BuddyAvatarSerializer(avatars, many=True, context={}).data,
        "active_avatar": BuddyAvatarSerializer(avatars.filter(is_active=True).first(), context={}).data if avatars.filter(is_active=True).first() else None,
        "recent_sessions": BuddySessionSerializer(sessions, many=True).data,
        "recent_memory": BuddyMemorySerializer(memories, many=True).data,
    }


def _session_transcript(session):
    transcript = list(session.transcript or [])
    messages = session.messages.order_by("created_at")
    if messages.exists():
        transcript = [
            {
                "role": message.role,
                "text": message.text,
                "audio_url": message.audio_url,
                "metadata": message.metadata,
                "created_at": message.created_at.isoformat(),
            }
            for message in messages
        ]
    return transcript


@api_view(["GET", "POST", "PATCH"])
@permission_classes([IsAuthenticated])
def buddy_profile_view(request):
    profile = _ensure_profile(request.user)
    if request.method == "GET":
        return Response(_profile_payload(profile))

    serializer = BuddyProfileSerializer(profile, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(_profile_payload(serializer.instance))


@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
def buddy_settings_view(request):
    profile = _ensure_profile(request.user)
    settings_obj, _ = BuddySettings.objects.get_or_create(profile=profile)
    if request.method == "GET":
        return Response(BuddySettingsSerializer(settings_obj).data)

    serializer = BuddySettingsSerializer(settings_obj, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data)


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def buddy_avatar_view(request):
    profile = _ensure_profile(request.user)
    if request.method == "GET":
        avatars = BuddyAvatar.objects.filter(profile=profile).order_by("-is_active", "-updated_at")
        return Response({
            "avatars": BuddyAvatarSerializer(avatars, many=True).data,
            "active_avatar": BuddyAvatarSerializer(avatars.filter(is_active=True).first()).data if avatars.filter(is_active=True).exists() else None,
        })

    if request.data.get("avatar_id"):
        avatar = get_object_or_404(BuddyAvatar, id=request.data.get("avatar_id"), profile=profile)
        BuddyAvatar.objects.filter(profile=profile).update(is_active=False)
        avatar.is_active = True
        avatar.save(update_fields=["is_active", "updated_at"])
        return Response(BuddyAvatarSerializer(avatar).data)

    serializer = BuddyAvatarSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    BuddyAvatar.objects.filter(profile=profile).update(is_active=False)
    avatar = serializer.save(profile=profile, is_active=True)
    if avatar.image and not avatar.image_url:
        avatar.image_url = request.build_absolute_uri(avatar.image.url)
        avatar.save(update_fields=["image_url", "updated_at"])
    return Response(BuddyAvatarSerializer(avatar).data, status=status.HTTP_201_CREATED)


@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
def buddy_memory_view(request):
    profile = _ensure_profile(request.user)
    if request.method == "GET":
        memories = BuddyMemory.objects.filter(profile=profile).order_by("-updated_at")
        return Response(BuddyMemorySerializer(memories, many=True).data)

    serializer = BuddyMemorySerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    memory = get_object_or_404(BuddyMemory, id=serializer.validated_data["memory_id"], profile=profile)
    for field in ("value", "importance", "is_active"):
        if field in serializer.validated_data:
            setattr(memory, field, serializer.validated_data[field])
    memory.save()
    return Response(BuddyMemorySerializer(memory).data)


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def buddy_memory_detail_view(request, pk):
    profile = _ensure_profile(request.user)
    memory = get_object_or_404(BuddyMemory, id=pk, profile=profile)
    memory.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def buddy_history_view(request):
    profile = _ensure_profile(request.user)
    sessions = BuddySession.objects.filter(profile=profile).order_by("-started_at")
    payload = []
    for session in sessions:
        payload.append({
            **BuddySessionSerializer(session).data,
            "message_count": session.messages.count(),
            "transcript": _session_transcript(session),
        })
    return Response(payload)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def buddy_session_view(request):
    profile = _ensure_profile(request.user)
    session = BuddySession.objects.filter(profile=profile).order_by("-started_at").first()
    if not session:
        return Response({"session": None})
    payload = BuddySessionSerializer(session).data
    payload["transcript"] = _session_transcript(session)
    return Response(payload)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def buddy_session_start_view(request):
    profile = _ensure_profile(request.user)
    serializer = BuddySessionStartSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    settings_obj = BuddySettings.objects.get(profile=profile)
    language = serializer.validated_data.get("language") or profile.target_language
    topic = serializer.validated_data.get("topic") or settings_obj.default_topic or "General speaking practice"
    session = BuddySession.objects.create(profile=profile, language=language, topic=topic, status="active", transcript=[])
    context = build_session_context(profile, settings_obj)
    welcome = generate_buddy_reply(context, f"Start a short {language} conversation about {topic}.", [])
    BuddyMessage.objects.create(session=session, role="assistant", text=welcome, metadata={"kind": "welcome"})
    session.transcript = [{"role": "assistant", "text": welcome, "metadata": {"kind": "welcome"}}]
    session.save(update_fields=["transcript", "updated_at"])
    payload = BuddySessionSerializer(session).data
    payload["welcome_message"] = welcome
    payload["context"] = context.prompt_data
    return Response(payload, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def buddy_session_message_view(request):
    profile = _ensure_profile(request.user)
    serializer = BuddySessionMessageSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    session = get_object_or_404(BuddySession, id=serializer.validated_data["session_id"], profile=profile)
    if session.status != "active":
        return Response({"error": "session_not_active"}, status=status.HTTP_400_BAD_REQUEST)

    user_text = serializer.validated_data["text"]
    BuddyMessage.objects.create(session=session, role="user", text=user_text, metadata={})
    transcript = _session_transcript(session)
    context = build_session_context(profile, BuddySettings.objects.get(profile=profile))
    reply = generate_buddy_reply(context, user_text, transcript)
    BuddyMessage.objects.create(session=session, role="assistant", text=reply, metadata={})
    transcript.append({"role": "assistant", "text": reply})
    session.transcript = transcript
    session.save(update_fields=["transcript", "updated_at"])
    return Response({
        "session_id": session.id,
        "assistant_reply": reply,
        "transcript": transcript,
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def buddy_session_end_view(request):
    profile = _ensure_profile(request.user)
    serializer = BuddySessionEndSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    session = get_object_or_404(BuddySession, id=serializer.validated_data["session_id"], profile=profile)
    if session.status == "ended":
        return Response(BuddySessionSerializer(session).data)

    transcript = _session_transcript(session)
    context = build_session_context(profile, BuddySettings.objects.get(profile=profile))
    summary = summarize_session(context, transcript)
    session.ended_at = timezone.now()
    session.status = "ended"
    session.duration_seconds = max(0, int((session.ended_at - session.started_at).total_seconds()))
    session.ai_summary = summary.get("summary", "")
    session.user_summary = summary.get("user_summary", "")
    session.mistakes_detected = summary.get("mistakes", [])
    session.vocabulary_practiced = summary.get("vocabulary", [])
    session.improvement_notes = "\n".join(summary.get("improvement_notes", []))
    session.save()
    update_session_insights(profile, session, summary)
    payload = BuddySessionSerializer(session).data
    payload["summary_payload"] = summary
    return Response(payload)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def buddy_realtime_token_view(request):
    profile = _ensure_profile(request.user)
    serializer = BuddyRealtimeTokenSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    settings_obj = BuddySettings.objects.get(profile=profile)
    session = None
    if serializer.validated_data.get("session_id"):
        session = get_object_or_404(BuddySession, id=serializer.validated_data["session_id"], profile=profile)
    context = build_session_context(profile, settings_obj)
    try:
        token = create_realtime_client_secret(context)
    except SpeakingBuddyError as exc:
        code = getattr(exc, "code", "realtime_token_failed")
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE if code in {"openai_not_configured", "realtime_token_failed"} else status.HTTP_400_BAD_REQUEST
        return Response({"error": code}, status=status_code)
    return Response(token)
