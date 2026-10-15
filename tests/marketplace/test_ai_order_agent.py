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
            {
                "items": [
                    {"product_id": self.product.id, "quantity": 1},
                    {"product_id": self.product.id, "quantity": 2},
                ]
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)


class AgentGuestCheckoutTests(AgentToolTests):
    def setUp(self):
        super().setUp()
        from django.test import override_settings

        self.enabled = override_settings(
            MARKETPLACE_AI_GUEST_CHECKOUT_ENABLED=True,
            MARKETPLACE_AI_GUEST_CHECKOUT_SHOPS=[self.shop.slug],
        )
        self.enabled.enable()
        self.addCleanup(self.enabled.disable)
        self.prepare_url = f"/api/marketplace/ai/shops/{self.shop.slug}/checkout/prepare/"
        self.confirm_url = f"/api/marketplace/ai/shops/{self.shop.slug}/checkout/confirm/"
        self.payload = {
            "items": [{"product_id": self.product.id, "quantity": 2}],
            "customer_name": "Test Guest",
            "customer_phone": "+31612345678",
            "customer_email": "guest@example.com",
        }

    def prepare(self):
        response = self.client.post(self.prepare_url, self.payload, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        return response.data["confirmation_token"]

    def confirm(self, token, **overrides):
        data = {"confirmation_token": token, "confirmed": True, "terms_accepted": True, **overrides}
        return self.client.post(self.confirm_url, data, format="json")

    def test_prepare_is_non_binding_and_confirmation_is_idempotent(self):
        from unittest.mock import patch

        from apps.marketplace.models import AgentCheckout, Order

        before = Order.objects.count()
        token = self.prepare()
        self.assertEqual(Order.objects.count(), before)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 10)
        with patch("apps.marketplace.services.threading.Thread") as thread:
            with self.captureOnCommitCallbacks(execute=True):
                first = self.confirm(token)
                replay = self.confirm(token)
            self.assertEqual(thread.call_count, 1)
        self.assertEqual(first.status_code, 201, first.data)
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(first.data["order_number"], replay.data["order_number"])
        self.assertTrue(replay.data["replayed"])
        order = Order.objects.get(order_number=first.data["order_number"])
        self.assertIsNone(order.customer_id)
        self.assertEqual(order.payment_status, "unpaid")
        self.assertEqual(order.payment_method, "cash")
        self.assertTrue(order.terms_accepted)
        self.assertEqual(order.total, Decimal("10.00"))
        self.assertEqual(order.invoices.count(), 1)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 8)
        self.assertEqual(Order.objects.count(), before + 1)
        checkout = AgentCheckout.objects.get(token=token)
        self.assertEqual(checkout.payload, {})
        self.assertEqual(checkout.quote, {})

    def test_no_confirmation_or_terms_never_places_order(self):
        from apps.marketplace.models import Order

        token = self.prepare()
        for data in ({"confirmed": False}, {"terms_accepted": False}):
            with self.subTest(data=data):
                self.assertEqual(self.confirm(token, **data).status_code, 400)
        self.assertEqual(
            self.client.post(self.confirm_url, {"confirmation_token": token}, format="json").status_code, 400
        )
        self.assertFalse(Order.objects.exists())

    def test_expired_review_cannot_create_order(self):
        from datetime import timedelta

        from django.utils import timezone

        from apps.marketplace.models import AgentCheckout, Order

        token = self.prepare()
        AgentCheckout.objects.filter(token=token).update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.confirm(token).status_code, 410)
        self.assertFalse(Order.objects.exists())

    def test_price_change_requires_fresh_customer_review(self):
        from apps.marketplace.models import Order

        token = self.prepare()
        self.product.price = Decimal("6.00")
        self.product.save(update_fields=["price"])
        response = self.confirm(token)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "QUOTE_CHANGED")
        self.assertFalse(Order.objects.exists())

    def test_stock_or_acceptance_change_is_revalidated(self):
        token = self.prepare()
        self.product.stock_quantity = 0
        self.product.save(update_fields=["stock_quantity"])
        self.assertEqual(self.confirm(token).status_code, 400)
        self.product.stock_quantity = 10
        self.product.save(update_fields=["stock_quantity"])
        self.shop.settings.accepting_orders = False
        self.shop.settings.save(update_fields=["accepting_orders"])
        self.assertEqual(self.confirm(token).status_code, 400)

    def test_confirm_cannot_mutate_reviewed_details(self):
        token = self.prepare()
        self.assertEqual(self.confirm(token, items=[]).status_code, 400)

    def test_guest_only_pickup_cash_and_strict_fields(self):
        for extra in (
            {"payment_method": "online"},
            {"order_type": "delivery"},
            {"create_account": True},
            {"shop_id": 999},
            {"coupon_code": "FREE"},
            {"customer_phone": "bad"},
        ):
            with self.subTest(extra=extra):
                response = self.client.post(self.prepare_url, {**self.payload, **extra}, format="json")
                self.assertEqual(response.status_code, 400, response.data)

    def test_disabled_by_default_and_shop_scoped(self):
        from django.test import override_settings

        with override_settings(MARKETPLACE_AI_GUEST_CHECKOUT_ENABLED=False):
            self.assertEqual(self.client.post(self.prepare_url, self.payload, format="json").status_code, 404)
        with override_settings(MARKETPLACE_AI_GUEST_CHECKOUT_SHOPS=[]):
            self.assertEqual(self.client.post(self.prepare_url, self.payload, format="json").status_code, 404)

    def test_token_is_unpredictable_and_cannot_cross_shops(self):
        from uuid import uuid4

        from apps.marketplace.models import AgentCheckout

        token = self.prepare()
        self.assertEqual(self.confirm(str(uuid4())).status_code, 404)
        checkout = AgentCheckout.objects.get(token=token)
        self.shop.slug = "different-shop"
        self.shop.save(update_fields=["slug"])
        self.assertEqual(self.confirm(token).status_code, 404)
        self.assertIsNone(checkout.order_id)

    def test_hindi_conversation_uses_existing_english_receipt(self):
        from unittest.mock import patch

        from apps.marketplace.models import Order

        self.payload["language"] = "hi"
        token = self.prepare()
        with patch("apps.marketplace.services.threading.Thread"):
            response = self.confirm(token)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(Order.objects.get(order_number=response.data["order_number"]).language, "en")

    def test_expired_draft_cleanup_and_no_store(self):
        from datetime import timedelta
        from io import StringIO

        from django.core.management import call_command
        from django.utils import timezone

        from apps.marketplace.models import AgentCheckout

        response = self.client.post(self.prepare_url, self.payload, format="json")
        self.assertEqual(response["Cache-Control"], "private, no-store")
        AgentCheckout.objects.filter(token=response.data["confirmation_token"]).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )
        call_command("cleanup_agent_checkouts", stdout=StringIO())
        self.assertFalse(AgentCheckout.objects.exists())

    def test_failed_invoice_rolls_back_order_stock_and_token(self):
        from unittest.mock import patch

        from apps.marketplace.models import AgentCheckout, Order

        token = self.prepare()
        with patch("apps.marketplace.billing.invoice_service.create_invoice", side_effect=RuntimeError("test failure")):
            with self.assertRaises(RuntimeError):
                self.confirm(token)
        self.assertFalse(Order.objects.exists())
        self.assertIsNone(AgentCheckout.objects.get(token=token).order_id)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 10)
        with self.captureOnCommitCallbacks(execute=True), patch("apps.marketplace.services.threading.Thread"):
            self.assertEqual(self.confirm(token).status_code, 201)

    def test_pickup_schedule_requires_real_slot(self):
        from unittest.mock import patch

        from apps.marketplace import ordering

        from .test_order_rules import NOW, PICKUP_HOURS

        self.shop.opening_hours = PICKUP_HOURS
        self.shop.save(update_fields=["opening_hours"])
        with patch("apps.marketplace.ordering.current_time", return_value=NOW):
            missing = self.client.post(self.prepare_url, self.payload, format="json")
            self.assertEqual(missing.status_code, 400)
            self.assertEqual(missing.data["code"], "PICKUP_SLOT_REQUIRED")
            slot = ordering.generate_pickup_slots(self.shop, 0, NOW)[0]
            self.payload["pickup_slot_start"] = slot.start.isoformat()
            token = self.prepare()
            with self.captureOnCommitCallbacks(execute=True), patch("apps.marketplace.services.threading.Thread"):
                confirmed = self.confirm(token)
            self.assertEqual(confirmed.status_code, 201, confirmed.data)
            self.assertEqual(confirmed.data["pickup_slot_start"], slot.start.isoformat())

    def test_selling_format_change_requires_new_review(self):
        from apps.marketplace.models import SellingUnit

        token = self.prepare()
        self.product.selling_unit = SellingUnit.PACK
        self.product.units_per_pack = 4
        self.product.save(update_fields=["selling_unit", "units_per_pack"])
        response = self.confirm(token)
        self.assertEqual(response.status_code, 409)

    def test_other_shop_cannot_use_token(self):
        from django.test import override_settings

        token = self.prepare()
        admin = get_user_model().objects.filter(is_superuser=True).first()
        _, _, other = create_seller_with_shop(
            email="other-agent-seller@example.com",
            password="unused-password-123",
            first_name="Other",
            last_name="Seller",
            business_name="Other Agent Kitchen",
            created_by=admin,
        )
        other.is_approved = True
        other.save(update_fields=["is_approved"])
        with override_settings(MARKETPLACE_AI_GUEST_CHECKOUT_SHOPS=[self.shop.slug, other.slug]):
            response = self.client.post(
                f"/api/marketplace/ai/shops/{other.slug}/checkout/confirm/",
                {"confirmation_token": token, "confirmed": True, "terms_accepted": True},
                format="json",
            )
        self.assertEqual(response.status_code, 404)
