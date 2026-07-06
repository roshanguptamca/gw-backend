from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase

from rest_framework import status
from rest_framework.test import APIClient

from apps.marketplace.models import Coupon, Order, OrderEmailLog, Product, Shop
from apps.marketplace.services import create_seller_with_shop

User = get_user_model()


class MarketplaceAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_superuser(
            username="admin@example.com",
            email="admin@example.com",
            password="adminpass123",
        )
        self.seller_user, self.seller_profile, self.shop = create_seller_with_shop(
            email="seller@example.com",
            password="sellerpass123",
            first_name="Seller",
            last_name="One",
            business_name="Seller One",
            created_by=self.admin,
        )
        self.other_user, self.other_profile, self.other_shop = create_seller_with_shop(
            email="other@example.com",
            password="sellerpass123",
            first_name="Seller",
            last_name="Two",
            business_name="Seller Two",
            created_by=self.admin,
        )
        for shop in (self.shop, self.other_shop):
            shop.is_approved = True
            shop.delivery_available = True
            shop.save()
        self.product = Product.objects.create(
            shop=self.shop,
            name="Masala Namkeen",
            slug="masala-namkeen",
            price=Decimal("4.99"),
            stock_quantity=10,
            is_active=True,
            is_approved=True,
        )
        self.hidden_product = Product.objects.create(
            shop=self.shop,
            name="Hidden",
            slug="hidden",
            price=Decimal("3.00"),
            stock_quantity=10,
            is_active=True,
            is_approved=False,
        )
        self.other_product = Product.objects.create(
            shop=self.other_shop,
            name="Other",
            slug="other",
            price=Decimal("9.00"),
            stock_quantity=10,
            is_active=True,
            is_approved=True,
        )

    def test_admin_can_create_seller_with_shop(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post(
            "/api/admin/sellers/",
            {
                "email": "fresh@example.com",
                "password": "freshpass123",
                "first_name": "Fresh",
                "last_name": "Seller",
                "business_name": "Fresh Foods",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(email="fresh@example.com")
        self.assertFalse(user.is_superuser)
        self.assertFalse(user.is_staff)
        self.assertTrue(hasattr(user, "seller_profile"))
        self.assertTrue(hasattr(user.seller_profile, "shop"))

    def test_public_products_only_include_active_approved_records(self):
        response = self.client.get("/api/marketplace/products/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        names = {item["name"] for item in response.data}
        self.assertIn("Masala Namkeen", names)
        self.assertNotIn("Hidden", names)

    def test_seller_products_are_scoped_to_own_shop(self):
        self.client.force_authenticate(self.seller_user)
        response = self.client.get("/api/seller/products/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        product_ids = {item["id"] for item in response.data}
        self.assertIn(self.product.id, product_ids)
        self.assertNotIn(self.other_product.id, product_ids)

        response = self.client.patch(
            f"/api/seller/products/{self.other_product.id}/",
            {"name": "Hijack"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_order_creation_calculates_totals_and_reduces_stock(self):
        Coupon.objects.create(
            shop=self.shop,
            code="WELCOME10",
            discount_type=Coupon.DISCOUNT_PERCENTAGE,
            discount_value=Decimal("10.00"),
            active=True,
        )
        response = self.client.post(
            "/api/orders/",
            {
                "shop_id": self.shop.id,
                "customer_name": "Rohan",
                "customer_email": "rohan@example.com",
                "customer_phone": "+31600000000",
                "order_type": "pickup",
                "payment_method": "cash",
                "coupon_code": "WELCOME10",
                "items": [{"product_id": self.product.id, "quantity": 2}],
                "terms_accepted": True,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Decimal(response.data["subtotal"]), Decimal("9.98"))
        self.assertEqual(Decimal(response.data["discount_total"]), Decimal("1.00"))
        self.assertEqual(Decimal(response.data["total"]), Decimal("8.98"))
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 8)

    def test_seller_order_status_transition_is_validated(self):
        order = Order.objects.create(
            shop=self.shop,
            order_number="GWTEST001",
            customer_name="Rohan",
            customer_phone="+31600000000",
            subtotal=Decimal("4.99"),
            total=Decimal("4.99"),
            status=Order.STATUS_PENDING,
        )
        self.client.force_authenticate(self.seller_user)
        bad = self.client.patch(f"/api/seller/orders/{order.id}/status/", {"status": "completed"}, format="json")
        self.assertEqual(bad.status_code, status.HTTP_400_BAD_REQUEST)
        good = self.client.patch(f"/api/seller/orders/{order.id}/status/", {"status": "accepted"}, format="json")
        self.assertEqual(good.status_code, status.HTTP_200_OK)
        self.assertEqual(good.data["status"], "accepted")

    def test_public_shop_slug_lookup_and_products_action(self):
        detail = self.client.get(f"/api/marketplace/shops/{self.shop.slug}/")
        products = self.client.get(f"/api/marketplace/shops/{self.shop.slug}/products/")

        self.assertEqual(detail.status_code, status.HTTP_200_OK)
        self.assertEqual(detail.data["slug"], self.shop.slug)
        self.assertEqual(products.status_code, status.HTTP_200_OK)
        self.assertEqual([item["id"] for item in products.data], [self.product.id])

    def test_session_cart_add_update_and_remove(self):
        added = self.client.post(
            "/api/marketplace/cart/items/",
            {"product_id": self.product.id, "quantity": 2},
            format="json",
        )
        self.assertEqual(added.status_code, status.HTTP_200_OK)
        self.assertEqual(added.data["items"][0]["quantity"], 2)

        updated = self.client.patch(
            f"/api/marketplace/cart/items/{self.product.id}/",
            {"quantity": 3},
            format="json",
        )
        self.assertEqual(updated.data["items"][0]["quantity"], 3)

        removed = self.client.delete(f"/api/marketplace/cart/items/{self.product.id}/")
        self.assertEqual(removed.data["items"], [])

    def test_marketplace_order_request_alias_links_authenticated_buyer(self):
        buyer = User.objects.create_user(
            username="checkout-buyer@example.com",
            email="checkout-buyer@example.com",
            password="buyerpass123",
        )
        self.client.force_authenticate(buyer)
        response = self.client.post(
            "/api/marketplace/orders/",
            {
                "shop_id": self.shop.id,
                "customer_name": "Checkout Buyer",
                "customer_email": buyer.email,
                "customer_phone": "+31612345678",
                "delivery_address": "",
                "order_type": "pickup",
                "payment_method": "cash",
                "customer_note": "Please call on arrival.",
                "items": [{"product_id": self.product.id, "quantity": 1}],
                "terms_accepted": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["customer"], buyer.id)
        detail = self.client.get(f"/api/marketplace/orders/{response.data['id']}/")
        self.assertEqual(detail.status_code, status.HTTP_200_OK)
        self.assertEqual(detail.data["order_number"], response.data["order_number"])

    def test_marketplace_order_detail_and_seller_alias_are_protected(self):
        order = Order.objects.create(
            shop=self.shop,
            order_number="GWALIAS001",
            customer_name="Guest",
            customer_phone="+31612345678",
            subtotal=Decimal("4.99"),
            total=Decimal("4.99"),
        )
        detail = self.client.get(f"/api/marketplace/orders/{order.id}/")
        seller_list = self.client.get("/api/marketplace/seller/orders/")
        self.assertEqual(detail.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(seller_list.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(self.seller_user)
        seller_list = self.client.get("/api/marketplace/seller/orders/")
        self.assertEqual(seller_list.status_code, status.HTTP_200_OK)
        self.assertEqual([item["id"] for item in seller_list.data], [order.id])


class BuyerOrderAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_superuser(
            username="admin2@example.com",
            email="admin2@example.com",
            password="adminpass123",
        )
        self.seller_user, self.seller_profile, self.shop = create_seller_with_shop(
            email="seller2@example.com",
            password="sellerpass123",
            first_name="Seller",
            last_name="Two",
            business_name="Buyer Test Shop",
            created_by=self.admin,
        )
        self.shop.is_approved = True
        self.shop.save()
        from apps.marketplace.models import ShopSettings

        ShopSettings.objects.get_or_create(shop=self.shop)

        self.buyer = User.objects.create_user(
            username="buyer@example.com",
            email="buyer@example.com",
            password="buyerpass123",
        )
        self.other_buyer = User.objects.create_user(
            username="other_buyer@example.com",
            email="other_buyer@example.com",
            password="buyerpass123",
        )
        self.product = Product.objects.create(
            shop=self.shop,
            name="Test Product",
            slug="test-product",
            price=Decimal("10.00"),
            stock_quantity=50,
            is_active=True,
            is_approved=True,
        )
        # Create an order owned by buyer
        self.order = Order.objects.create(
            shop=self.shop,
            customer=self.buyer,
            order_number="GWBUYER001",
            customer_name="Test Buyer",
            customer_email="buyer@example.com",
            customer_phone="+31600000001",
            subtotal=Decimal("10.00"),
            total=Decimal("10.00"),
            status=Order.STATUS_PENDING,
        )
        # Create an order owned by other_buyer
        self.other_order = Order.objects.create(
            shop=self.shop,
            customer=self.other_buyer,
            order_number="GWBUYER002",
            customer_name="Other Buyer",
            customer_email="other_buyer@example.com",
            customer_phone="+31600000002",
            subtotal=Decimal("10.00"),
            total=Decimal("10.00"),
            status=Order.STATUS_PENDING,
        )

    def test_buyer_sees_only_own_orders(self):
        self.client.force_authenticate(self.buyer)
        res = self.client.get("/api/buyer/orders/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        order_ids = [o["id"] for o in res.data]
        self.assertIn(self.order.id, order_ids)
        self.assertNotIn(self.other_order.id, order_ids)

    def test_buyer_cannot_access_other_buyer_order_by_id(self):
        self.client.force_authenticate(self.buyer)
        res = self.client.get(f"/api/buyer/orders/{self.other_order.id}/")
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_unauthenticated_buyer_api_returns_401(self):
        res = self.client.get("/api/buyer/orders/")
        self.assertIn(res.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    def test_buyer_can_submit_cancellation_request(self):
        self.client.force_authenticate(self.buyer)
        res = self.client.post(
            f"/api/buyer/orders/{self.order.id}/cancel_request/",
            {"reason": "changed_mind", "message": "Changed my mind"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data["status"], "pending")
        self.assertEqual(res.data["reason"], "changed_mind")

    def test_buyer_cannot_submit_duplicate_cancellation_request(self):
        from apps.marketplace.models import OrderCancellationRequest

        OrderCancellationRequest.objects.create(
            order=self.order,
            buyer=self.buyer,
            shop=self.shop,
            reason="changed_mind",
        )
        self.client.force_authenticate(self.buyer)
        res = self.client.post(
            f"/api/buyer/orders/{self.order.id}/cancel_request/",
            {"reason": "other"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)


class SellerCancellationAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_superuser(
            username="admin3@example.com",
            email="admin3@example.com",
            password="adminpass123",
        )
        self.seller_user, self.seller_profile, self.shop = create_seller_with_shop(
            email="seller3@example.com",
            password="sellerpass123",
            first_name="Seller",
            last_name="Three",
            business_name="Cancel Test Shop",
            created_by=self.admin,
        )
        self.shop.is_approved = True
        self.shop.save()
        self.buyer = User.objects.create_user(
            username="buyer3@example.com",
            email="buyer3@example.com",
            password="buyerpass123",
        )
        self.order = Order.objects.create(
            shop=self.shop,
            customer=self.buyer,
            order_number="GWCANCEL001",
            customer_name="Cancel Buyer",
            customer_email="buyer3@example.com",
            customer_phone="+31600000003",
            subtotal=Decimal("15.00"),
            total=Decimal("15.00"),
            status=Order.STATUS_PENDING,
        )
        from apps.marketplace.models import OrderCancellationRequest

        self.cancel_request = OrderCancellationRequest.objects.create(
            order=self.order,
            buyer=self.buyer,
            shop=self.shop,
            reason="changed_mind",
            message="Test message",
        )

    def test_seller_can_list_cancellation_requests(self):
        self.client.force_authenticate(self.seller_user)
        res = self.client.get("/api/seller/cancellation-requests/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data), 1)

    def test_seller_can_approve_cancellation_request(self):
        self.client.force_authenticate(self.seller_user)
        res = self.client.patch(
            f"/api/seller/cancellation-requests/{self.cancel_request.id}/",
            {"status": "approved", "seller_note": "Refund will be processed"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["status"], "approved")
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.STATUS_CANCELLED)

    def test_seller_cannot_process_already_processed_request(self):
        from apps.marketplace.models import OrderCancellationRequest

        self.cancel_request.status = OrderCancellationRequest.STATUS_APPROVED
        self.cancel_request.save()
        self.client.force_authenticate(self.seller_user)
        res = self.client.patch(
            f"/api/seller/cancellation-requests/{self.cancel_request.id}/",
            {"status": "rejected"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)


class MarketplaceSearchAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        admin = User.objects.create_superuser(
            username="admin4@example.com",
            email="admin4@example.com",
            password="adminpass123",
        )
        _, _, self.shop = create_seller_with_shop(
            email="seller4@example.com",
            password="sellerpass123",
            first_name="Seller",
            last_name="Four",
            business_name="Search Test Shop",
            created_by=admin,
        )
        self.shop.is_approved = True
        self.shop.save()
        from apps.marketplace.models import Category

        self.cat = Category.objects.create(shop=self.shop, name="Books", slug="books", is_active=True)
        self.product = Product.objects.create(
            shop=self.shop,
            name="Python Book",
            slug="python-book",
            price=Decimal("29.99"),
            stock_quantity=5,
            is_active=True,
            is_approved=True,
            category=self.cat,
        )

    def test_search_by_product_name(self):
        res = self.client.get("/api/marketplace/search/?q=Python")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["total_products"], 1)
        self.assertEqual(res.data["products"][0]["name"], "Python Book")

    def test_search_by_category_slug(self):
        res = self.client.get(f"/api/marketplace/search/?category=books")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["total_products"], 1)

    def test_search_price_filter(self):
        res = self.client.get("/api/marketplace/search/?min_price=30")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["total_products"], 0)

    def test_search_in_stock_filter(self):
        res = self.client.get("/api/marketplace/search/?in_stock=true")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(res.data["total_products"], 1)

    def test_categories_endpoint_returns_list(self):
        res = self.client.get("/api/marketplace/categories/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        names = [c["name"] for c in res.data]
        self.assertIn("Books", names)


class MarketplaceMeAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_superuser(
            username="admin-me@example.com",
            email="admin-me@example.com",
            password="AdminPass123!",
        )
        self.seller_user, self.seller_profile, self.shop = create_seller_with_shop(
            email="me-seller@example.com",
            password="SellerPass123!",
            first_name="Me",
            last_name="Seller",
            business_name="Me Seller Shop",
            created_by=self.admin,
        )
        self.buyer = User.objects.create_user(
            username="me-buyer@example.com",
            email="me-buyer@example.com",
            password="BuyerPass123!",
        )

    def test_anonymous_user_is_not_authenticated(self):
        response = self.client.get("/api/marketplace/me/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data,
            {"is_authenticated": False, "is_seller": False, "shop_slug": None},
        )

    def test_authenticated_buyer_is_not_a_seller(self):
        self.client.force_authenticate(user=self.buyer)

        response = self.client.get("/api/marketplace/me/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data,
            {"is_authenticated": True, "is_seller": False, "shop_slug": None},
        )

    def test_authenticated_seller_returns_shop_slug(self):
        self.client.force_authenticate(user=self.seller_user)

        response = self.client.get("/api/marketplace/me/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data,
            {"is_authenticated": True, "is_seller": True, "shop_slug": self.shop.slug},
        )


class GuestOrderLinkingTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        admin = User.objects.create_superuser(
            username="admin5@example.com",
            email="admin5@example.com",
            password="adminpass123",
        )
        _, _, self.shop = create_seller_with_shop(
            email="seller5@example.com",
            password="sellerpass123",
            first_name="Seller",
            last_name="Five",
            business_name="Link Test Shop",
            created_by=admin,
        )
        self.shop.is_approved = True
        self.shop.save()

    def test_guest_order_linked_on_registration(self):
        # Create a guest order with the email we'll register with
        guest_order = Order.objects.create(
            shop=self.shop,
            customer=None,
            order_number="GWGUEST001",
            customer_name="Guest User",
            customer_email="newbuyer@example.com",
            customer_phone="+31600000099",
            subtotal=Decimal("20.00"),
            total=Decimal("20.00"),
            status=Order.STATUS_PENDING,
        )
        # Register with same email
        res = self.client.post(
            "/api/accounts/register/",
            {
                "username": "newbuyer",
                "email": "newbuyer@example.com",
                "password": "SecurePass123!",
                "password2": "SecurePass123!",
                "account_type": "buyer",
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        guest_order.refresh_from_db()
        user = User.objects.get(email="newbuyer@example.com")
        self.assertEqual(guest_order.customer, user)


class _SyncThread:
    """Drop-in replacement for threading.Thread that runs the target
    synchronously in the calling thread. Avoids SQLite table-locking
    flakiness in tests while still exercising the real email code path."""

    def __init__(self, target=None, args=(), kwargs=None, daemon=None):
        self._target = target
        self._args = args
        self._kwargs = kwargs or {}
        self.name = "SyncThread"

    def start(self):
        self._target(*self._args, **self._kwargs)


class OrderCheckoutAccountCreationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        admin = User.objects.create_superuser(
            username="admin6@example.com",
            email="admin6@example.com",
            password="AdminPass123!",
        )
        self.seller_user, _, self.shop = create_seller_with_shop(
            email="seller6@example.com",
            password="SellerPass123!",
            first_name="Seller",
            last_name="Six",
            business_name="Checkout Test Shop",
            created_by=admin,
        )
        self.shop.is_approved = True
        self.shop.delivery_available = True
        self.shop.save()
        self.product = Product.objects.create(
            shop=self.shop,
            name="Test Product",
            slug="test-product",
            price=Decimal("5.00"),
            stock_quantity=20,
            is_active=True,
            is_approved=True,
        )

    def _order_payload(self, **overrides):
        payload = {
            "shop_id": self.shop.id,
            "customer_name": "New Buyer",
            "customer_email": "guest-checkout@example.com",
            "customer_phone": "+31600000111",
            "order_type": "pickup",
            "payment_method": "cash",
            "items": [{"product_id": self.product.id, "quantity": 1}],
            "terms_accepted": True,
        }
        payload.update(overrides)
        return payload

    def test_guest_order_creation_works(self):
        with patch("apps.marketplace.services.threading.Thread", _SyncThread):
            response = self.client.post("/api/marketplace/orders/", self._order_payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIsNone(response.data["customer"])

    def test_guest_order_with_create_account_creates_user_via_existing_flow(self):
        payload = self._order_payload(
            create_account=True,
            password="StrongPass123!",
            password_confirm="StrongPass123!",
        )
        with patch("apps.marketplace.services.threading.Thread", _SyncThread):
            response = self.client.post("/api/marketplace/orders/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        user = User.objects.get(email="guest-checkout@example.com")
        self.assertEqual(response.data["customer"], user.id)
        # Reuses the existing registration flow: profile + confirmation token created.
        self.assertFalse(user.profile.email_confirmed)
        self.assertTrue(user.profile.email_confirmation_token)

    def test_duplicate_email_returns_validation_error(self):
        User.objects.create_user(
            username="existing-buyer",
            email="guest-checkout@example.com",
            password="ExistingPass123!",
        )
        payload = self._order_payload(
            create_account=True,
            password="StrongPass123!",
            password_confirm="StrongPass123!",
        )
        response = self.client.post("/api/marketplace/orders/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("customer_email", response.data)
        self.assertIn("already exists", str(response.data["customer_email"]))

    def test_password_mismatch_returns_validation_error(self):
        payload = self._order_payload(
            create_account=True,
            password="StrongPass123!",
            password_confirm="Different123!",
        )
        response = self.client.post("/api/marketplace/orders/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password_confirm", response.data)

    @patch("apps.future_wise.email_service.BrevoEmailService.send_account_confirmation_email")
    def test_verification_email_is_triggered_on_account_creation(self, mock_send):
        payload = self._order_payload(
            create_account=True,
            password="StrongPass123!",
            password_confirm="StrongPass123!",
        )
        with patch("apps.marketplace.services.threading.Thread", _SyncThread):
            response = self.client.post("/api/marketplace/orders/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        mock_send.assert_called_once()

    def test_logged_in_order_links_to_request_user_and_ignores_create_account(self):
        buyer = User.objects.create_user(
            username="logged-in-buyer",
            email="logged-in-buyer@example.com",
            password="LoggedInPass123!",
        )
        self.client.force_authenticate(buyer)
        payload = self._order_payload(
            customer_email="logged-in-buyer@example.com",
            create_account=True,
            password="StrongPass123!",
            password_confirm="StrongPass123!",
        )
        with patch("apps.marketplace.services.threading.Thread", _SyncThread):
            response = self.client.post("/api/marketplace/orders/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["customer"], buyer.id)
        # No extra account should have been created.
        self.assertEqual(User.objects.filter(email="logged-in-buyer@example.com").count(), 1)

    def test_email_failure_does_not_roll_back_order(self):
        with (
            patch("apps.marketplace.services.threading.Thread", _SyncThread),
            patch("apps.marketplace.services.send_mail", side_effect=Exception("smtp down")),
        ):
            response = self.client.post("/api/marketplace/orders/", self._order_payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Order.objects.filter(pk=response.data["id"]).exists())

    def test_buyer_confirmation_email_is_triggered(self):
        with patch("apps.marketplace.services.threading.Thread", _SyncThread):
            response = self.client.post("/api/marketplace/orders/", self._order_payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(mail.outbox), 2)  # buyer confirmation + seller notification
        recipients = {tuple(msg.to) for msg in mail.outbox}
        self.assertIn(("guest-checkout@example.com",), recipients)

    def test_seller_notification_email_uses_shop_owner_email(self):
        with patch("apps.marketplace.services.threading.Thread", _SyncThread):
            response = self.client.post("/api/marketplace/orders/", self._order_payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        recipients = {tuple(msg.to) for msg in mail.outbox}
        self.assertIn((self.seller_user.email,), recipients)

    def test_successful_emails_are_logged_and_order_flags_updated(self):
        with patch("apps.marketplace.services.threading.Thread", _SyncThread):
            response = self.client.post("/api/marketplace/orders/", self._order_payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        order = Order.objects.get(pk=response.data["id"])
        logs = {log.email_type: log for log in order.email_logs.all()}
        self.assertEqual(len(logs), 2)
        self.assertEqual(logs["buyer_confirmation"].status, OrderEmailLog.STATUS_SENT)
        self.assertEqual(logs["buyer_confirmation"].recipient, "guest-checkout@example.com")
        self.assertIsNotNone(logs["buyer_confirmation"].sent_at)
        self.assertEqual(logs["seller_notification"].status, OrderEmailLog.STATUS_SENT)
        self.assertEqual(logs["seller_notification"].recipient, self.seller_user.email)
        self.assertIsNotNone(logs["seller_notification"].sent_at)

        order.refresh_from_db()
        self.assertIsNotNone(order.buyer_email_sent_at)
        self.assertIsNotNone(order.seller_email_sent_at)

    def test_failed_email_is_logged_with_error_and_flag_not_set(self):
        with (
            patch("apps.marketplace.services.threading.Thread", _SyncThread),
            patch("apps.marketplace.services.send_mail", side_effect=Exception("smtp down")),
        ):
            response = self.client.post("/api/marketplace/orders/", self._order_payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        order = Order.objects.get(pk=response.data["id"])
        logs = list(order.email_logs.all())
        self.assertEqual(len(logs), 2)
        for log in logs:
            self.assertEqual(log.status, OrderEmailLog.STATUS_FAILED)
            self.assertIn("smtp down", log.error_message)
            self.assertIsNone(log.sent_at)

        order.refresh_from_db()
        self.assertIsNone(order.buyer_email_sent_at)
        self.assertIsNone(order.seller_email_sent_at)
