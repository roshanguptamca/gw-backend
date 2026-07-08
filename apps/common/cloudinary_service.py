"""App-independent Cloudinary upload core.

This module intentionally has no Django models/admin/migrations and is not
registered in INSTALLED_APPS — it is a plain, importable shared library so
that unrelated apps (e.g. ``marketplace`` and ``speaking_buddy``) can reuse
the same Cloudinary configuration/upload/delete logic without depending on
each other. Each app should keep its own domain-specific wrapper (public_id
naming, model field assignment, max sizes, etc.) and call into the generic
helpers here.
"""

import logging

from django.conf import settings
from django.core.exceptions import ValidationError

logger = logging.getLogger(__name__)

DEFAULT_ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
DEFAULT_ALLOWED_IMAGE_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
DEFAULT_MAX_IMAGE_BYTES = 5 * 1024 * 1024


def is_cloudinary_configured():
    return all(
        getattr(settings, name, "") for name in ("CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET")
    )


def validate_image_file(
    image_file,
    *,
    max_bytes=DEFAULT_MAX_IMAGE_BYTES,
    allowed_extensions=None,
    allowed_content_types=None,
):
    from pathlib import Path

    if not image_file:
        raise ValidationError("An image file is required.")

    allowed_extensions = allowed_extensions or DEFAULT_ALLOWED_IMAGE_EXTENSIONS
    allowed_content_types = allowed_content_types or DEFAULT_ALLOWED_IMAGE_CONTENT_TYPES

    extension = Path(getattr(image_file, "name", "")).suffix.lower().lstrip(".")
    if extension not in allowed_extensions:
        raise ValidationError("Only jpg, jpeg, png, and webp images are allowed.")

    # Freshly uploaded request files (e.g. SimpleUploadedFile/InMemoryUploadedFile)
    # always carry a content_type; a file re-opened from storage (as we do when
    # re-uploading an already-saved source photo to Cloudinary) does not, and
    # was already content-type-validated at the original upload time — so we
    # only enforce the content_type check when it's actually present.
    content_type = getattr(image_file, "content_type", "")
    if content_type and content_type.lower() not in allowed_content_types:
        raise ValidationError("Only jpg, jpeg, png, and webp images are allowed.")

    if image_file.size > max_bytes:
        max_mb = max_bytes // (1024 * 1024)
        raise ValidationError(f"Image must be {max_mb} MB or smaller.")
    return image_file


def cloudinary_uploader():
    missing = [
        name
        for name in ("CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET")
        if not getattr(settings, name, "")
    ]
    if missing:
        raise ValidationError("Cloudinary image uploads are not configured.")

    try:
        import cloudinary
        import cloudinary.uploader
    except ImportError as exc:  # pragma: no cover - deployment dependency guard
        raise ValidationError("Cloudinary image uploads are unavailable.") from exc

    cloudinary.config(
        cloud_name=settings.CLOUDINARY_CLOUD_NAME,
        api_key=settings.CLOUDINARY_API_KEY,
        api_secret=settings.CLOUDINARY_API_SECRET,
        secure=True,
    )
    return cloudinary.uploader


def upload_image(
    image_file,
    public_id,
    *,
    max_bytes=DEFAULT_MAX_IMAGE_BYTES,
    eager=None,
    resource_type="image",
):
    """Uploads ``image_file`` to Cloudinary under ``public_id``.

    Returns ``(public_id, secure_url, eager_results)`` where ``eager_results``
    is the list of any requested eager-transformation results (e.g. a
    face-cropped thumbnail), or an empty list if ``eager`` was not passed.
    """
    validate_image_file(image_file, max_bytes=max_bytes)
    try:
        upload_kwargs = {
            "public_id": public_id,
            "overwrite": True,
            "invalidate": True,
            "resource_type": resource_type,
            "type": "upload",
            "format": "webp",
            "quality": "auto:good",
        }
        if eager:
            upload_kwargs["eager"] = eager
        result = cloudinary_uploader().upload(image_file, **upload_kwargs)
    except ValidationError:
        raise
    except Exception as exc:
        logger.exception("Cloudinary upload failed for %s", public_id)
        raise ValidationError("Image upload failed. Please try again.") from exc

    secure_url = result.get("secure_url")
    uploaded_public_id = result.get("public_id") or public_id
    if not secure_url or not secure_url.startswith("https://"):
        raise ValidationError("Cloudinary did not return a secure image URL.")
    return uploaded_public_id, secure_url, result.get("eager", [])


def delete_image(public_id, *, resource_type="image"):
    if not public_id:
        return None
    try:
        return cloudinary_uploader().destroy(public_id, resource_type=resource_type, invalidate=True)
    except ValidationError:
        raise
    except Exception as exc:
        logger.exception("Cloudinary deletion failed for %s", public_id)
        raise ValidationError("Image deletion failed. Please try again.") from exc
