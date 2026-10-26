from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from rest_framework.exceptions import ValidationError

from apps.marketplace.models import Order
from apps.marketplace.services import ALLOWED_ORDER_TRANSITIONS, update_order_status


class SellerDirectCompletionTests(SimpleTestCase):
    def test_active_orders_can_be_completed_directly(self):
        for status in (
            Order.STATUS_PENDING,
            Order.STATUS_ACCEPTED,
            Order.STATUS_PREPARING,
            Order.STATUS_READY,
            Order.STATUS_OUT_FOR_DELIVERY,
        ):
            with self.subTest(status=status):
                self.assertIn(Order.STATUS_COMPLETED, ALLOWED_ORDER_TRANSITIONS[status])
                order = SimpleNamespace(status=status, order_number="TEST-1", save=Mock())
                with patch("apps.marketplace.services.send_order_status_update_email_to_buyer") as notify:
                    result = update_order_status(order, Order.STATUS_COMPLETED)
                self.assertIs(result, order)
                self.assertEqual(order.status, Order.STATUS_COMPLETED)
                order.save.assert_called_once_with(update_fields=["status", "updated_at"])
                notify.assert_called_once_with(order, status)

    def test_terminal_orders_cannot_be_reopened_or_completed(self):
        for status in (Order.STATUS_COMPLETED, Order.STATUS_CANCELLED, Order.STATUS_REJECTED):
            with self.subTest(status=status):
                order = SimpleNamespace(status=status, order_number="TEST-1", save=Mock())
                for target in (Order.STATUS_ACCEPTED, Order.STATUS_COMPLETED):
                    if target == status:
                        continue
                    with self.assertRaises(ValidationError):
                        update_order_status(order, target)
                order.save.assert_not_called()
