"""Read-only AI ordering endpoint tests."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.marketplace.models import Product
from apps.marketplace.services import create_seller_with_shop


class AgentToolTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        admin = get_user_model().objects.create_superuser(
            username="ai-admin@example.com",
            email="ai-admin@example.com",
            password="unused-password-123",
        )
        _, _, self.shop = create_seller_with_shop(
            email="ai-seller@example.com",
            password="unused-password-123",
            first_name="AI",
            last_name="Seller",
            business_name="Agent Test Kitchen",
            created_by=admin,
        )
        self.shop.is_approved = True
        self.shop.pickup_available = True
        self.shop.save(update_fields=["is_approved", "pickup_available"])
        self.product = Product.objects.create(
            shop=self.shop,
            name="Samosa",
            slug="samosa",
            price=Decimal("5.00"),
            stock_quantity=10,
            is_active=True,
            is_approved=True,
        )
        self.hidden = Product.objects.create(
            shop=self.shop,
            name="Hidden",
            slug="hidden",
            price=Decimal("8.00"),
            stock_quantity=10,
            is_active=True,
            is_approved=False,
        )
        self.menu_url = f"/api/marketplace/ai/shops/{self.shop.slug}/menu/"
        self.quote_url = f"/api/marketplace/ai/shops/{self.shop.slug}/quote/"

    def test_menu_only_returns_public_products(self):
        response = self.client.get(self.menu_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual([p["name"] for p in response.data["items"]], ["Samosa"])
        self.assertEqual(response.data["items"][0]["price_eur"], "5.00")

    def test_quote_uses_db_prices_and_does_not_place_order(self):
        from apps.marketplace.models import Order

        before = Order.objects.count()
        response = self.client.post(
            self.quote_url,
            {"items": [{"product_id": self.product.id, "quantity": 2}]},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["subtotal_eur"], "10.00")
        self.assertEqual(Order.objects.count(), before)

    def test_quote_rejects_hidden_product(self):
        response = self.client.post(
            self.quote_url,
            {"items": [{"product_id": self.hidden.id, "quantity": 1}]},
            format="json",
        )
        self.assertFalse(response.data["valid_for_checkout"])
        self.assertEqual(response.data["errors"][0]["code"], "NOT_AVAILABLE")

    def test_quote_rejects_insufficient_stock(self):
        response = self.client.post(
            self.quote_url,
            {"items": [{"product_id": self.product.id, "quantity": 11}]},
            format="json",
        )
        self.assertFalse(response.data["valid_for_checkout"])
        self.assertIn("INSUFFICIENT_STOCK", [e["code"] for e in response.data["errors"]])

    def test_quote_rejects_duplicate_lines(self):
        response = self.client.post(
            self.quote_url,
            {"items": [
                {"product_id": self.product.id, "quantity": 1},
                {"product_id": self.product.id, "quantity": 2},
            ]}, format="json",
        )
        self.assertEqual(response.status_code, 400)
