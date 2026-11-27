from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from rest_framework.test import APIClient

from apps.marketplace.models import Product, ShopEnquiry, ShopPage
from apps.marketplace.services import create_seller_with_shop


class ShopPagesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = get_user_model().objects.create_superuser("pages-admin", "pages-admin@example.com", "password123")
        cls.seller, _, cls.shop = create_seller_with_shop(
            email="pages-seller@example.com",
            password="password123",
            first_name="Seller",
            last_name="One",
            business_name="Page shop",
            created_by=cls.admin,
        )
        cls.other, _, cls.other_shop = create_seller_with_shop(
            email="pages-other@example.com",
            password="password123",
            first_name="Other",
            last_name="Seller",
            business_name="Other shop",
            created_by=cls.admin,
        )
        for shop in [cls.shop, cls.other_shop]:
            shop.is_approved = True
            shop.save()
        cls.product = Product.objects.create(
            shop=cls.shop, name="Samosa", slug="samosa", price=Decimal("5"), stock_quantity=20
        )
        cls.foreign = Product.objects.create(shop=cls.other_shop, name="Other", slug="other", price=Decimal("6"))

    def setUp(self):
        self.client = APIClient()
        cache.clear()

    def public_url(self, suffix=""):
        return f"/api/marketplace/shops/{self.shop.slug}/pages/{suffix}"

    def create_page(self, **kwargs):
        fields = {"shop": self.shop, "title": "Friday special", "slug": "friday-special", "is_published": True}
        fields.update(kwargs)
        page = ShopPage.objects.create(**fields)
        page.products.add(self.product)
        return page

    def enquiry_data(self, **kwargs):
        data = {
            "customer_name": "Test customer",
            "email": "customer@example.com",
            "event_date": str(timezone.localdate() + timedelta(days=7)),
            "guests": 20,
            "product_ids": [self.product.id],
            "privacy_accepted": True,
        }
        data.update(kwargs)
        return data

    def test_public_empty_and_only_published_pages_in_configured_order(self):
        self.assertEqual(self.client.get(self.public_url()).json(), [])
        self.create_page(is_published=False)
        self.assertEqual(self.client.get(self.public_url()).json(), [])
        self.assertEqual(self.client.get(self.public_url("friday-special/")).status_code, 404)
        self.create_page(slug="party", title="Party Orders", position=2)
        self.create_page(slug="about", kind="information", position=1)
        self.assertEqual([p["slug"] for p in self.client.get(self.public_url()).json()], ["about", "party"])

    def test_seller_crud_is_scoped_and_drafts_are_private(self):
        self.client.force_authenticate(self.seller)
        response = self.client.post(
            "/api/seller/pages/",
            {"title": "Weekly menu", "slug": "weekly-menu", "product_ids": [self.product.id]},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        page_id = response.data["id"]
        self.assertFalse(response.data["is_published"])
        self.assertEqual(self.client.get(self.public_url()).json(), [])
        response = self.client.patch(
            f"/api/seller/pages/{page_id}/", {"is_published": True, "position": 3}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.data)
        # Authenticated sellers can also browse public pages without serializer errors.
        self.assertEqual(self.client.get(self.public_url()).json()[0]["title"], "Weekly menu")
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get("/api/seller/pages/").json(), [])
        self.assertEqual(self.client.patch(f"/api/seller/pages/{page_id}/", {"title": "Hack"}).status_code, 404)
        self.assertEqual(self.client.delete(f"/api/seller/pages/{page_id}/").status_code, 404)
        self.client.force_authenticate(self.seller)
        self.assertEqual(self.client.delete(f"/api/seller/pages/{page_id}/").status_code, 204)

    def test_permissions_and_validation(self):
        self.assertIn(self.client.get("/api/seller/pages/").status_code, [401, 403])
        self.client.force_authenticate(self.seller)
        for invalid in [
            {"product_ids": [self.foreign.id]},
            {"slug": "Bad_Slug"},
            {"cover_url": "http://example.com/a.png"},
            {"kind": "unknown"},
            {"position": -1},
            {"is_published": True, "product_ids": []},
        ]:
            data = {"title": "Test", "slug": "test", **invalid}
            self.assertEqual(self.client.post("/api/seller/pages/", data, format="json").status_code, 400, invalid)
        page = self.create_page()
        self.assertEqual(
            self.client.post(
                "/api/seller/pages/", {"title": "Duplicate", "slug": page.slug}, format="json"
            ).status_code,
            400,
        )
        self.client.force_authenticate(self.other)
        self.assertEqual(
            self.client.post(
                "/api/seller/pages/", {"title": "Same URL other shop", "slug": page.slug}, format="json"
            ).status_code,
            201,
        )

    def test_public_products_filter_and_shop_approval(self):
        page = self.create_page()
        hidden = Product.objects.create(shop=self.shop, name="Hidden", slug="hidden", price=1, is_approved=False)
        page.products.add(hidden, self.foreign)
        self.assertEqual(self.client.get(self.public_url()).json()[0]["product_ids"], [self.product.id])
        self.shop.is_approved = False
        self.shop.save()
        self.assertEqual(self.client.get(self.public_url()).status_code, 404)
        self.shop.is_approved = True
        self.shop.is_active = False
        self.shop.save()
        self.assertEqual(self.client.get(self.public_url("friday-special/")).status_code, 404)

    def test_quote_persisted_and_only_visible_to_owner_even_after_page_deletion(self):
        page = self.create_page(kind="enquiry")
        response = self.client.post(
            self.public_url(f"{page.slug}/enquiries/"), self.enquiry_data(message="No peanuts"), format="json"
        )
        self.assertEqual(response.status_code, 201, response.data)
        enquiry = ShopEnquiry.objects.get(pk=response.data["id"])
        self.assertEqual(enquiry.shop, self.shop)
        self.assertEqual(enquiry.message, "No peanuts")
        self.assertEqual(enquiry.product_ids, [self.product.id])
        self.assertIn(self.client.get("/api/seller/page-enquiries/").status_code, [401, 403])
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get("/api/seller/page-enquiries/").json(), [])
        self.assertEqual(self.client.get(f"/api/seller/page-enquiries/{enquiry.id}/").status_code, 404)
        self.client.force_authenticate(self.seller)
        self.assertEqual(self.client.get("/api/seller/page-enquiries/").json()[0]["page_title"], page.title)
        page.delete()
        enquiry.refresh_from_db()
        self.assertIsNone(enquiry.page_id)
        self.assertEqual(enquiry.page_title, "Friday special")

    def test_quote_validation_closed_draft_non_enquiry_and_throttle(self):
        page = self.create_page(kind="enquiry")
        url = self.public_url(f"{page.slug}/enquiries/")
        for invalid in [
            {"guests": 0},
            {"event_date": "2000-01-01"},
            {"email": "invalid"},
            {"privacy_accepted": False},
            {"product_ids": [self.foreign.id]},
        ]:
            cache.clear()
            self.assertEqual(
                self.client.post(url, self.enquiry_data(**invalid), format="json").status_code, 400, invalid
            )
        cache.clear()
        for _ in range(5):
            self.assertEqual(self.client.post(url, self.enquiry_data(), format="json").status_code, 201)
        self.assertEqual(self.client.post(url, self.enquiry_data(), format="json").status_code, 429)
        cache.clear()
        page.order_deadline = timezone.now() - timedelta(seconds=1)
        page.save()
        self.assertFalse(self.client.get(self.public_url()).json()[0]["ordering_open"])
        self.assertEqual(self.client.post(url, self.enquiry_data(), format="json").status_code, 400)
        page.order_deadline = None
        page.kind = "menu"
        page.save()
        self.assertEqual(self.client.post(url, self.enquiry_data(), format="json").status_code, 400)
        page.kind = "enquiry"
        page.is_published = False
        page.save()
        self.assertEqual(self.client.post(url, self.enquiry_data(), format="json").status_code, 404)

    def test_quotes_closed_when_seller_pauses_orders(self):
        page = self.create_page(kind="enquiry")
        self.shop.settings.accepting_orders = False
        self.shop.settings.save()
        self.assertEqual(
            self.client.post(
                self.public_url(f"{page.slug}/enquiries/"), self.enquiry_data(), format="json"
            ).status_code,
            400,
        )
