"""Seller-initiated fixed order discounts, with server-side reconciliation."""

from decimal import Decimal

from django.db import transaction

from .models import Order


@transaction.atomic
def apply_manual_discount(order_id, *, title, amount):
    order = Order.objects.select_for_update().get(pk=order_id)
    if order.status in (Order.STATUS_CANCELLED, Order.STATUS_REJECTED):
        raise ValueError("Cannot discount a cancelled or rejected order.")
    if order.payment_status in ("paid", "refunded"):
        raise ValueError("Paid orders require a separate refund or credit note.")
    amount = Decimal(amount).quantize(Decimal("0.01"))
    if amount < 0 or amount > order.subtotal - (order.discount_total - order.manual_discount_amount):
        raise ValueError("Discount must be between zero and the remaining merchandise subtotal.")
    if amount and not title.strip():
        raise ValueError("A discount title is required.")
    previous = order.manual_discount_amount
    order.manual_discount_title = title.strip() if amount else ""
    order.manual_discount_amount = amount
    order.discount_total = order.discount_total - previous + amount
    order.total = order.subtotal - order.discount_total + order.delivery_fee
    order.save(
        update_fields=["manual_discount_title", "manual_discount_amount", "discount_total", "total", "updated_at"]
    )
    if order.invoices.exists():
        from .invoice_refresh import refresh_invoice

        refresh_invoice(order.pk)
    return order
