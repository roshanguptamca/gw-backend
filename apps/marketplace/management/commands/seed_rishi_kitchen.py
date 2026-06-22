"""
Management command: seed_rishi_kitchen

Creates the default Rishi Kitchen seller shop for GuideWisey Marketplace.

Features:
  - Fully idempotent — safe to run multiple times (get_or_create / update_or_create)
  - Production-safe — no data destruction, no hardcoded passwords
  - Password sourced from RISHI_KITCHEN_PASSWORD env var; auto-generated if absent
  - Downloads royalty-free product images from Unsplash (no watermark, free license)

Usage:
    python manage.py seed_rishi_kitchen
"""
from __future__ import annotations

import logging
import os
import secrets
import string
import urllib.request
try:
    import requests as _requests
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand

from apps.accounts.models import UserProfile
from apps.marketplace.models import (
    Category,
    Product,
    ProductImage,
    SellerProfile,
    Shop,
    ShopSettings,
)

User = get_user_model()
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SELLER_EMAIL = "guptarati024@gmail.com"
SELLER_USERNAME = "guptarati024@gmail.com"
SELLER_FIRST_NAME = "Rishi"
SELLER_LAST_NAME = "Kitchen"

SHOP_SLUG = "rishi-kitchen"
SHOP_NAME = "Rishi Kitchen"
SHOP_DESCRIPTION = (
    "Homemade Indian snacks, sweets and traditional food prepared with care "
    "using authentic recipes. Freshly prepared for pickup or delivery."
)

ALLERGEN_NOTE = "Please contact seller for allergen information."
DEFAULT_STOCK = 20

# ---------------------------------------------------------------------------
# Category definitions  (shop-specific, not global)
# ---------------------------------------------------------------------------

CATEGORIES = [
    {"name": "Snacks",     "slug": "snacks"},
    {"name": "Sweets",     "slug": "sweets"},
    {"name": "Fresh Food", "slug": "fresh-food"},
]

# ---------------------------------------------------------------------------
# Royalty-free Unsplash image URLs  (no watermark, Unsplash free license)
# Images are downloaded once at seed time and stored in Django media storage.
# ---------------------------------------------------------------------------
_BASE = "https://images.unsplash.com"
PRODUCT_IMAGES: dict[str, str] = {
    # Snacks
    "namak-para-saloni":    f"{_BASE}/photo-1513558161293-cdaf765ed2fd?w=600&q=85",
    "samosa":               f"{_BASE}/photo-1601050690597-df0568f70950?w=600&q=85",
    "vada-pav":             f"{_BASE}/photo-1606491956689-2ea866880c84?w=600&q=85",
    "murmura-namkeen-250g": f"{_BASE}/photo-1571506165871-ee72a35bc9d4?w=600&q=85",
    "murmura-namkeen-500g": f"{_BASE}/photo-1571506165871-ee72a35bc9d4?w=600&q=85",
    # Sweets
    "gulab-jamun":          f"{_BASE}/photo-1627308595229-7830a5c91f9f?w=600&q=85",
    "gujia-rava-250g":      f"{_BASE}/photo-1587314168485-3236d6710814?w=600&q=85",
    "gujia-rava-500g":      f"{_BASE}/photo-1587314168485-3236d6710814?w=600&q=85",
    "gujia-mava-250g":      f"{_BASE}/photo-1590080875515-8a3a8dc5735e?w=600&q=85",
    "gujia-mava-500g":      f"{_BASE}/photo-1590080875515-8a3a8dc5735e?w=600&q=85",
    # Fresh Food
    "idli":                 f"{_BASE}/photo-1555126634-323283e090fa?w=600&q=85",
    "minapa-garelu":        f"{_BASE}/photo-1551024601-bec78aea704b?w=600&q=85",
}

# ---------------------------------------------------------------------------
# Product definitions
# ---------------------------------------------------------------------------

PRODUCTS = [
    # ── Snacks ────────────────────────────────────────────────────────────
    {
        "name": "Namak Para / Saloni",
        "slug": "namak-para-saloni",
        "category": "snacks",
        "description": "Crispy homemade Indian savoury snack, perfect with tea.",
        "price": Decimal("5.00"),
        "weight_grams": 500,
        "sku": "RK-S-001",
        "is_featured": True,
    },
    {
        "name": "Samosa",
        "slug": "samosa",
        "category": "snacks",
        "description": "Crispy pastry filled with traditional Indian spiced potato filling. 2 pieces.",
        "price": Decimal("5.00"),
        "sku": "RK-S-002",
    },
    {
        "name": "Vada Pav",
        "slug": "vada-pav",
        "category": "snacks",
        "description": "Popular Indian street food with spiced potato fritter served in a bun. 2 pieces.",
        "price": Decimal("5.00"),
        "sku": "RK-S-003",
    },
    {
        "name": "Murmura Namkeen 250g",
        "slug": "murmura-namkeen-250g",
        "category": "snacks",
        "description": "Light and crunchy puffed rice snack with traditional spices.",
        "price": Decimal("5.00"),
        "weight_grams": 250,
        "sku": "RK-S-004",
    },
    {
        "name": "Murmura Namkeen 500g",
        "slug": "murmura-namkeen-500g",
        "category": "snacks",
        "description": "Family-size puffed rice snack mix with authentic Indian flavour.",
        "price": Decimal("10.00"),
        "weight_grams": 500,
        "sku": "RK-S-005",
    },
    # ── Sweets ────────────────────────────────────────────────────────────
    {
        "name": "Gulab Jamun",
        "slug": "gulab-jamun",
        "category": "sweets",
        "description": "Soft milk-based sweet dumplings soaked in aromatic sugar syrup.",
        "price": Decimal("10.00"),
        "weight_grams": 500,
        "sku": "RK-W-001",
        "is_featured": True,
    },
    {
        "name": "Gujia Rava 250g",
        "slug": "gujia-rava-250g",
        "category": "sweets",
        "description": "Traditional festive sweet pastry filled with roasted semolina.",
        "price": Decimal("5.00"),
        "weight_grams": 250,
        "sku": "RK-W-002",
    },
    {
        "name": "Gujia Rava 500g",
        "slug": "gujia-rava-500g",
        "category": "sweets",
        "description": "Family-size festive sweet pastry filled with roasted semolina.",
        "price": Decimal("10.00"),
        "weight_grams": 500,
        "sku": "RK-W-003",
    },
    {
        "name": "Gujia Mava 250g",
        "slug": "gujia-mava-250g",
        "category": "sweets",
        "description": "Rich traditional Gujia filled with sweetened milk solids.",
        "price": Decimal("10.00"),
        "weight_grams": 250,
        "sku": "RK-W-004",
    },
    {
        "name": "Gujia Mava 500g",
        "slug": "gujia-mava-500g",
        "category": "sweets",
        "description": "Premium festive Gujia with rich mava filling.",
        "price": Decimal("18.00"),
        "weight_grams": 500,
        "sku": "RK-W-005",
    },
    # ── Fresh Food ────────────────────────────────────────────────────────
    {
        "name": "Idli",
        "slug": "idli",
        "category": "fresh-food",
        "description": "Soft steamed South Indian rice cakes served fresh. 2 pieces.",
        "price": Decimal("5.00"),
        "sku": "RK-F-001",
        "is_featured": True,
    },
    {
        "name": "Minapa Garelu",
        "slug": "minapa-garelu",
        "category": "fresh-food",
        "description": "Traditional South Indian lentil doughnuts, crispy outside and soft inside. 2 pieces.",
        "price": Decimal("5.00"),
        "sku": "RK-F-002",
    },
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _generate_password(length: int = 16) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _download_image(url: str, filename: str) -> "ContentFile | None":
    """Download an image from a public URL and return a Django ContentFile.

    Prefers the `requests` library (bundled with Django, handles SSL via certifi).
    Falls back to urllib with system SSL context if requests is unavailable.
    Returns None on any error so the seed continues gracefully.
    """
    ua = (
        "GuideWisey-marketplace-seed/1.0 "
        "(https://guidewisey.com; marketplace@guidewisey.com)"
    )
    try:
        if _HAS_REQUESTS:
            resp = _requests.get(url, headers={"User-Agent": ua}, timeout=15)
            resp.raise_for_status()
            return ContentFile(resp.content, name=filename)
        else:
            import ssl
            ctx = ssl.create_default_context()
            req = urllib.request.Request(
                url, headers={"User-Agent": ua, "Accept": "image/*"}
            )
            with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
                return ContentFile(resp.read(), name=filename)
    except Exception as exc:
        logger.warning("Could not download image %s: %s", url, exc)
        return None


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------

class Command(BaseCommand):
    help = "Seed Rishi Kitchen shop for GuideWisey Marketplace (idempotent)"

    def _log(self, msg: str, style=None) -> None:
        styled = style(msg) if style else msg
        self.stdout.write(styled)
        logger.info(msg)

    def handle(self, *args, **options):  # noqa: ARG002
        self._log("=" * 60)
        self._log("  GuideWisey — Rishi Kitchen Seed", self.style.HTTP_INFO)
        self._log("=" * 60)

        # ── 1. Seller account ────────────────────────────────────────────
        self._log("\n[1/6] Creating seller account...")
        password = os.environ.get("RISHI_KITCHEN_PASSWORD")
        generated = False
        if not password:
            password = _generate_password()
            generated = True

        user, created = User.objects.get_or_create(
            email=SELLER_EMAIL,
            defaults={
                "username": SELLER_USERNAME,
                "first_name": SELLER_FIRST_NAME,
                "last_name": SELLER_LAST_NAME,
                "is_active": True,
            },
        )
        if created:
            user.set_password(password)
            user.save(update_fields=["password"])
            self._log(f"  + User created: {SELLER_EMAIL}", self.style.SUCCESS)
        else:
            self._log(f"  -> User already exists: {SELLER_EMAIL}")

        # Ensure email confirmed so seller can log in immediately
        UserProfile.objects.update_or_create(
            user=user,
            defaults={"email_confirmed": True},
        )

        if generated:
            self._log(
                f"\n  WARNING: No RISHI_KITCHEN_PASSWORD env var found.\n"
                f"  Generated password: {password}\n"
                f"  Store this securely — it will not be shown again.\n",
                self.style.WARNING,
            )

        # ── 2. Seller profile ────────────────────────────────────────────
        self._log("\n[2/6] Creating seller profile...")
        profile, created = SellerProfile.objects.get_or_create(
            user=user,
            defaults={
                "business_name": SHOP_NAME,
                "city": "Netherlands",
                "is_active": True,
                "onboarding_completed": True,
            },
        )
        status = "+ SellerProfile created" if created else "-> SellerProfile already exists"
        self._log(f"  {status}", self.style.SUCCESS if created else None)

        # ── 3. Shop ──────────────────────────────────────────────────────
        self._log("\n[3/6] Creating shop...")
        shop, created = Shop.objects.get_or_create(
            slug=SHOP_SLUG,
            defaults={
                "owner": user,
                "seller_profile": profile,
                "name": SHOP_NAME,
                "description": SHOP_DESCRIPTION,
                "city": "Netherlands",
                "pickup_available": True,
                "delivery_available": True,
                "is_active": True,
                "is_approved": True,
            },
        )
        status = f"+ Shop created: {SHOP_NAME}" if created else f"-> Shop already exists: {SHOP_NAME}"
        self._log(f"  {status}", self.style.SUCCESS if created else None)

        # ── 4. Shop settings ─────────────────────────────────────────────
        self._log("\n[4/6] Creating shop settings...")
        settings_obj, created = ShopSettings.objects.get_or_create(
            shop=shop,
            defaults={
                "currency": "EUR",
                "local_delivery_fee": Decimal("5.00"),
                "international_delivery_fee": Decimal("10.00"),
                "free_delivery_above": None,
                "delivery_fee": Decimal("5.00"),
                "min_order_amount": Decimal("0.00"),
                "order_acceptance_mode": ShopSettings.ORDER_ACCEPTANCE_MANUAL,
                "delivery_notes": (
                    "Pickup is free. Netherlands delivery EUR 5. "
                    "International delivery EUR 10. "
                    "All fees are configurable from Seller Settings."
                ),
            },
        )
        status = "+ ShopSettings created" if created else "-> ShopSettings already exists"
        self._log(f"  {status}", self.style.SUCCESS if created else None)

        # ── 5. Categories ────────────────────────────────────────────────
        self._log("\n[5/6] Creating categories...")
        category_map: dict[str, Category] = {}
        for cat_def in CATEGORIES:
            cat, created = Category.objects.get_or_create(
                shop=shop,
                slug=cat_def["slug"],
                defaults={
                    "name": cat_def["name"],
                    "is_global": False,
                    "is_active": True,
                },
            )
            category_map[cat_def["slug"]] = cat
            status = "+ Created" if created else "-> Exists "
            self._log(f"  {status}: {cat_def['name']}", self.style.SUCCESS if created else None)

        # ── 6. Products + images ─────────────────────────────────────────
        self._log(f"\n[6/6] Creating {len(PRODUCTS)} products + downloading images...")
        created_count = 0
        img_ok = 0
        img_skip = 0

        for prod_def in PRODUCTS:
            slug = prod_def["slug"]
            category = category_map.get(prod_def["category"])

            product_fields = {
                "name": prod_def["name"],
                "description": prod_def["description"],
                "price": prod_def["price"],
                "allergens": ALLERGEN_NOTE,
                "stock_quantity": DEFAULT_STOCK,
                "sku": prod_def.get("sku", ""),
                "category": category,
                "is_active": True,
                "is_approved": True,
                "is_featured": prod_def.get("is_featured", False),
                "weight_grams": prod_def.get("weight_grams"),
            }

            product, created = Product.objects.get_or_create(
                shop=shop,
                slug=slug,
                defaults=product_fields,
            )

            if created:
                created_count += 1
                self._log(f"  + {product.name} (EUR {product.price})", self.style.SUCCESS)
            else:
                self._log(f"  -> Exists: {product.name}")

            # Download + attach image if product has none yet
            image_url = PRODUCT_IMAGES.get(slug)
            if image_url and not product.image:
                filename = f"rk-{slug}.jpg"
                self._log(f"     Downloading image for {product.name}...")
                img_file = _download_image(image_url, filename)
                if img_file:
                    product.image.save(filename, img_file, save=True)
                    img_ok += 1
                    self._log(f"     + Image saved: {filename}", self.style.SUCCESS)
                    # Create ProductImage gallery entry
                    ProductImage.objects.get_or_create(
                        product=product,
                        alt_text=product.name,
                        defaults={"image": product.image.name, "sort_order": 0},
                    )
                else:
                    img_skip += 1
                    self._log(
                        f"     WARNING: Image download failed for {product.name} — skipped.",
                        self.style.WARNING,
                    )
            elif product.image:
                img_ok += 1
                self._log(f"     -> Image already set: {product.image.name}")
            else:
                img_skip += 1

        # ── Summary ──────────────────────────────────────────────────────
        self._log("\n" + "=" * 60)
        self._log("  Rishi Kitchen seed complete!", self.style.SUCCESS)
        self._log("=" * 60)
        self._log(
            f"\n  Shop     : {SHOP_NAME}\n"
            f"  Slug     : {SHOP_SLUG}\n"
            f"  Seller   : {SELLER_EMAIL}\n"
            f"  Products : {Product.objects.filter(shop=shop).count()} total "
            f"({created_count} newly created)\n"
            f"  Images   : {img_ok} attached, {img_skip} skipped\n"
            f"  Pickup   : Free\n"
            f"  Delivery : EUR 5 Netherlands / EUR 10 International\n"
            f"\n  INFO: Delivery fees are configurable in Seller Settings.\n"
            f"  INFO: Images sourced from Unsplash (royalty-free, no watermark).\n"
            f"  INFO: Replace with seller-owned photos before going live.\n"
        )
