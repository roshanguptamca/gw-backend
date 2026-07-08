"""Speaking Buddy's Cloudinary wrapper for the photo-avatar-generation flow.

Built on the app-independent core in ``apps.common.cloudinary_service`` so
this app does not depend on ``marketplace`` (or vice versa). Handles
uploading a user's source selfie plus generating a face-cropped thumbnail
via a Cloudinary eager transformation, so a "generated" avatar always has a
real, human image behind it instead of a generic icon.
"""

from django.conf import settings

from apps.common.cloudinary_service import delete_image, is_cloudinary_configured, upload_image

AVATAR_SOURCE_MAX_BYTES = getattr(settings, "SPEAKING_BUDDY_MAX_AVATAR_BYTES", 5 * 1024 * 1024)

# Face-cropped, fixed-size thumbnail so the avatar gallery/preview always has
# a consistent, human-centered image regardless of the uploaded photo's
# original aspect ratio.
THUMBNAIL_EAGER_TRANSFORM = [{"width": 400, "height": 400, "crop": "fill", "gravity": "face"}]


def _avatar_folder_prefix():
    return getattr(settings, "CLOUDINARY_BUDDY_AVATAR_FOLDER", "guidewisey/buddy_avatars").strip("/")


def _avatar_public_id(user_id, avatar_id, suffix):
    return f"{_avatar_folder_prefix()}/{user_id}/{avatar_id}/{suffix}"


def upload_avatar_source_photo(user_id, avatar_id, image_file):
    """Uploads the user's source photo to Cloudinary and requests an eager
    face-cropped thumbnail alongside it.

    Returns ``(source_public_id, source_url, thumbnail_url)``. ``thumbnail_url``
    falls back to ``source_url`` if the eager transform result is unavailable
    for any reason (still a real photo, never a generic icon).
    """
    public_id = _avatar_public_id(user_id, avatar_id, "source")
    uploaded_public_id, secure_url, eager_results = upload_image(
        image_file,
        public_id,
        max_bytes=AVATAR_SOURCE_MAX_BYTES,
        eager=THUMBNAIL_EAGER_TRANSFORM,
    )
    thumbnail_url = secure_url
    if eager_results:
        thumbnail_url = eager_results[0].get("secure_url") or secure_url
    return uploaded_public_id, secure_url, thumbnail_url


def delete_avatar_source_photo(public_id):
    return delete_image(public_id, resource_type="image")


__all__ = [
    "is_cloudinary_configured",
    "upload_avatar_source_photo",
    "delete_avatar_source_photo",
]
