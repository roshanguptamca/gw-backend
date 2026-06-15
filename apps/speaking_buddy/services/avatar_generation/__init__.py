from .base import AvatarGenerationError, AvatarGenerationService

BuddyAvatarGenerationError = AvatarGenerationError


def request_generated_avatar(*, user, source_image, consent_confirmed, provider="", options=None):
    return AvatarGenerationService().generate_from_photo(
        user=user,
        image=source_image,
        consent_confirmed=consent_confirmed,
        options={**(options or {}), "provider": provider or "template"},
    )


__all__ = [
    "AvatarGenerationError",
    "AvatarGenerationService",
    "BuddyAvatarGenerationError",
    "request_generated_avatar",
]
