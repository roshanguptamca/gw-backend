import logging
import re
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError

logger = logging.getLogger(__name__)

ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
ALLOWED_IMAGE_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
PRODUCT_IMAGE_MAX_BYTES = 2 * 1024 * 1024
BANNER_IMAGE_MAX_BYTES = 5 * 1024 * 1024
_SAFE_SKU = re.compile(r"^[A-Za-z0-9_-]+$")


def validate_image_file(image_file, *, max_bytes=PRODUCT_IMAGE_MAX_BYTES):
    if not image_file:
        raise ValidationError("An image file is required.")

    extension = Path(getattr(image_file, "name", "")).suffix.lower().lstrip(".")
    content_type = getattr(image_file, "content_type", "").lower()
    if extension not in ALLOWED_IMAGE_EXTENSIONS or content_type not in ALLOWED_IMAGE_CONTENT_TYPES:
        raise ValidationError("Only jpg, jpeg, png, and webp images are allowed.")

    if image_file.size > max_bytes:
        max_mb = max_bytes // (1024 * 1024)
        raise ValidationError(f"Image must be {max_mb} MB or smaller.")
    return image_file


def _cloudinary_uploader():
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


def _product_public_id(product, suffix):
    sku = (product.sku or "").strip()
    if not sku:
        raise ValidationError("A SKU is required before uploading product images.")
    if not _SAFE_SKU.fullmatch(sku):
        raise ValidationError("SKU may contain only letters, numbers, hyphens, and underscores.")
    prefix = settings.CLOUDINARY_FOLDER_PREFIX.strip("/")
    return f"{prefix}/{sku}/{suffix}"


def _upload(image_file, public_id):
    validate_image_file(image_file)
    try:
        result = _cloudinary_uploader().upload(
            image_file,
            public_id=public_id,
            overwrite=True,
            invalidate=True,
            resource_type="image",
            type="upload",
            format="webp",
            quality="auto:good",
        )
    except ValidationError:
        raise
    except Exception as exc:
        logger.exception("Cloudinary upload failed for %s", public_id)
        raise ValidationError("Image upload failed. Please try again.") from exc

    secure_url = result.get("secure_url")
    uploaded_public_id = result.get("public_id") or public_id
    if not secure_url or not secure_url.startswith("https://"):
        raise ValidationError("Cloudinary did not return a secure image URL.")
    return uploaded_public_id, secure_url


def upload_product_main_image(product, image_file):
    public_id = _product_public_id(product, "main")
    uploaded_public_id, secure_url = _upload(image_file, public_id)
    product.image_public_id = uploaded_public_id
    product.image_url = secure_url
    # Cloudinary is canonical; remove any stale local-storage reference.
    product.image = None
    product.save(update_fields=["image_public_id", "image_url", "image", "updated_at"])
    return product


def upload_product_gallery_image(product, image_file, sort_order):
    if sort_order is None or int(sort_order) < 0:
        raise ValidationError("sort_order must be zero or greater.")
    sort_order = int(sort_order)
    public_id = _product_public_id(product, f"gallery/{sort_order}")
    uploaded_public_id, secure_url = _upload(image_file, public_id)
    gallery_image = product.images.filter(sort_order=sort_order).order_by("id").first()
    if gallery_image:
        gallery_image.image = None
        gallery_image.image_public_id = uploaded_public_id
        gallery_image.image_url = secure_url
        gallery_image.save(update_fields=["image", "image_public_id", "image_url"])
    else:
        gallery_image = product.images.create(
            sort_order=sort_order,
            image_public_id=uploaded_public_id,
            image_url=secure_url,
        )
    return gallery_image


def delete_cloudinary_image(public_id):
    if not public_id:
        return None
    try:
        return _cloudinary_uploader().destroy(public_id, resource_type="image", invalidate=True)
    except ValidationError:
        raise
    except Exception as exc:
        logger.exception("Cloudinary deletion failed for %s", public_id)
        raise ValidationError("Image deletion failed. Please try again.") from exc
