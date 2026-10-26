from decimal import Decimal
from unittest.mock import patch

import pytest

from apps.marketplace.manual_discount import apply_manual_discount
from apps.marketplace.models import Order


@pytest.mark.django_db
def test_manual_discount_reconciles_totals():
    # No invoice or external payment is needed to check calculation.
    with patch.object(Order.objects, "select_for_update") as locked:
        order = locked.return_value.get.return_value
        order.status = Order.STATUS_PENDING
        order.payment_status = "unpaid"
        order.subtotal = Decimal("304.87")
        order.discount_total = Decimal("0.00")
        order.manual_discount_amount = Decimal("0.00")
        order.delivery_fee = Decimal("0.00")
        result = apply_manual_discount(1, title="Diwali Discount", amount=Decimal("60.87"))
        assert result.total == Decimal("244.00")
        assert result.manual_discount_title == "Diwali Discount"
        order.save.assert_called_once()


@pytest.mark.django_db
def test_manual_discount_rejects_paid_order():
    with patch.object(Order.objects, "select_for_update") as locked:
        order = locked.return_value.get.return_value
        order.status = Order.STATUS_PENDING
        order.payment_status = "paid"
        with pytest.raises(ValueError, match="Paid orders"):
            apply_manual_discount(1, title="Diwali", amount=Decimal("1.00"))
