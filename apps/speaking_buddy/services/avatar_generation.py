import uuid

from django.conf import settings

from ..models import BuddyGeneratedAvatar


class BuddyAvatarGenerationError(Exception):
    pass


def request_generated_avatar(*, user, source_image, consent_confirmed, provider="stub"):
    if not consent_confirmed:
        raise BuddyAvatarGenerationError("consent_required")

    provider_name = provider or getattr(settings, "SPEAKING_BUDDY_AVATAR_PROVIDER", "stub")
    job_id = uuid.uuid4().hex
    default_glb = getattr(
        settings,
        "SPEAKING_BUDDY_GENERATED_AVATAR_DEFAULT_GLB",
        "https://threejs.org/examples/models/gltf/RobotExpressive/RobotExpressive.glb",
    )
    status = "completed" if provider_name == "stub" else "processing"

    avatar = BuddyGeneratedAvatar.objects.create(
        user=user,
        source_image=source_image,
        provider=provider_name,
        provider_job_id=job_id,
        status=status,
        consent_confirmed=True,
        user_generated=True,
        is_active=False,
        generated_glb_url=default_glb if status == "completed" else "",
        generated_thumbnail_url="",
    )
    return avatar
