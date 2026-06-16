import logging

from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import (
    Buddy3DAvatar,
    BuddyAvatar,
    BuddyGeneratedAvatar,
    BuddyMemory,
    BuddyMessage,
    BuddyMistake,
    BuddyProfile,
    BuddySession,
    BuddySettings,
    BuddyVocabulary,
)
from .serializers import (
    Buddy3DAvatarSelectSerializer,
    Buddy3DAvatarSerializer,
    BuddyAvatarSerializer,
    BuddyGeneratedAvatarCreateSerializer,
    BuddyGeneratedAvatarRegenerateSerializer,
    BuddyGeneratedAvatarSerializer,
    BuddyMemorySerializer,
    BuddyMistakeSerializer,
    BuddyProfileSerializer,
    BuddyRealtimeTokenSerializer,
    BuddySessionEndSerializer,
    BuddySessionMessageSerializer,
    BuddySessionSerializer,
    BuddySessionStartSerializer,
    BuddySettingsSerializer,
    BuddyVocabularySerializer,
)
from .services.avatar_generation import AvatarGenerationService, BuddyAvatarGenerationError, request_generated_avatar
from .services.context_builder import build_session_context, language_name
from .services.memory_service import update_session_insights
from .services.openai_buddy import (
    SpeakingBuddyError,
    create_realtime_client_secret,
    generate_buddy_reply,
    summarize_session,
)
from .services.quota import (
    can_start_conversation,
    end_session_reason,
    get_remaining_conversations,
    get_usage_quota,
    increment_conversation_usage,
)

logger = logging.getLogger(__name__)


def _ensure_profile(user):
    profile, created = BuddyProfile.objects.get_or_create(user=user)
    if created:
        try:
            user_profile = user.profile
            profile.native_language = user_profile.preferred_language
            profile.target_language = user_profile.preferred_language
            profile.save(update_fields=["native_language", "target_language", "updated_at"])
        except Exception:
            pass
    BuddySettings.objects.get_or_create(profile=profile)
    return profile


def _profile_payload(profile, request=None):
    settings_obj = BuddySettings.objects.filter(profile=profile).first()
    avatars = BuddyAvatar.objects.filter(profile=profile).order_by("-is_active", "-updated_at")
    catalog_3d = Buddy3DAvatar.objects.filter(is_active=True).order_by("name")
    generated_avatars = BuddyGeneratedAvatar.objects.filter(user=profile.user).order_by("-updated_at")
    sessions = BuddySession.objects.filter(profile=profile).order_by("-started_at")[:10]
    memories = BuddyMemory.objects.filter(profile=profile, is_active=True).order_by("-updated_at")[:20]
    context = {"request": request} if request is not None else {}
    selected_3d_avatar = None
    selected_generated_avatar = None
    if settings_obj:
        if settings_obj.selected_3d_avatar_slug:
            selected_3d_avatar = catalog_3d.filter(slug=settings_obj.selected_3d_avatar_slug).first()
        if settings_obj.selected_generated_avatar_id:
            selected_generated_avatar = generated_avatars.filter(id=settings_obj.selected_generated_avatar_id).first()
    render_mode = settings_obj.avatar_render_mode if settings_obj else "2d"
    if render_mode == "generated_3d" and selected_generated_avatar:
        selected_renderable_avatar = BuddyGeneratedAvatarSerializer(
            selected_generated_avatar,
            context=context,
        ).data
    elif selected_3d_avatar:
        selected_renderable_avatar = Buddy3DAvatarSerializer(
            selected_3d_avatar,
            context=context,
        ).data
    else:
        selected_renderable_avatar = None
    return {
        "profile": BuddyProfileSerializer(profile, context=context).data,
        "settings": BuddySettingsSerializer(settings_obj, context=context).data if settings_obj else None,
        "avatars": BuddyAvatarSerializer(avatars, many=True, context=context).data,
        "active_avatar": (
            BuddyAvatarSerializer(avatars.filter(is_active=True).first(), context=context).data
            if avatars.filter(is_active=True).first()
            else None
        ),
        "avatar_render_mode": render_mode,
        "three_d_avatars": Buddy3DAvatarSerializer(catalog_3d, many=True, context=context).data,
        "selected_3d_avatar": (
            Buddy3DAvatarSerializer(selected_3d_avatar, context=context).data if selected_3d_avatar else None
        ),
        "selected_3d_renderable_avatar": selected_renderable_avatar,
        "generated_avatars": BuddyGeneratedAvatarSerializer(generated_avatars, many=True, context=context).data,
        "selected_generated_avatar": (
            BuddyGeneratedAvatarSerializer(selected_generated_avatar, context=context).data
            if selected_generated_avatar
            else None
        ),
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
        return Response(_profile_payload(profile, request=request))

    serializer = BuddyProfileSerializer(profile, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(_profile_payload(serializer.instance, request=request))


@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
def buddy_settings_view(request):
    profile = _ensure_profile(request.user)
    settings_obj, _ = BuddySettings.objects.get_or_create(profile=profile)
    if request.method == "GET":
        return Response(BuddySettingsSerializer(settings_obj, context={"request": request}).data)

    serializer = BuddySettingsSerializer(settings_obj, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data)


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def buddy_avatar_view(request):
    profile = _ensure_profile(request.user)
    settings_obj, _ = BuddySettings.objects.get_or_create(profile=profile)
    if request.method == "GET":
        avatars = BuddyAvatar.objects.filter(profile=profile).order_by("-is_active", "-updated_at")
        generated_avatars = BuddyGeneratedAvatar.objects.filter(user=profile.user).order_by("-updated_at")
        selected_3d_avatar = (
            Buddy3DAvatar.objects.filter(slug=settings_obj.selected_3d_avatar_slug, is_active=True).first()
            if settings_obj.selected_3d_avatar_slug
            else None
        )
        selected_generated_avatar = (
            generated_avatars.filter(id=settings_obj.selected_generated_avatar_id).first()
            if settings_obj.selected_generated_avatar_id
            else None
        )
        return Response(
            {
                "avatars": BuddyAvatarSerializer(avatars, many=True, context={"request": request}).data,
                "active_avatar": (
                    BuddyAvatarSerializer(avatars.filter(is_active=True).first(), context={"request": request}).data
                    if avatars.filter(is_active=True).exists()
                    else None
                ),
                "three_d_avatars": Buddy3DAvatarSerializer(
                    Buddy3DAvatar.objects.filter(is_active=True).order_by("name"),
                    many=True,
                    context={"request": request},
                ).data,
                "selected_3d_avatar": (
                    Buddy3DAvatarSerializer(selected_3d_avatar, context={"request": request}).data
                    if selected_3d_avatar
                    else None
                ),
                "generated_avatars": BuddyGeneratedAvatarSerializer(
                    generated_avatars, many=True, context={"request": request}
                ).data,
                "selected_generated_avatar": (
                    BuddyGeneratedAvatarSerializer(selected_generated_avatar, context={"request": request}).data
                    if selected_generated_avatar
                    else None
                ),
                "avatar_render_mode": settings_obj.avatar_render_mode,
            }
        )

    select_serializer = Buddy3DAvatarSelectSerializer(data=request.data)
    if select_serializer.is_valid():
        selected_mode = select_serializer.validated_data.get("avatar_render_mode")
        if select_serializer.validated_data.get("avatar_3d_slug"):
            avatar = get_object_or_404(
                Buddy3DAvatar, slug=select_serializer.validated_data["avatar_3d_slug"], is_active=True
            )
            settings_obj.avatar_render_mode = "3d"
            settings_obj.selected_3d_avatar_slug = avatar.slug
            settings_obj.selected_generated_avatar = None
            settings_obj.save(
                update_fields=[
                    "avatar_render_mode",
                    "selected_3d_avatar_slug",
                    "selected_generated_avatar",
                    "updated_at",
                ]
            )
            return Response(_profile_payload(profile, request=request))
        if select_serializer.validated_data.get("generated_avatar_id"):
            avatar = get_object_or_404(
                BuddyGeneratedAvatar, id=select_serializer.validated_data["generated_avatar_id"], user=profile.user
            )
            settings_obj.avatar_render_mode = "generated_3d"
            settings_obj.selected_generated_avatar = avatar
            settings_obj.selected_3d_avatar_slug = ""
            settings_obj.save(
                update_fields=[
                    "avatar_render_mode",
                    "selected_generated_avatar",
                    "selected_3d_avatar_slug",
                    "updated_at",
                ]
            )
            return Response(_profile_payload(profile, request=request))
        if selected_mode in {"3d", "generated_3d"}:
            settings_obj.avatar_render_mode = selected_mode
            settings_obj.save(
                update_fields=[
                    "avatar_render_mode",
                    "selected_3d_avatar_slug",
                    "selected_generated_avatar",
                    "updated_at",
                ]
            )
            return Response(_profile_payload(profile, request=request))

    if request.data.get("avatar_id"):
        avatar = get_object_or_404(BuddyAvatar, id=request.data.get("avatar_id"), profile=profile)
        BuddyAvatar.objects.filter(profile=profile).update(is_active=False)
        avatar.is_active = True
        avatar.save(update_fields=["is_active", "updated_at"])
        settings_obj.avatar_render_mode = "2d"
        settings_obj.selected_3d_avatar_slug = ""
        settings_obj.selected_generated_avatar = None
        settings_obj.save(
            update_fields=["avatar_render_mode", "selected_3d_avatar_slug", "selected_generated_avatar", "updated_at"]
        )
        return Response(BuddyAvatarSerializer(avatar, context={"request": request}).data)

    serializer = BuddyAvatarSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    BuddyAvatar.objects.filter(profile=profile).update(is_active=False)
    avatar = serializer.save(profile=profile, is_active=True)
    if avatar.image and not avatar.image_url:
        avatar.image_url = request.build_absolute_uri(avatar.image.url)
        avatar.save(update_fields=["image_url", "updated_at"])
    settings_obj.avatar_render_mode = "2d"
    settings_obj.selected_3d_avatar_slug = ""
    settings_obj.selected_generated_avatar = None
    settings_obj.save(
        update_fields=["avatar_render_mode", "selected_3d_avatar_slug", "selected_generated_avatar", "updated_at"]
    )
    return Response(BuddyAvatarSerializer(avatar, context={"request": request}).data, status=status.HTTP_201_CREATED)


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def buddy_3d_avatar_view(request):
    profile = _ensure_profile(request.user)
    settings_obj, _ = BuddySettings.objects.get_or_create(profile=profile)
    catalog = Buddy3DAvatar.objects.filter(is_active=True).order_by("name")
    generated_avatars = BuddyGeneratedAvatar.objects.filter(user=profile.user).order_by("-updated_at")

    if request.method == "GET":
        selected_3d_avatar = (
            catalog.filter(slug=settings_obj.selected_3d_avatar_slug).first()
            if settings_obj.selected_3d_avatar_slug
            else None
        )
        selected_generated_avatar = (
            generated_avatars.filter(id=settings_obj.selected_generated_avatar_id).first()
            if settings_obj.selected_generated_avatar_id
            else None
        )
        return Response(
            {
                "catalog": Buddy3DAvatarSerializer(catalog, many=True, context={"request": request}).data,
                "generated_avatars": BuddyGeneratedAvatarSerializer(
                    generated_avatars, many=True, context={"request": request}
                ).data,
                "selected_3d_avatar": (
                    Buddy3DAvatarSerializer(selected_3d_avatar, context={"request": request}).data
                    if selected_3d_avatar
                    else None
                ),
                "selected_generated_avatar": (
                    BuddyGeneratedAvatarSerializer(selected_generated_avatar, context={"request": request}).data
                    if selected_generated_avatar
                    else None
                ),
                "avatar_render_mode": settings_obj.avatar_render_mode,
            }
        )

    select_serializer = Buddy3DAvatarSelectSerializer(data=request.data)
    select_serializer.is_valid(raise_exception=True)
    if select_serializer.validated_data.get("avatar_3d_slug"):
        avatar = get_object_or_404(
            Buddy3DAvatar, slug=select_serializer.validated_data["avatar_3d_slug"], is_active=True
        )
        settings_obj.avatar_render_mode = "3d"
        settings_obj.selected_3d_avatar_slug = avatar.slug
        settings_obj.selected_generated_avatar = None
        settings_obj.save(
            update_fields=["avatar_render_mode", "selected_3d_avatar_slug", "selected_generated_avatar", "updated_at"]
        )
    elif select_serializer.validated_data.get("generated_avatar_id"):
        avatar = get_object_or_404(
            BuddyGeneratedAvatar, id=select_serializer.validated_data["generated_avatar_id"], user=profile.user
        )
        settings_obj.avatar_render_mode = "generated_3d"
        settings_obj.selected_generated_avatar = avatar
        settings_obj.selected_3d_avatar_slug = ""
        settings_obj.save(
            update_fields=["avatar_render_mode", "selected_generated_avatar", "selected_3d_avatar_slug", "updated_at"]
        )
    elif select_serializer.validated_data.get("avatar_render_mode"):
        settings_obj.avatar_render_mode = select_serializer.validated_data["avatar_render_mode"]
        if settings_obj.avatar_render_mode == "2d":
            settings_obj.selected_3d_avatar_slug = ""
            settings_obj.selected_generated_avatar = None
        settings_obj.save(
            update_fields=["avatar_render_mode", "selected_3d_avatar_slug", "selected_generated_avatar", "updated_at"]
        )

    return Response(_profile_payload(profile, request=request))


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def buddy_generated_avatar_view(request):
    profile = _ensure_profile(request.user)
    if request.method == "GET":
        avatars = BuddyGeneratedAvatar.objects.filter(user=profile.user).order_by("-updated_at")
        return Response(
            {"generated_avatars": BuddyGeneratedAvatarSerializer(avatars, many=True, context={"request": request}).data}
        )

    serializer = BuddyGeneratedAvatarCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        options = {
            key: serializer.validated_data.get(key, "")
            for key in (
                "preferred_gender_style",
                "preferred_age_style",
                "preferred_hair_style",
                "preferred_outfit_style",
                "realism_level",
            )
        }
        avatar = request_generated_avatar(
            user=profile.user,
            source_image=serializer.validated_data["source_image"],
            consent_confirmed=serializer.validated_data["consent_confirmed"],
            provider=serializer.validated_data.get("provider") or "",
            options=options,
        )
    except BuddyAvatarGenerationError as exc:
        return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    return Response(
        BuddyGeneratedAvatarSerializer(avatar, context={"request": request}).data, status=status.HTTP_201_CREATED
    )


@api_view(["GET", "DELETE"])
@permission_classes([IsAuthenticated])
def buddy_generated_avatar_detail_view(request, pk):
    profile = _ensure_profile(request.user)
    avatar = get_object_or_404(BuddyGeneratedAvatar, id=pk, user=profile.user)
    if request.method == "GET":
        return Response(BuddyGeneratedAvatarSerializer(avatar, context={"request": request}).data)
    if profile.buddy_settings.selected_generated_avatar_id == avatar.id:
        profile.buddy_settings.selected_generated_avatar = None
        profile.buddy_settings.avatar_render_mode = "2d"
        profile.buddy_settings.save(update_fields=["selected_generated_avatar", "avatar_render_mode", "updated_at"])
    avatar.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def buddy_generated_avatar_regenerate_view(request, pk):
    profile = _ensure_profile(request.user)
    avatar = get_object_or_404(BuddyGeneratedAvatar, id=pk, user=profile.user)
    serializer = BuddyGeneratedAvatarRegenerateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        avatar = AvatarGenerationService().regenerate(avatar, serializer.validated_data)
    except BuddyAvatarGenerationError as exc:
        return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    return Response(BuddyGeneratedAvatarSerializer(avatar, context={"request": request}).data)


@api_view(["GET", "POST", "PATCH"])
@permission_classes([IsAuthenticated])
def buddy_memory_view(request):
    profile = _ensure_profile(request.user)
    if request.method == "GET":
        memories = BuddyMemory.objects.filter(profile=profile).order_by("-updated_at")
        return Response(BuddyMemorySerializer(memories, many=True).data)

    if request.method == "POST":
        serializer = BuddyMemorySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        memory = serializer.save(profile=profile)
        return Response(BuddyMemorySerializer(memory).data, status=status.HTTP_201_CREATED)

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
        payload.append(
            {
                **BuddySessionSerializer(session).data,
                "message_count": session.messages.count(),
                "transcript": _session_transcript(session),
            }
        )
    return Response(payload)


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def buddy_vocabulary_view(request):
    profile = _ensure_profile(request.user)
    if request.method == "GET":
        items = BuddyVocabulary.objects.filter(profile=profile).order_by("-updated_at")
        return Response(BuddyVocabularySerializer(items, many=True).data)
    serializer = BuddyVocabularySerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    item = serializer.save(profile=profile)
    return Response(BuddyVocabularySerializer(item).data, status=status.HTTP_201_CREATED)


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def buddy_mistakes_view(request):
    profile = _ensure_profile(request.user)
    if request.method == "GET":
        items = BuddyMistake.objects.filter(profile=profile).order_by("-created_at")
        return Response(BuddyMistakeSerializer(items, many=True).data)
    serializer = BuddyMistakeSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    session = serializer.validated_data.get("session")
    if session and session.profile_id != profile.id:
        return Response({"session": "Invalid session."}, status=status.HTTP_400_BAD_REQUEST)
    item = serializer.save(profile=profile)
    return Response(BuddyMistakeSerializer(item).data, status=status.HTTP_201_CREATED)


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
    active_session = BuddySession.objects.filter(profile=profile, status="active").order_by("-started_at").first()
    if active_session:
        payload = BuddySessionSerializer(active_session).data
        payload["transcript"] = _session_transcript(active_session)
        payload["reused_session"] = True
        return Response(payload)
    if not can_start_conversation(request.user):
        return Response(
            {
                "error": "You've used your 100 free AI Buddy conversations.",
                "detail": "You've used your 100 free AI Buddy conversations.",
            },
            status=status.HTTP_403_FORBIDDEN,
        )
    language = serializer.validated_data.get("language") or profile.target_language
    topic = serializer.validated_data.get("topic") or settings_obj.default_topic or "General speaking practice"
    session = BuddySession.objects.create(
        profile=profile,
        language=language,
        topic=topic,
        status="active",
        transcript=[],
        selected_voice=settings_obj.selected_voice,
    )
    context = build_session_context(profile, settings_obj)
    welcome = generate_buddy_reply(context, f"Start a short {language_name(language)} conversation about {topic}.", [])
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
    return Response(
        {
            "session_id": session.id,
            "assistant_reply": reply,
            "transcript": transcript,
        }
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@csrf_exempt
def buddy_session_end_view(request):
    profile = _ensure_profile(request.user)
    serializer = BuddySessionEndSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    session = get_object_or_404(BuddySession, id=serializer.validated_data["session_id"], profile=profile)
    end_reason = serializer.validated_data.get("reason") or ""
    client_closed_at = serializer.validated_data.get("client_closed_at")
    end_session_reason(session, end_reason, client_closed_at)
    if session.status == "ended":
        quota = get_usage_quota(request.user)
        payload = BuddySessionSerializer(session).data
        payload["usage_counted"] = session.usage_counted
        payload["usage"] = {
            "conversations_used": quota.conversations_used,
            "free_conversation_limit": quota.free_conversation_limit,
            "conversations_remaining": quota.conversations_remaining,
            "is_limit_reached": quota.conversations_remaining <= 0,
        }
        return Response(payload)

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
    if end_reason:
        session.end_reason = end_reason
    if client_closed_at:
        session.client_closed_at = client_closed_at
    session.save()
    update_session_insights(profile, session, summary)
    quota, counted = increment_conversation_usage(request.user, session)
    payload = BuddySessionSerializer(session).data
    payload["summary_payload"] = summary
    payload["usage_counted"] = counted
    payload["usage"] = {
        "conversations_used": quota.conversations_used,
        "free_conversation_limit": quota.free_conversation_limit,
        "conversations_remaining": quota.conversations_remaining,
        "is_limit_reached": quota.conversations_remaining <= 0,
    }
    return Response(payload)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def buddy_usage_view(request):
    quota = get_usage_quota(request.user)
    return Response(
        {
            "conversations_used": quota.conversations_used,
            "free_conversation_limit": quota.free_conversation_limit,
            "conversations_remaining": get_remaining_conversations(request.user),
            "is_limit_reached": quota.conversations_remaining <= 0,
        }
    )


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
        selected_voice = session.selected_voice if session else settings_obj.selected_voice
        token = create_realtime_client_secret(
            context,
            selected_voice=selected_voice,
            buddy_session_id=session.id if session else None,
        )
    except SpeakingBuddyError as exc:
        code = getattr(exc, "code", "realtime_token_failed")
        status_code = (
            status.HTTP_503_SERVICE_UNAVAILABLE
            if code in {"openai_not_configured", "realtime_token_failed"}
            else status.HTTP_400_BAD_REQUEST
        )
        return Response({"error": code}, status=status_code)
    return Response(token)
