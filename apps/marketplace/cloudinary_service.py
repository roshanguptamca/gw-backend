import re

from django.conf import settings
from django.core.exceptions import ValidationError

from apps.common.cloudinary_service import delete_image as _shared_delete_image
from apps.common.cloudinary_service import upload_image as _shared_upload_image
from apps.common.cloudinary_service import validate_image_file

ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
ALLOWED_IMAGE_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
PRODUCT_IMAGE_MAX_BYTES = 2 * 1024 * 1024
BANNER_IMAGE_MAX_BYTES = 5 * 1024 * 1024
SHOP_LOGO_MAX_BYTES = PRODUCT_IMAGE_MAX_BYTES
SHOP_BANNER_MAX_BYTES = BANNER_IMAGE_MAX_BYTES
_SAFE_SKU = re.compile(r"^[A-Za-z0-9_-]+$")
_SAFE_SLUG = re.compile(r"^[a-z0-9_-]+$")

__all__ = [
    "validate_image_file",
    "upload_product_main_image",
    "upload_product_gallery_image",
    "upload_shop_logo",
    "upload_shop_banner",
    "delete_cloudinary_image",
]


def _product_public_id(product, suffix):
    sku = (product.sku or "").strip()
    if not sku:
        raise ValidationError("A SKU is required before uploading product images.")
    if not _SAFE_SKU.fullmatch(sku):
        raise ValidationError("SKU may contain only letters, numbers, hyphens, and underscores.")
    prefix = settings.CLOUDINARY_FOLDER_PREFIX.strip("/")
    return f"{prefix}/{sku}/{suffix}"


def _shop_public_id(shop, suffix):
    slug = (shop.slug or "").strip()
    if not slug:
        raise ValidationError("A shop slug is required before uploading shop images.")
    if not _SAFE_SLUG.fullmatch(slug):
        raise ValidationError("Shop slug may contain only lowercase letters, numbers, hyphens, and underscores.")
    product_prefix = settings.CLOUDINARY_FOLDER_PREFIX.strip("/")
    root_prefix, separator, leaf = product_prefix.rpartition("/")
    if leaf == "products":
        shop_prefix = f"{root_prefix}/shops" if separator else "shops"
    else:
        shop_prefix = f"{product_prefix}/shops"
    return f"{shop_prefix}/{slug}/{suffix}"


def _upload(image_file, public_id, *, max_bytes=PRODUCT_IMAGE_MAX_BYTES):
    uploaded_public_id, secure_url, _eager = _shared_upload_image(image_file, public_id, max_bytes=max_bytes)
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


def upload_shop_logo(shop, image_file):
    public_id = _shop_public_id(shop, "logo")
    uploaded_public_id, secure_url = _upload(image_file, public_id, max_bytes=SHOP_LOGO_MAX_BYTES)
    shop.logo_public_id = uploaded_public_id
    shop.logo_url = secure_url
    shop.logo = None
    shop.save(update_fields=["logo_public_id", "logo_url", "logo", "updated_at"])
    return shop


def upload_shop_banner(shop, image_file):
    public_id = _shop_public_id(shop, "banner")
    uploaded_public_id, secure_url = _upload(image_file, public_id, max_bytes=SHOP_BANNER_MAX_BYTES)
    shop.banner_public_id = uploaded_public_id
    shop.banner_url = secure_url
    shop.banner_image = None
    shop.save(update_fields=["banner_public_id", "banner_url", "banner_image", "updated_at"])
    return shop


def delete_cloudinary_image(public_id):
    return _shared_delete_image(public_id, resource_type="image")
