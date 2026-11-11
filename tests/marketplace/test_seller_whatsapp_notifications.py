"""Regression tests for opt-in, nonblocking marketplace seller WhatsApp alerts."""
import json
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings

from apps.marketplace.whatsapp_notifications import (
    notification_config,
    send_seller_whatsapp,
    template_variables,
)


def sample_order():
    shop_settings = SimpleNamespace(whatsapp_number="+31612345678")
    shop = SimpleNamespace(id=7, pk=7, slug="rishi-kitchen", settings=shop_settings)
    return SimpleNamespace(
        pk=101,
        shop=shop,
        shop_id=7,
        order_number="RK-101",
        customer_name="Test Customer",
        total=Decimal("25.00"),
        order_type="pickup",
        fulfillment_snapshot={"currency": "EUR", "pickup_date": "Friday", "pickup_time": "17:00"},
        items=SimpleNamespace(all=lambda: [
            SimpleNamespace(quantity=2, product_name="Chole Bhature"),
            SimpleNamespace(quantity=1, product_name="Besan Laddu"),
        ]),
    )


CONFIG = {
    "MARKETPLACE_SELLER_WHATSAPP_ENABLED": True,
    "MARKETPLACE_SELLER_WHATSAPP_SHOPS": "rishi-kitchen",
    "MARKETPLACE_WHATSAPP_CONTENT_SID": "HX" + "a" * 32,
    "TWILIO_ACCOUNT_SID": "AC" + "b" * 32,
    "TWILIO_AUTH_TOKEN": "test-token",
    "TWILIO_WHATSAPP_FROM": "+14155238886",
}


class SellerWhatsAppConfigTests(SimpleTestCase):
    def test_disabled_by_default(self):
        with override_settings(**{**CONFIG, "MARKETPLACE_SELLER_WHATSAPP_ENABLED": False}):
            self.assertIsNone(notification_config(sample_order()))

    def test_nonallowlisted_shop_does_not_send(self):
        with override_settings(**{**CONFIG, "MARKETPLACE_SELLER_WHATSAPP_SHOPS": "another-shop"}):
            self.assertIsNone(notification_config(sample_order()))

    def test_missing_or_invalid_number_fails_closed(self):
        order = sample_order()
        order.shop.settings.whatsapp_number = "0612345678"
        with override_settings(**CONFIG):
            self.assertIsNone(notification_config(order))

    def test_missing_template_fails_closed(self):
        with override_settings(**{**CONFIG, "MARKETPLACE_WHATSAPP_CONTENT_SID": ""}):
            self.assertIsNone(notification_config(sample_order()))

    def test_valid_config_uses_seller_personal_number(self):
        with override_settings(**CONFIG):
            recipient, sender, sid, account, token = notification_config(sample_order())
        self.assertEqual(recipient, "+31612345678")
        self.assertEqual(sender, "+14155238886")
        self.assertEqual(sid, CONFIG["MARKETPLACE_WHATSAPP_CONTENT_SID"])

    def test_template_contains_order_details_without_customer_contact_information(self):
        variables = template_variables(sample_order())
        self.assertEqual(variables["1"], "RK-101")
        self.assertIn("2 x Chole Bhature", variables["2"])
        self.assertEqual(variables["3"], "25.00 EUR")
        self.assertIn("Friday", variables["4"])
        self.assertEqual(variables["5"], "Test Customer")


class SellerWhatsAppDeliveryTests(SimpleTestCase):
    @override_settings(**CONFIG)
    @patch("twilio.rest.Client")
    @patch("apps.marketplace.models.Order.objects")
    def test_uses_approved_template_and_explicit_seller_number(self, objects, client):
        order = sample_order()
        objects.select_related.return_value.prefetch_related.return_value.get.return_value = order
        client.return_value.messages.create.return_value.sid = "SM123"
        self.assertTrue(send_seller_whatsapp(101))
        kwargs = client.return_value.messages.create.call_args.kwargs
        self.assertEqual(kwargs["to"], "whatsapp:+31612345678")
        self.assertEqual(kwargs["from_"], "whatsapp:+14155238886")
        self.assertEqual(kwargs["content_sid"], CONFIG["MARKETPLACE_WHATSAPP_CONTENT_SID"])
        self.assertEqual(json.loads(kwargs["content_variables"])["1"], "RK-101")
        self.assertNotIn("body", kwargs)

    @override_settings(**CONFIG)
    @patch("twilio.rest.Client")
    @patch("apps.marketplace.models.Order.objects")
    def test_twilio_failure_is_swallowed(self, objects, client):
        objects.select_related.return_value.prefetch_related.return_value.get.return_value = sample_order()
        client.return_value.messages.create.side_effect = RuntimeError("temporary error")
        self.assertFalse(send_seller_whatsapp(101))

    @override_settings(**{**CONFIG, "MARKETPLACE_SELLER_WHATSAPP_ENABLED": False})
    @patch("twilio.rest.Client")
    @patch("apps.marketplace.models.Order.objects")
    def test_disabled_never_calls_twilio(self, objects, client):
        objects.select_related.return_value.prefetch_related.return_value.get.return_value = sample_order()
        self.assertFalse(send_seller_whatsapp(101))
        client.assert_not_called()


class ExistingEmailsRegressionTests(SimpleTestCase):
    @patch("apps.marketplace.whatsapp_notifications.send_seller_whatsapp", side_effect=RuntimeError("down"))
    @patch("apps.marketplace.services.send_seller_notification_email")
    @patch("apps.marketplace.services.send_buyer_confirmation_email")
    @patch("apps.marketplace.models.Order.objects")
    def test_whatsapp_failure_does_not_prevent_existing_emails(self, objects, buyer, seller, whatsapp):
        from apps.marketplace.services import _send_emails_background

        objects.select_related.return_value.prefetch_related.return_value.get.return_value = sample_order()
        _send_emails_background(101)
        buyer.assert_called_once()
        seller.assert_called_once()
        whatsapp.assert_called_once_with(101)
