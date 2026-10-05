from datetime import timedelta
from decimal import Decimal
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

import requests
from rest_framework.test import APIClient

from apps.marketplace.models import Order, OrderWhatsAppNotification, Product
from apps.marketplace.serializers import PublicShopSettingsSerializer, ShopSettingsSerializer
from apps.marketplace.services import create_order_from_payload, create_seller_with_shop
from apps.marketplace.whatsapp import (
    MAX_ATTEMPTS,
    DeliveryResult,
    MetaCloudWhatsAppProvider,
    WhatsAppNotificationService,
    dispatch_order_whatsapp_notifications,
    order_parameters,
    render_message,
)


@override_settings(MARKETPLACE_SELLER_PORTAL_URL="https://marketplace.example.com")
class OrderWhatsAppTests(TestCase):
    def setUp(self):
        self.user, _, self.shop = create_seller_with_shop(
            email="seller@example.com",
            password="SellerTest123!",
            first_name="Seller",
            last_name="One",
            business_name="First Shop",
        )
        self.other_user, _, self.other_shop = create_seller_with_shop(
            email="other@example.com",
            password="SellerTest123!",
            first_name="Seller",
            last_name="Two",
            business_name="Second Shop",
        )
        for shop in (self.shop, self.other_shop):
            shop.is_approved = True
            shop.delivery_available = True
            shop.save()
            shop.settings.whatsapp_notifications_enabled = True
            shop.settings.whatsapp_number = "+14155552671" if shop == self.shop else "+447700900123"
            shop.settings.pickup_address_line_1 = f"{shop.name} pickup location"
            shop.settings.save()
        self.product = Product.objects.create(
            shop=self.shop,
            name="First item",
            slug="first",
            price=Decimal("4.50"),
            stock_quantity=100,
            is_approved=True,
        )
        self.other_product = Product.objects.create(
            shop=self.other_shop,
            name="Second item",
            slug="second",
            price=Decimal("7.00"),
            stock_quantity=100,
            is_approved=True,
        )
        self.thread = patch("apps.marketplace.services.threading.Thread").start()
        self.addCleanup(patch.stopall)
        self.client = APIClient()
        self.provider = Mock()
        self.provider.send.return_value = DeliveryResult(message_id="wamid.test")

    def payload(self, shop=None, product=None, **extra):
        data = {
            "shop_id": (shop or self.shop).pk,
            "customer_name": "Example Buyer",
            "customer_phone": "+33123456789",
            "customer_email": "buyer@example.com",
            "items": [{"product_id": (product or self.product).pk, "quantity": 2}],
            "terms_accepted": True,
            "order_type": "pickup",
            "customer_note": "No extra spice",
        }
        return {**data, **extra}

    def create(self, **extra):
        return create_order_from_payload(self.payload(**extra))

    def deliver(self, order):
        WhatsAppNotificationService.deliver(order.whatsapp_notification.pk, self.provider)
        order.whatsapp_notification.refresh_from_db()
        return order.whatsapp_notification

    def test_successful_order_enqueues_and_sends_seller_notification(self):
        response = self.client.post("/api/orders/", self.payload(), format="json")
        self.assertEqual(response.status_code, 201)
        order = Order.objects.get(pk=response.data["id"])
        self.provider.send.assert_not_called()
        notification = self.deliver(order)
        self.assertEqual(notification.status, "sent")
        self.assertEqual(notification.provider_message_id, "wamid.test")
        self.assertIsNotNone(notification.sent_at)
        self.provider.send.assert_called_once()
        self.assertEqual(self.provider.send.call_args.args[0], "+14155552671")
        self.thread.assert_called_once()

    def test_invalid_order_does_not_enqueue(self):
        response = self.client.post("/api/orders/", self.payload(items=[]), format="json")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(OrderWhatsAppNotification.objects.exists())

    def test_outbox_rolls_back_with_order(self):
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                self.create()
                raise RuntimeError("rollback")
        self.assertFalse(Order.objects.exists())
        self.assertFalse(OrderWhatsAppNotification.objects.exists())

    def test_disabled_does_not_enqueue(self):
        self.shop.settings.whatsapp_notifications_enabled = False
        self.shop.settings.save()
        self.create()
        self.assertFalse(OrderWhatsAppNotification.objects.exists())

    def test_missing_or_invalid_number_does_not_fail_order(self):
        for number in ("", "local number"):
            with self.subTest(number=number):
                self.shop.settings.whatsapp_number = number
                self.shop.settings.save()
                with self.assertLogs("apps.marketplace.whatsapp", level="WARNING"):
                    order = self.create()
                self.assertTrue(Order.objects.filter(pk=order.pk).exists())
                self.assertFalse(OrderWhatsAppNotification.objects.exists())

    def test_provider_failure_cannot_fail_checkout(self):
        self.provider.send.return_value = DeliveryResult(error="Provider rejected request.")
        order = self.create()
        notification = self.deliver(order)
        self.assertEqual(notification.status, "failed")
        self.assertTrue(Order.objects.filter(pk=order.pk).exists())

    def test_pickup_message_uses_order_snapshot_not_current_shop(self):
        order = self.create()
        order.fulfillment_snapshot.update(pickup_date="10 Oct 2026", pickup_time="16:30", currency="GBP")
        order.save()
        self.shop.name = "Renamed Shop"
        self.shop.save()
        message = render_message(order_parameters(order))
        for value in (
            "First Shop",
            order.order_number,
            "Example Buyer",
            "+33123456789",
            "buyer@example.com",
            "2 pieces First item",
            "GBP 9.00",
            "Pickup",
            "First Shop pickup location",
            "10 Oct 2026",
            "16:30",
            "No extra spice",
            f"https://marketplace.example.com/seller/orders?order={order.pk}",
        ):
            self.assertIn(value, message)
        self.assertNotIn("Renamed Shop", message)

    def test_delivery_message_does_not_include_pickup_location_or_time(self):
        order = self.create(order_type="delivery", delivery_address="12 Buyer Road, Example City")
        message = render_message(order_parameters(order))
        self.assertIn("Delivery", message)
        self.assertIn("12 Buyer Road, Example City", message)
        self.assertNotIn("pickup location", message)
        self.assertIn("Requested date: Not applicable", message)

    def test_multiple_shop_orders_are_isolated(self):
        first = self.create()
        second = self.create(
            shop=self.other_shop,
            product=self.other_product,
            order_type="delivery",
            delivery_address="Second fulfillment address",
        )
        self.deliver(first)
        self.deliver(second)
        first_call, second_call = self.provider.send.call_args_list
        self.assertEqual(first_call.args[0], "+14155552671")
        self.assertEqual(second_call.args[0], "+447700900123")
        first_message = render_message(first_call.args[1])
        second_message = render_message(second_call.args[1])
        self.assertNotIn("Second item", first_message)
        self.assertNotIn("Second fulfillment address", first_message)
        self.assertNotIn("First item", second_message)
        self.assertNotIn("First Shop pickup location", second_message)

    def test_duplicate_enqueue_and_delivery_do_not_resend(self):
        order = self.create()
        WhatsAppNotificationService.enqueue(order)
        self.deliver(order)
        self.deliver(order)
        self.assertEqual(OrderWhatsAppNotification.objects.count(), 1)
        self.provider.send.assert_called_once()

    def test_atomic_claim_prevents_concurrent_duplicate_send(self):
        order = self.create()
        self.provider.send.side_effect = lambda *args: (
            WhatsAppNotificationService.deliver(order.whatsapp_notification.pk, self.provider)
            or DeliveryResult(message_id="wamid.test")
        )
        self.deliver(order)
        self.provider.send.assert_called_once()

    def test_retry_is_delayed_and_bounded(self):
        self.provider.send.return_value = DeliveryResult(error="Rate limited", retryable=True)
        order = self.create()
        for attempt in range(1, MAX_ATTEMPTS + 1):
            notification = self.deliver(order)
            self.assertEqual(notification.attempts, attempt)
            if attempt < MAX_ATTEMPTS:
                self.assertEqual(notification.status, "pending")
                self.assertGreater(notification.next_attempt_at, timezone.now())
                self.deliver(order)
                self.assertEqual(self.provider.send.call_count, attempt)
                OrderWhatsAppNotification.objects.filter(pk=notification.pk).update(
                    next_attempt_at=timezone.now() - timedelta(seconds=1)
                )
        self.assertEqual(notification.status, "failed")
        self.deliver(order)
        self.assertEqual(self.provider.send.call_count, MAX_ATTEMPTS)

    def test_uncertain_result_is_not_automatically_retried(self):
        self.provider.send.return_value = DeliveryResult(error="Uncertain timeout", uncertain=True)
        order = self.create()
        self.assertEqual(self.deliver(order).status, "unknown")
        self.deliver(order)
        self.provider.send.assert_called_once()

    def test_stale_worker_claim_is_not_resent(self):
        order = self.create()
        notification = order.whatsapp_notification
        notification.status = "processing"
        notification.claimed_at = timezone.now() - timedelta(minutes=6)
        notification.save()
        with patch("apps.marketplace.whatsapp.MetaCloudWhatsAppProvider.send") as send:
            dispatch_order_whatsapp_notifications()
        send.assert_not_called()
        notification.refresh_from_db()
        self.assertEqual(notification.status, "unknown")

    def test_worker_recovers_durable_pending_outbox(self):
        order = self.create()
        with patch(
            "apps.marketplace.whatsapp.MetaCloudWhatsAppProvider.send",
            return_value=DeliveryResult(message_id="wamid.recovered"),
        ) as send:
            dispatch_order_whatsapp_notifications()
        send.assert_called_once()
        order.whatsapp_notification.refresh_from_db()
        self.assertEqual(order.whatsapp_notification.status, "sent")

    def test_worker_logs_unexpected_errors_without_secret_text(self):
        order = self.create()
        with patch(
            "apps.marketplace.whatsapp.MetaCloudWhatsAppProvider.send", side_effect=RuntimeError("sensitive-token")
        ):
            with self.assertLogs("apps.marketplace.whatsapp", level="ERROR") as logs:
                dispatch_order_whatsapp_notifications()
        self.assertNotIn("sensitive-token", " ".join(logs.output))
        order.whatsapp_notification.refresh_from_db()
        self.assertEqual(order.whatsapp_notification.status, "processing")

    def test_disabling_or_changing_recipient_cancels_queued_notification(self):
        for field, value in (("whatsapp_notifications_enabled", False), ("whatsapp_number", "+819012345678")):
            with self.subTest(field=field):
                self.shop.settings.whatsapp_notifications_enabled = True
                self.shop.settings.whatsapp_number = "+14155552671"
                self.shop.settings.save()
                order = self.create()
                setattr(self.shop.settings, field, value)
                self.shop.settings.save()
                self.assertEqual(self.deliver(order).status, "skipped")
        self.provider.send.assert_not_called()

    def test_large_content_respects_meta_template_limits(self):
        order = self.create(customer_note="x" * 10000)
        order.customer_name = "n" * 150
        order.customer_email = "e" * 250
        order.fulfillment_snapshot["shop_address"] = "a" * 1000
        order.items.update(product_name="p" * 150)
        parameters = order_parameters(order)
        self.assertLessEqual(len(render_message(parameters)), 1024)
        self.assertEqual(len(parameters), 13)
        self.assertTrue(all("\n" not in value and "\t" not in value for value in parameters))
        self.assertTrue(parameters[-1].endswith(f"?order={order.pk}"))

    def test_invalid_portal_config_fails_safely_without_provider_call(self):
        order = self.create()
        with override_settings(MARKETPLACE_SELLER_PORTAL_URL="http://unsafe.example.com"):
            self.assertEqual(self.deliver(order).status, "failed")
        self.provider.send.assert_not_called()

    def test_only_own_shop_settings_can_be_changed(self):
        self.client.force_authenticate(self.user)
        response = self.client.patch(
            "/api/seller/settings/", {"shop": self.other_shop.pk, "whatsapp_number": "+819012345678"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.other_shop.settings.refresh_from_db()
        self.assertEqual(self.other_shop.settings.whatsapp_number, "+447700900123")
        self.shop.settings.refresh_from_db()
        self.assertEqual(self.shop.settings.whatsapp_number, "+819012345678")

    def test_anonymous_and_buyer_cannot_change_settings(self):
        self.assertIn(self.client.patch("/api/seller/settings/", {}, format="json").status_code, (401, 403))
        buyer = get_user_model().objects.create_user(username="buyer", password="BuyerTest123!")
        self.client.force_authenticate(buyer)
        self.assertEqual(self.client.patch("/api/seller/settings/", {}, format="json").status_code, 403)

    def test_public_shop_contact_preserved_without_private_provider_config(self):
        data = PublicShopSettingsSerializer(self.shop.settings).data
        self.assertEqual(data["whatsapp_number"], "+14155552671")
        self.assertNotIn("whatsapp_notifications_enabled", data)
        self.assertIn("whatsapp_group_url", data)

    def test_e164_validation_and_enable_requires_number(self):
        for number in ("0612345678", "+0123456789", "+123", "+1234567890123456"):
            with self.subTest(number=number):
                serializer = ShopSettingsSerializer(self.shop.settings, data={"whatsapp_number": number}, partial=True)
                self.assertFalse(serializer.is_valid())
        for number in ("+31612345678", "+14155552671", "+819012345678", "+31 6 12345678"):
            serializer = ShopSettingsSerializer(self.shop.settings, data={"whatsapp_number": number}, partial=True)
            self.assertTrue(serializer.is_valid(), serializer.errors)
        serializer = ShopSettingsSerializer(self.shop.settings, data={"whatsapp_number": ""}, partial=True)
        self.assertFalse(serializer.is_valid())
        serializer = ShopSettingsSerializer(
            self.shop.settings,
            data={"whatsapp_notifications_enabled": False, "whatsapp_number": ""},
            partial=True,
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_admin_model_validation_requires_number_when_enabled(self):
        self.shop.settings.whatsapp_number = ""
        with self.assertRaises(ValidationError):
            self.shop.settings.full_clean()

    def test_existing_formatted_shop_number_is_normalized_on_send(self):
        self.shop.settings.whatsapp_number = "+1 (415) 555-2671"
        self.shop.settings.save()
        order = self.create()
        self.deliver(order)
        self.assertEqual(self.provider.send.call_args.args[0], "+14155552671")

    def test_enabling_normalizes_existing_number_without_separate_recipient(self):
        self.shop.settings.whatsapp_notifications_enabled = False
        self.shop.settings.whatsapp_number = "+1 (415) 555-2671"
        self.shop.settings.save()
        serializer = ShopSettingsSerializer(
            self.shop.settings, data={"whatsapp_notifications_enabled": True}, partial=True
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        serializer.save()
        self.assertEqual(self.shop.settings.whatsapp_number, "+14155552671")

    def test_weight_and_pack_quantities_use_item_snapshots(self):
        order = self.create()
        item = order.items.get()
        item.selling_unit = "PACK"
        item.units_per_pack = 3
        item.save()
        self.assertIn("2 packs", order_parameters(order)[5])
        self.assertIn("6 pieces", order_parameters(order)[5])
        item.selling_unit = "WEIGHT"
        item.weight_value = Decimal("250")
        item.weight_unit = "GRAM"
        item.save()
        self.assertIn("250 g", order_parameters(order)[5])
        self.assertIn("500 g", order_parameters(order)[5])


@override_settings(
    WHATSAPP_ACCESS_TOKEN="test-only-token",
    WHATSAPP_PHONE_NUMBER_ID="123456",
    WHATSAPP_API_VERSION="v25.0",
    WHATSAPP_ORDER_TEMPLATE_NAME="marketplace_new_order",
    WHATSAPP_ORDER_TEMPLATE_LANGUAGE="en_US",
)
class MetaProviderTests(SimpleTestCase):
    def setUp(self):
        self.provider = MetaCloudWhatsAppProvider()
        self.parameters = [f"value-{index}" for index in range(13)]

    @patch("apps.marketplace.whatsapp.requests.post")
    def test_uses_approved_template_not_freeform(self, post):
        post.return_value = Mock(status_code=200)
        post.return_value.json.return_value = {"messages": [{"id": "wamid.test"}]}
        result = self.provider.send("+14155552671", self.parameters)
        self.assertEqual(result.message_id, "wamid.test")
        args, kwargs = post.call_args
        self.assertEqual(args[0], "https://graph.facebook.com/v25.0/123456/messages")
        self.assertEqual(kwargs["timeout"], (5, 15))
        self.assertEqual(kwargs["json"]["type"], "template")
        self.assertNotIn("text", kwargs["json"])
        template = kwargs["json"]["template"]
        self.assertEqual(template["name"], "marketplace_new_order")
        self.assertEqual(template["language"], {"code": "en_US"})
        self.assertEqual(len(template["components"][0]["parameters"]), 13)

    @patch("apps.marketplace.whatsapp.requests.post")
    def test_rate_limit_retries_but_permanent_rejection_does_not(self, post):
        for status, code, retryable in (
            (429, 130429, True),
            (400, 131056, True),
            (503, 2, True),
            (500, 131000, True),
            (500, 131016, True),
            (401, 190, False),
            (400, 132001, False),
            (400, 131026, False),
        ):
            with self.subTest(code=code):
                post.return_value = Mock(status_code=status)
                post.return_value.json.return_value = {"error": {"code": code, "message": "sensitive-token"}}
                result = self.provider.send("+14155552671", self.parameters)
                self.assertEqual(result.retryable, retryable)
                self.assertNotIn("sensitive-token", result.error)

    @patch("apps.marketplace.whatsapp.requests.post")
    def test_network_errors_are_uncertain_not_retryable(self, post):
        for error in (requests.ReadTimeout("secret"), requests.ConnectionError("secret")):
            post.side_effect = error
            result = self.provider.send("+14155552671", self.parameters)
            self.assertTrue(result.uncertain)
            self.assertFalse(result.retryable)
            self.assertNotIn("secret", result.error)

    @patch("apps.marketplace.whatsapp.requests.post")
    def test_malformed_success_and_server_errors_are_uncertain(self, post):
        for status, body in ((200, {}), (200, []), (200, {"messages": [{"id": None}]}), (503, {})):
            with self.subTest(status=status, body=body):
                post.return_value = Mock(status_code=status)
                post.return_value.json.return_value = body
                self.assertTrue(self.provider.send("+14155552671", self.parameters).uncertain)
        post.return_value.json.side_effect = ValueError("invalid JSON")
        self.assertTrue(self.provider.send("+14155552671", self.parameters).uncertain)

    @patch("apps.marketplace.whatsapp.requests.post")
    def test_missing_config_never_attempts_real_delivery(self, post):
        with override_settings(WHATSAPP_ACCESS_TOKEN=""):
            result = self.provider.send("+14155552671", self.parameters)
        self.assertTrue(result.error)
        self.assertFalse(result.retryable)
        post.assert_not_called()


class WhatsAppSchedulerTests(SimpleTestCase):
    @patch("apps.future_wise.apps._scheduler_started", False)
    @patch("apps.future_wise.apps._start_background_scheduler")
    def test_pytest_startup_never_starts_live_notification_scheduler(self, start_scheduler):
        from django.apps import apps

        apps.get_app_config("future_wise").ready()
        start_scheduler.assert_not_called()

    def assert_registered(self, scheduler):
        registrations = [
            call
            for call in scheduler.add_job.call_args_list
            if call.kwargs.get("id") == "dispatch_order_whatsapp_notifications"
        ]
        self.assertEqual(len(registrations), 1)
        self.assertEqual(registrations[0].args[0], dispatch_order_whatsapp_notifications)
        self.assertEqual(registrations[0].kwargs["trigger"].interval, timedelta(seconds=5))
        self.assertEqual(registrations[0].kwargs["max_instances"], 1)
        self.assertTrue(registrations[0].kwargs["coalesce"])

    @patch("apps.future_wise.management.commands.runapscheduler.BlockingScheduler")
    def test_dedicated_scheduler_registers_whatsapp_dispatch(self, scheduler_class):
        from apps.future_wise.management.commands.runapscheduler import Command

        Command().handle()
        self.assert_registered(scheduler_class.return_value)

    @override_settings(IS_DEVELOPMENT=True)
    @patch("apscheduler.schedulers.background.BackgroundScheduler")
    def test_existing_background_scheduler_registers_whatsapp_dispatch(self, scheduler_class):
        from apps.future_wise.apps import _start_background_scheduler

        _start_background_scheduler()
        self.assert_registered(scheduler_class.return_value)
