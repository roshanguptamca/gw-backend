"""
Management command: create_marketplace_seed

Creates default test shops, products, categories, coupons and sample orders
for development / QA purposes.

Usage:
    python manage.py create_marketplace_seed
    python manage.py create_marketplace_seed --clear   # drop all marketplace data first
"""

from __future__ import annotations

import random
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.utils.text import slugify

from apps.accounts.models import UserProfile
from apps.marketplace.models import (
    Campaign,
    Category,
    Coupon,
    Order,
    OrderItem,
    Product,
    SellerProfile,
    Shop,
    ShopSettings,
)

User = get_user_model()

# ---------------------------------------------------------------------------
# Seed definitions
# ---------------------------------------------------------------------------

GLOBAL_CATEGORIES = [
    ("Books & Guides", "books-guides"),
    ("Legal Templates", "legal-templates"),
    ("Study Materials", "study-materials"),
    ("Consultation", "consultation"),
    ("Accessories", "accessories"),
]

SHOPS = [
    {
        "user": {
            "username": "seller_immigration",
            "email": "seller1@testshop.dev",
            "first_name": "Ahmed",
            "last_name": "Hassan",
            "password": "TestPass123!",
        },
        "profile": {
            "business_name": "Immigration Expert Store",
            "phone": "+49 30 12345678",
            "city": "Berlin",
            "address": "Musterstraße 12, 10115 Berlin",
        },
        "shop": {
            "name": "Immigration Guides Shop",
            "slug": "immigration-guides-shop",
            "description": (
                "Your one-stop shop for immigration forms, visa guides, "
                "document checklists and expert templates for Germany and Europe."
            ),
            "city": "Berlin",
            "delivery_area": "Germany, Austria, Switzerland",
            "pickup_available": True,
            "delivery_available": True,
        },
        "settings": {
            "currency": "EUR",
            "min_order_amount": Decimal("5.00"),
            "delivery_fee": Decimal("3.50"),
            "local_delivery_fee": Decimal("3.50"),
            "international_delivery_fee": Decimal("8.00"),
            "free_delivery_above": Decimal("30.00"),
            "order_acceptance_mode": "auto",
            "whatsapp_number": "+49 151 11223344",
            "bank_transfer_instructions": "IBAN: DE12 3456 7890 1234 5678 90 | BIC: DEUTDEDB",
        },
        "products": [
            {
                "name": "Germany Visa Application Package",
                "slug": "germany-visa-application-package",
                "description": "Complete step-by-step guide + all required forms for German visa application.",
                "price": Decimal("24.99"),
                "compare_at_price": Decimal("39.99"),
                "stock_quantity": 500,
                "sku": "IGS-001",
                "is_featured": True,
                "category_slug": "books-guides",
            },
            {
                "name": "Blue Card Application Guide",
                "slug": "blue-card-application-guide",
                "description": "Full guide for EU Blue Card application with document checklist and templates.",
                "price": Decimal("19.99"),
                "stock_quantity": 300,
                "sku": "IGS-002",
                "is_featured": False,
                "category_slug": "books-guides",
            },
            {
                "name": "Family Reunion Visa Template Pack",
                "slug": "family-reunion-visa-template-pack",
                "description": "Templates and sample letters for family reunification visa applications.",
                "price": Decimal("14.99"),
                "stock_quantity": 250,
                "sku": "IGS-003",
                "is_featured": True,
                "category_slug": "legal-templates",
            },
            {
                "name": "1-Hour Immigration Consultation",
                "slug": "1-hour-immigration-consultation",
                "description": "Online consultation session with an immigration expert (video call).",
                "price": Decimal("59.99"),
                "stock_quantity": 50,
                "sku": "IGS-004",
                "is_featured": False,
                "category_slug": "consultation",
            },
            {
                "name": "Document Translation Checklist",
                "slug": "document-translation-checklist",
                "description": "Comprehensive checklist for getting your documents translated for German authorities.",
                "price": Decimal("9.99"),
                "stock_quantity": 999,
                "sku": "IGS-005",
                "is_featured": False,
                "category_slug": "legal-templates",
            },
        ],
        "coupons": [
            {
                "code": "WELCOME10",
                "discount_type": "percentage",
                "discount_value": Decimal("10"),
                "min_order_amount": Decimal("15.00"),
                "usage_limit": 100,
            },
            {
                "code": "SAVE5EUR",
                "discount_type": "fixed",
                "discount_value": Decimal("5.00"),
                "min_order_amount": Decimal("25.00"),
                "usage_limit": 50,
            },
        ],
    },
    {
        "user": {
            "username": "seller_study",
            "email": "seller2@testshop.dev",
            "first_name": "Maria",
            "last_name": "Schmidt",
            "password": "TestPass123!",
        },
        "profile": {
            "business_name": "Study Abroad Essentials",
            "phone": "+49 89 98765432",
            "city": "Munich",
            "address": "Schwabing Allee 5, 80333 Munich",
        },
        "shop": {
            "name": "Study Abroad Essentials",
            "slug": "study-abroad-essentials",
            "description": (
                "Everything you need to prepare for studying abroad — "
                "test prep books, university application guides and student planners."
            ),
            "city": "Munich",
            "delivery_area": "Worldwide (digital), Germany (physical)",
            "pickup_available": False,
            "delivery_available": True,
        },
        "settings": {
            "currency": "EUR",
            "min_order_amount": Decimal("0.00"),
            "delivery_fee": Decimal("5.00"),
            "local_delivery_fee": Decimal("5.00"),
            "international_delivery_fee": Decimal("10.00"),
            "free_delivery_above": None,
            "order_acceptance_mode": "auto",
            "whatsapp_number": "+49 175 99887766",
            "bank_transfer_instructions": "IBAN: DE98 7654 3210 9876 5432 10 | BIC: HYVEDEMM",
        },
        "products": [
            {
                "name": "IELTS Complete Preparation Pack",
                "slug": "ielts-complete-preparation-pack",
                "description": "Full IELTS study materials: reading, writing, listening and speaking modules.",
                "price": Decimal("29.99"),
                "compare_at_price": Decimal("49.99"),
                "stock_quantity": 200,
                "sku": "SAE-001",
                "is_featured": True,
                "category_slug": "study-materials",
            },
            {
                "name": "German Language Starter Kit (A1–B1)",
                "slug": "german-language-starter-kit",
                "description": "Digital workbook + audio exercises for beginners to intermediate German learners.",
                "price": Decimal("22.99"),
                "stock_quantity": 350,
                "sku": "SAE-002",
                "is_featured": True,
                "category_slug": "study-materials",
            },
            {
                "name": "University Application Strategy Guide",
                "slug": "university-application-strategy-guide",
                "description": "Step-by-step guide to applying to German and European universities.",
                "price": Decimal("17.99"),
                "stock_quantity": 150,
                "sku": "SAE-003",
                "is_featured": False,
                "category_slug": "books-guides",
            },
            {
                "name": "Student Budget Planner (Printable PDF)",
                "slug": "student-budget-planner-pdf",
                "description": "Monthly budget planner optimised for international students in Germany.",
                "price": Decimal("4.99"),
                "stock_quantity": 9999,
                "sku": "SAE-004",
                "is_featured": False,
                "category_slug": "accessories",
            },
        ],
        "coupons": [
            {
                "code": "STUDY20",
                "discount_type": "percentage",
                "discount_value": Decimal("20"),
                "min_order_amount": Decimal("20.00"),
                "usage_limit": 200,
            },
        ],
    },
    {
        "user": {
            "username": "seller_legal",
            "email": "seller3@testshop.dev",
            "first_name": "Lena",
            "last_name": "Weber",
            "password": "TestPass123!",
        },
        "profile": {
            "business_name": "Legal Doc Templates Hub",
            "phone": "+49 40 55512233",
            "city": "Hamburg",
            "address": "Hafencity Promenade 8, 20457 Hamburg",
        },
        "shop": {
            "name": "Legal Document Templates",
            "slug": "legal-document-templates",
            "description": (
                "Professional legal document templates for expats in Germany — "
                "rental agreements, employment letters, power of attorney and more."
            ),
            "city": "Hamburg",
            "delivery_area": "Germany",
            "pickup_available": True,
            "delivery_available": False,
        },
        "settings": {
            "currency": "EUR",
            "min_order_amount": Decimal("10.00"),
            "delivery_fee": Decimal("5.00"),
            "local_delivery_fee": Decimal("5.00"),
            "international_delivery_fee": Decimal("10.00"),
            "free_delivery_above": None,
            "order_acceptance_mode": "manual",
            "whatsapp_number": "+49 160 44556677",
            "bank_transfer_instructions": "IBAN: DE11 2222 3333 4444 5555 66 | BIC: COMMDEHA",
        },
        "products": [
            {
                "name": "German Rental Contract Template",
                "slug": "german-rental-contract-template",
                "description": "Bilingual (DE/EN) residential rental contract template — German law compliant.",
                "price": Decimal("12.99"),
                "stock_quantity": 1000,
                "sku": "LDT-001",
                "is_featured": True,
                "category_slug": "legal-templates",
            },
            {
                "name": "Employment Confirmation Letter Pack",
                "slug": "employment-confirmation-letter-pack",
                "description": "5 ready-to-use employment confirmation letter templates for visa and banking purposes.",
                "price": Decimal("9.99"),
                "stock_quantity": 1000,
                "sku": "LDT-002",
                "is_featured": False,
                "category_slug": "legal-templates",
            },
            {
                "name": "Power of Attorney Template (Germany)",
                "slug": "power-of-attorney-template-germany",
                "description": "Full power of attorney template for German administrative procedures.",
                "price": Decimal("8.99"),
                "stock_quantity": 800,
                "sku": "LDT-003",
                "is_featured": True,
                "category_slug": "legal-templates",
            },
            {
                "name": "Legal German Glossary & Translation Guide",
                "slug": "legal-german-glossary-guide",
                "description": "Key legal terms in German with plain-language explanations and English translations.",
                "price": Decimal("14.99"),
                "stock_quantity": 500,
                "sku": "LDT-004",
                "is_featured": False,
                "category_slug": "books-guides",
            },
            {
                "name": "Startup Registration Checklist Germany",
                "slug": "startup-registration-checklist-germany",
                "description": "Complete checklist and guide for registering a business in Germany as a foreigner.",
                "price": Decimal("19.99"),
                "compare_at_price": Decimal("29.99"),
                "stock_quantity": 300,
                "sku": "LDT-005",
                "is_featured": True,
                "category_slug": "books-guides",
            },
        ],
        "coupons": [
            {
                "code": "LEGALFIRST",
                "discount_type": "fixed",
                "discount_value": Decimal("3.00"),
                "min_order_amount": Decimal("12.00"),
                "usage_limit": None,
            },
        ],
    },
    # ── Test Shop 99 — general-purpose QA shop ────────────────────────────────
    {
        "user": {
            "username": "seller_test99",
            "email": "seller99@testshop.dev",
            "first_name": "Test",
            "last_name": "Seller",
            "password": "TestPass123!",
        },
        "profile": {
            "business_name": "Test Shop 99 Ltd.",
            "phone": "+31 6 99000099",
            "city": "Amsterdam",
            "address": "Teststraat 99, 1011 AB Amsterdam",
        },
        "shop": {
            "name": "Test Shop 99",
            "slug": "test-shop-99",
            "description": (
                "A general-purpose QA test shop used for development and automated testing. "
                "Contains sample products across multiple categories."
            ),
            "city": "Amsterdam",
            "delivery_area": "Netherlands",
            "pickup_available": True,
            "delivery_available": True,
        },
        "settings": {
            "currency": "EUR",
            "min_order_amount": Decimal("0.00"),
            "delivery_fee": Decimal("5.00"),
            "local_delivery_fee": Decimal("5.00"),
            "international_delivery_fee": Decimal("10.00"),
            "free_delivery_above": Decimal("50.00"),
            "order_acceptance_mode": "auto",
            "whatsapp_number": "+31 6 99000099",
            "bank_transfer_instructions": "IBAN: NL91 ABNA 0417 1643 00 | BIC: ABNANL2A",
        },
        "products": [
            {
                "name": "Sample Product A",
                "slug": "sample-product-a",
                "description": "A sample physical product for QA testing — pickup or delivery.",
                "price": Decimal("9.99"),
                "compare_at_price": Decimal("14.99"),
                "stock_quantity": 100,
                "sku": "TST-001",
                "is_featured": True,
                "category_slug": "accessories",
            },
            {
                "name": "Sample Digital Guide",
                "slug": "sample-digital-guide",
                "description": "A sample digital product for testing checkout flows.",
                "price": Decimal("4.99"),
                "compare_at_price": None,
                "stock_quantity": 9999,
                "sku": "TST-002",
                "is_featured": True,
                "category_slug": "books-guides",
            },
            {
                "name": "Sample Consultation Slot",
                "slug": "sample-consultation-slot",
                "description": "A sample consultation product for testing order notifications.",
                "price": Decimal("19.99"),
                "compare_at_price": Decimal("29.99"),
                "stock_quantity": 50,
                "sku": "TST-003",
                "is_featured": False,
                "category_slug": "consultation",
            },
        ],
        "coupons": [
            {
                "code": "TEST10",
                "discount_type": "percentage",
                "discount_value": Decimal("10"),
                "min_order_amount": Decimal("5.00"),
                "usage_limit": None,
            },
        ],
    },
]

BUYER = {
    "username": "buyer_test",
    "email": "buyer@testshop.dev",
    "first_name": "Test",
    "last_name": "Buyer",
    "password": "TestPass123!",
}


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------


class Command(BaseCommand):
    help = "Populate the database with default test shops, products and sample orders."

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete all existing marketplace data before seeding.",
        )

    def handle(self, *args, **options):
        if options["clear"]:
            self.stdout.write(self.style.WARNING("Clearing existing marketplace data …"))
            Campaign.objects.all().delete()
            Coupon.objects.all().delete()
            Order.objects.all().delete()
            Product.objects.all().delete()
            Category.objects.all().delete()
            ShopSettings.objects.all().delete()
            Shop.objects.all().delete()
            SellerProfile.objects.all().delete()
            self.stdout.write(self.style.SUCCESS("Cleared."))

        # -- Global categories --
        self.stdout.write("Creating global categories …")
        global_cats: dict[str, Category] = {}
        for name, slug in GLOBAL_CATEGORIES:
            cat, _ = Category.objects.get_or_create(
                slug=slug,
                shop=None,
                defaults={"name": name, "is_global": True, "is_active": True},
            )
            global_cats[slug] = cat

        # -- Buyer user --
        self.stdout.write("Creating test buyer …")
        buyer = self._get_or_create_user(BUYER)

        # -- Shops --
        for shop_def in SHOPS:
            self.stdout.write(f"Creating shop: {shop_def['shop']['name']} …")

            user = self._get_or_create_user(shop_def["user"])
            profile, _ = SellerProfile.objects.get_or_create(
                user=user,
                defaults={
                    **shop_def["profile"],
                    "is_active": True,
                    "onboarding_completed": True,
                },
            )

            shop, _ = Shop.objects.get_or_create(
                slug=shop_def["shop"]["slug"],
                defaults={
                    **shop_def["shop"],
                    "owner": user,
                    "seller_profile": profile,
                    "is_active": True,
                    "is_approved": True,
                },
            )

            ShopSettings.objects.get_or_create(shop=shop, defaults=shop_def["settings"])

            # -- Products --
            products_created: list[Product] = []
            for prod_def in shop_def["products"]:
                cat_slug = prod_def.pop("category_slug")
                category = global_cats.get(cat_slug)
                product, _ = Product.objects.get_or_create(
                    shop=shop,
                    slug=prod_def["slug"],
                    defaults={
                        **prod_def,
                        "category": category,
                        "is_active": True,
                        "is_approved": True,
                    },
                )
                prod_def["category_slug"] = cat_slug  # restore
                products_created.append(product)

            # -- Coupons --
            for coupon_def in shop_def.get("coupons", []):
                Coupon.objects.get_or_create(
                    shop=shop,
                    code=coupon_def["code"],
                    defaults={**coupon_def, "active": True},
                )

            # -- Sample campaign --
            if products_created:
                Campaign.objects.get_or_create(
                    shop=shop,
                    title=f"Summer Launch – {shop.name}",
                    defaults={
                        "description": "Introducing our best products for this season!",
                        "starts_at": timezone.now(),
                        "ends_at": timezone.now() + timezone.timedelta(days=30),
                        "active": True,
                        "featured_product": products_created[0],
                    },
                )

            # -- Sample orders --
            self._create_sample_orders(shop, buyer, products_created)

        self.stdout.write(self.style.SUCCESS("\n✅  Seed complete!"))
        self.stdout.write(
            "\nTest credentials:\n"
            "  Seller 1 : seller1@testshop.dev  / TestPass123!\n"
            "  Seller 2 : seller2@testshop.dev  / TestPass123!\n"
            "  Seller 3 : seller3@testshop.dev  / TestPass123!\n"
            "  Buyer    : buyer@testshop.dev    / TestPass123!\n"
        )

    # ------------------------------------------------------------------ helpers

    def _get_or_create_user(self, user_def: dict) -> "User":
        user, created = User.objects.get_or_create(
            email=user_def["email"],
            defaults={
                "username": user_def["username"],
                "first_name": user_def["first_name"],
                "last_name": user_def["last_name"],
                "is_active": True,
            },
        )
        if created:
            user.set_password(user_def["password"])
            user.save(update_fields=["password"])
        # Ensure email is confirmed so test users can log in immediately
        UserProfile.objects.filter(user=user).update(email_confirmed=True)
        return user

    def _create_sample_orders(self, shop: Shop, buyer, products: list):
        statuses = [
            Order.STATUS_PENDING,
            Order.STATUS_ACCEPTED,
            Order.STATUS_COMPLETED,
        ]
        for idx, status in enumerate(statuses):
            if not products:
                break
            product = random.choice(products)
            qty = random.randint(1, 3)
            unit_price = product.price
            line_total = unit_price * qty
            order_number = f"ORD-SEED-{shop.id or 0}-{idx + 1:03d}"

            if Order.objects.filter(order_number=order_number).exists():
                continue

            order = Order.objects.create(
                shop=shop,
                customer=buyer,
                order_number=order_number,
                customer_name=f"{buyer.first_name} {buyer.last_name}",
                customer_email=buyer.email,
                customer_phone="+49 152 00000000",
                order_type="delivery",
                status=status,
                payment_method="cash",
                payment_status="unpaid" if status == Order.STATUS_PENDING else "paid",
                subtotal=line_total,
                discount_total=Decimal("0"),
                delivery_fee=shop.settings.delivery_fee if hasattr(shop, "settings") else Decimal("0"),
                total=line_total + (shop.settings.delivery_fee if hasattr(shop, "settings") else Decimal("0")),
                customer_note="Seed order for testing",
            )
            OrderItem.objects.create(
                order=order,
                product=product,
                product_name=product.name,
                unit_price=unit_price,
                quantity=qty,
                line_total=line_total,
            )
