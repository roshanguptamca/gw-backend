from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import TestCase, TransactionTestCase, skipUnlessDBFeature
from django.urls import reverse

from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.marketplace.models import Order, Product, ScheduledMenu, SellerProfile, Shop, ShopSettings
from apps.marketplace.scheduled_menus import menu_schedule, remaining_units
from apps.marketplace.services import _create_order_atomic

TZ = ZoneInfo("Europe/Amsterdam")
NOW = datetime(2026, 10, 22, 12, tzinfo=TZ)
PICKUP = datetime(2026, 10, 23, 16, tzinfo=TZ)


class ScheduledMenuTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user(username="menu-seller", password="test")
        profile = SellerProfile.objects.create(user=self.owner, business_name="Menu shop")
        self.shop = Shop.objects.create(
            owner=self.owner,
            seller_profile=profile,
            name="Menu shop",
            slug="menu-shop",
            is_active=True,
            is_approved=True,
        )
        ShopSettings.objects.create(
            shop=self.shop, min_order_amount=0, order_acceptance_mode="manual", pickup_timezone="Europe/Amsterdam"
        )
        self.product = Product.objects.create(
            shop=self.shop,
            name="Vada Pav",
            slug="vada",
            sku="VADA",
            price=Decimal("5"),
            stock_quantity=100,
            is_active=True,
            is_approved=True,
        )
        self.menu = ScheduledMenu.objects.create(
            shop=self.shop,
            title="Friday special",
            pickup_date=PICKUP.date(),
            pickup_start=PICKUP.time(),
            pickup_end=(PICKUP + timedelta(hours=2)).time(),
            order_deadline=NOW + timedelta(hours=8),
            slot_minutes=30,
            capacity=10,
            slot_capacity=2,
            active=True,
        )
        self.menu.products.add(self.product)
        self.client = APIClient()
        self.clock = patch("apps.marketplace.ordering.current_time", return_value=NOW)
        self.clock.start()
        self.addCleanup(self.clock.stop)
        self.django_clock = patch("django.utils.timezone.now", return_value=NOW)
        self.django_clock.start()
        self.addCleanup(self.django_clock.stop)

    def payload(self, **overrides):
        return {
            "shop_id": self.shop.pk,
            "scheduled_menu_id": self.menu.pk,
            "customer_name": "Buyer",
            "customer_email": "buyer@example.com",
            "customer_phone": "+31612345678",
            "order_type": "pickup",
            "payment_method": "cash",
            "terms_accepted": True,
            "pickup_slot_start": PICKUP,
            "items": [{"product_id": self.product.pk, "quantity": 2}],
            **overrides,
        }

    def order(self, **overrides):
        return _create_order_atomic(self.payload(**overrides))

    def seller_url(self, suffix="detail"):
        return reverse(f"seller-scheduled-menu-{suffix}", kwargs={"pk": self.menu.pk})

    def test_menu_order_uses_existing_order_and_snapshots_outside_regular_hours(self):
        order = self.order()
        self.assertEqual(order.scheduled_menu, self.menu)
        self.assertEqual(order.pickup_slot_start, PICKUP)
        self.assertEqual(order.fulfillment_snapshot["scheduled_menu_title"], "Friday special")
        self.assertEqual(order.items.get().quantity, 2)
        self.assertEqual(remaining_units(self.menu), 8)

    def test_capacity_is_authoritative_and_pending_orders_reserve_it(self):
        self.menu.capacity = 3
        self.menu.save()
        self.order()
        with self.assertRaises(ValidationError):
            self.order()
        self.assertEqual(self.menu.orders.count(), 1)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 98)

    def test_full_slot_is_removed_but_later_slots_remain(self):
        self.menu.slot_capacity = 1
        self.menu.save()
        self.order()
        slots = menu_schedule(self.menu, [self.product], NOW)["days"][0]["slots"]
        self.assertNotEqual(slots[0]["start"], PICKUP.isoformat())
        with self.assertRaises(ValidationError):
            self.order()
        self.order(pickup_slot_start=PICKUP + timedelta(minutes=30))

    def test_cancellation_and_rejection_release_capacity_and_slot(self):
        for status in (Order.STATUS_CANCELLED, Order.STATUS_REJECTED):
            order = self.order()
            order.status = status
            order.save(update_fields=["status"])
            self.assertEqual(remaining_units(self.menu), 10)
            self.assertEqual(
                menu_schedule(self.menu, [self.product], NOW)["days"][0]["slots"][0]["start"], PICKUP.isoformat()
            )

    def test_deadline_is_exclusive_and_cannot_be_bypassed(self):
        with patch("apps.marketplace.ordering.current_time", return_value=self.menu.order_deadline):
            with self.assertRaises(ValidationError):
                self.order()
        self.assertEqual(menu_schedule(self.menu, [self.product], self.menu.order_deadline)["days"], [])

    def test_preparation_time_and_missing_or_unaligned_slot_are_enforced(self):
        self.product.preparation_time_minutes = 48 * 60
        self.product.save()
        with self.assertRaises(ValidationError):
            self.order()
        self.product.preparation_time_minutes = 0
        self.product.save()
        for slot in (None, PICKUP + timedelta(minutes=1), PICKUP - timedelta(days=1)):
            with self.assertRaises(ValidationError):
                self.order(pickup_slot_start=slot)

    def test_delivery_paused_menu_and_unknown_menu_are_rejected(self):
        with self.assertRaises(ValidationError):
            self.order(order_type="delivery", delivery_address="Test address")
        self.menu.active = False
        self.menu.save()
        with self.assertRaises(ValidationError):
            self.order()
        with self.assertRaises(ValidationError):
            self.order(scheduled_menu_id=999999)

    def test_only_products_in_the_menu_are_allowed(self):
        other = Product.objects.create(
            shop=self.shop,
            name="Other",
            slug="other",
            sku="OTHER",
            price=5,
            stock_quantity=100,
            is_active=True,
            is_approved=True,
        )
        with self.assertRaises(ValidationError):
            self.order(items=[{"product_id": other.pk, "quantity": 1}])

    def test_duplicate_product_lines_are_aggregated_before_stock_checks(self):
        self.product.stock_quantity = 3
        self.product.save()
        with self.assertRaises(ValidationError):
            self.order(items=[{"product_id": self.product.pk, "quantity": 2}] * 2)
        self.assertFalse(self.menu.orders.exists())

    def test_regular_orders_keep_existing_flow(self):
        payload = self.payload()
        payload.pop("scheduled_menu_id")
        order = _create_order_atomic(payload)
        self.assertIsNone(order.scheduled_menu_id)

    def test_seller_reports_separate_pending_and_confirmed_and_exclude_cancelled(self):
        self.order()
        order = self.order(pickup_slot_start=PICKUP + timedelta(minutes=30))
        order.status = Order.STATUS_ACCEPTED
        order.save()
        cancelled = self.order(pickup_slot_start=PICKUP + timedelta(minutes=60))
        cancelled.status = Order.STATUS_CANCELLED
        cancelled.save()
        self.client.force_authenticate(self.owner)
        response = self.client.get(self.seller_url("preparation"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["confirmed_quantities"][0]["quantity"], 2)
        self.assertEqual(response.data["pending_quantities"][0]["quantity"], 2)
        self.assertEqual(len(response.data["pickups"]), 2)

    def test_public_menus_never_contain_buyer_data(self):
        self.order()
        response = self.client.get(reverse("marketplace-shop-scheduled-menus", kwargs={"slug": self.shop.slug}))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("Buyer", str(response.data))
        self.assertEqual(response.data[0]["remaining_capacity"], 8)
        self.menu.active = False
        self.menu.save()
        self.assertEqual(
            self.client.get(reverse("marketplace-shop-scheduled-menus", kwargs={"slug": self.shop.slug})).data, []
        )

    def test_seller_access_is_scoped_to_own_shop(self):
        other = get_user_model().objects.create_user(username="other-owner")
        profile = SellerProfile.objects.create(user=other, business_name="Other")
        Shop.objects.create(owner=other, seller_profile=profile, name="Other", slug="other")
        self.client.force_authenticate(other)
        self.assertEqual(self.client.get(self.seller_url("preparation")).status_code, 404)
        self.assertEqual(self.client.patch(self.seller_url(), {"title": "changed"}).status_code, 404)
        self.assertEqual(self.client.get(reverse("seller-scheduled-menu-list")).data, [])

    def test_editing_booked_schedule_or_lowering_capacity_is_rejected(self):
        self.order()
        self.client.force_authenticate(self.owner)
        for body in ({"pickup_date": "2026-10-24"}, {"products": []}, {"capacity": 1}):
            self.assertEqual(self.client.patch(self.seller_url(), body, format="json").status_code, 400)
        self.assertEqual(self.client.patch(self.seller_url(), {"capacity": 20}, format="json").status_code, 200)
        self.assertEqual(self.client.patch(self.seller_url(), {"active": False}, format="json").status_code, 200)

    def test_slot_query_is_scoped_to_shop_and_menu(self):
        url = reverse("marketplace-shop-pickup-slots", kwargs={"slug": self.shop.slug})
        response = self.client.get(url, {"product_ids": self.product.pk, "scheduled_menu_id": self.menu.pk})
        self.assertTrue(response.data["scheduling_enabled"])
        self.assertEqual(len(response.data["days"]), 1)
        self.assertEqual(self.client.get(url, {"scheduled_menu_id": "bad"}).status_code, 404)

    def test_create_menu_validates_timezone_windows_and_product_ownership(self):
        self.client.force_authenticate(self.owner)
        body = {
            "title": "New menu",
            "products": [self.product.pk],
            "pickup_date": "2026-10-24",
            "pickup_start": "15:00",
            "pickup_end": "18:00",
            "order_deadline": "2026-10-23T20:00",
            "capacity": 40,
            "active": True,
        }
        response = self.client.post(reverse("seller-scheduled-menu-list"), body, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(ScheduledMenu.objects.get(pk=response.data["id"]).order_deadline.astimezone(TZ).hour, 20)
        for updates in ({"pickup_end": "14:00"}, {"order_deadline": "2026-10-24T16:00"}, {"products": [999999]}):
            response = self.client.post(reverse("seller-scheduled-menu-list"), {**body, **updates}, format="json")
            self.assertEqual(response.status_code, 400)

    def test_booked_menu_keeps_its_timezone_if_shop_settings_change(self):
        order = self.order()
        self.shop.settings.pickup_timezone = "UTC"
        self.shop.settings.save()
        self.menu.refresh_from_db()
        self.assertEqual(self.menu.pickup_timezone, "Europe/Amsterdam")
        self.assertEqual(order.fulfillment_snapshot["pickup_timezone"], "Europe/Amsterdam")
        self.assertEqual(menu_schedule(self.menu, [self.product], NOW)["timezone"], "Europe/Amsterdam")

    def test_stale_status_updates_cannot_resurrect_released_capacity(self):
        from apps.marketplace.services import update_order_status

        order = self.order()
        stale = Order.objects.get(pk=order.pk)
        with patch("apps.marketplace.services.send_order_status_update_email_to_buyer"):
            update_order_status(order, Order.STATUS_REJECTED)
            with self.assertRaises(ValidationError):
                update_order_status(stale, Order.STATUS_ACCEPTED)
        self.assertEqual(remaining_units(self.menu), 10)

    @patch("apps.marketplace.services.threading.Thread")
    def test_existing_checkout_endpoint_accepts_menu_context(self, thread):
        body = self.payload()
        body["pickup_slot_start"] = PICKUP.isoformat()
        response = self.client.post("/api/marketplace/orders/", body, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(Order.objects.get(pk=response.data["id"]).scheduled_menu_id, self.menu.pk)

    def test_menu_from_a_different_shop_cannot_be_ordered(self):
        other = get_user_model().objects.create_user(username="foreign-menu-owner")
        profile = SellerProfile.objects.create(user=other, business_name="Other")
        shop = Shop.objects.create(owner=other, seller_profile=profile, name="Other", slug="foreign-menu-shop")
        self.menu.shop = shop
        self.menu.save()
        with self.assertRaises(ValidationError):
            self.order()

    def test_slot_limit_cannot_be_reduced_below_existing_bookings(self):
        self.order()
        self.order()
        self.client.force_authenticate(self.owner)
        response = self.client.patch(self.seller_url(), {"slot_capacity": 1}, format="json")
        self.assertEqual(response.status_code, 400)


# Row-lock correctness is exercised when this suite uses PostgreSQL in CI/staging.


class ScheduledMenuConcurrencyTests(TransactionTestCase):
    setUp = ScheduledMenuTests.setUp
    payload = ScheduledMenuTests.payload

    @skipUnlessDBFeature("has_select_for_update")
    def test_two_buyers_cannot_reserve_the_last_unit(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier

        from django.db import connections

        self.menu.capacity = 1
        self.menu.save()
        barrier = Barrier(2)

        def buy():
            connections.close_all()
            barrier.wait(timeout=10)
            try:
                _create_order_atomic(self.payload(items=[{"product_id": self.product.pk, "quantity": 1}]))
                return "reserved"
            except ValidationError:
                return "full"
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: buy(), range(2)))
        self.assertCountEqual(results, ["reserved", "full"])
        self.assertEqual(self.menu.orders.count(), 1)
