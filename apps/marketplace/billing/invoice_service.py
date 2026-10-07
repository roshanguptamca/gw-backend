from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.marketplace.models import Order, Shop, ShopSettings

from .models import Invoice, InvoiceItem, InvoiceSequence
from .pdf_service import snapshot_logo
from .vat_service import allocate_discount, extract_vat


def seller_snapshot(shop, settings):
    return {
        "shop_name": shop.name,
        "legal_business_name": settings.legal_business_name or shop.name,
        "address_line1": settings.billing_address_line1 or shop.address,
        "address_line2": settings.billing_address_line2,
        "postcode": settings.billing_postcode or shop.postal_code,
        "city": settings.billing_city or shop.city,
        "country": settings.billing_country or shop.country,
        "kvk_number": settings.kvk_number,
        "vat_number": settings.vat_number,
        "iban": settings.invoice_iban,
        "footer": settings.invoice_footer,
        "logo": snapshot_logo(shop),
    }


@transaction.atomic
def create_invoice(order):
    """One seller per existing Order; lock shop first to serialize its sequence."""
    shop = Shop.objects.select_for_update().get(pk=order.shop_id)
    order = Order.objects.select_for_update().get(pk=order.pk)
    existing = Invoice.objects.filter(order=order, shop=shop).first()
    if existing:
        return existing
    if order.status in (Order.STATUS_CANCELLED, Order.STATUS_REJECTED):
        raise ValueError("Cannot issue an invoice for a cancelled or rejected order.")
    if order.payment_method == "online" and order.payment_status != "paid":
        raise ValueError("Online orders must have successful payment before invoicing.")
    settings, _ = ShopSettings.objects.get_or_create(shop=shop)
    items = list(order.items.order_by("id"))
    if not items or any(item.product_id and item.product.shop_id != shop.id for item in items):
        raise ValueError("Invoice items must belong to the order's shop.")
    if any(item.quantity < 1 or item.line_total < 0 for item in items):
        raise ValueError("Invalid invoice item quantity or amount.")
    if sum((item.line_total for item in items), Decimal("0")) != order.subtotal:
        raise ValueError("Order merchandise does not reconcile with its subtotal.")
    if order.subtotal - order.discount_total + order.delivery_fee != order.total or order.delivery_fee < 0:
        raise ValueError("Order totals do not reconcile.")
    discounts = allocate_discount(order.discount_total, [item.line_total for item in items])
    issue_date = timezone.localdate()
    sequence, _ = InvoiceSequence.objects.get_or_create(shop=shop, year=issue_date.year)
    sequence.last_number += 1
    sequence.save(update_fields=["last_number"])
    # Shop ID disambiguates seller-configurable prefixes without imposing a global prefix registry.
    prefix = f"{settings.invoice_prefix}-{shop.pk}" if settings.invoice_prefix else f"SHOP{shop.pk}"
    lines = []
    for item, discount in zip(items, discounts):
        gross = item.line_total - discount
        net, vat = extract_vat(gross, item.vat_rate)
        lines.append(
            {
                "order_item": item,
                "description": item.product_name,
                "sku": item.sku,
                "quantity": item.quantity,
                "unit_price_inc_vat": item.unit_price,
                "vat_rate": item.vat_rate,
                "unit_price_ex_vat": (item.unit_price / (Decimal("1") + item.vat_rate / Decimal("100"))).quantize(
                    Decimal("0.000001")
                ),
                "discount_inc_vat": discount,
                "line_total_ex_vat": net,
                "vat_amount": vat,
                "line_total_inc_vat": gross,
            }
        )
    if order.delivery_fee:
        rate = Decimal(order.billing_snapshot.get("delivery_vat_rate", "0.00"))
        net, vat = extract_vat(order.delivery_fee, rate)
        lines.append(
            {
                "description": "Delivery / Bezorging",
                "kind": "delivery",
                "quantity": 1,
                "unit_price_inc_vat": order.delivery_fee,
                "vat_rate": rate,
                "unit_price_ex_vat": (order.delivery_fee / (Decimal("1") + rate / Decimal("100"))).quantize(
                    Decimal("0.000001")
                ),
                "line_total_ex_vat": net,
                "vat_amount": vat,
                "line_total_inc_vat": order.delivery_fee,
            }
        )
    snapshot = order.billing_snapshot
    invoice = Invoice.objects.create(
        order=order,
        shop=shop,
        customer=order.customer,
        invoice_number=f"{prefix}-{issue_date.year}-{sequence.last_number:06d}",
        issue_date=issue_date,
        order_number=order.order_number,
        order_date=order.created_at,
        currency=snapshot.get("currency") or order.fulfillment_snapshot.get("currency") or settings.currency,
        subtotal_ex_vat=sum((line["line_total_ex_vat"] for line in lines), Decimal("0")),
        vat_total=sum((line["vat_amount"] for line in lines), Decimal("0")),
        total_inc_vat=order.total,
        discount_total=order.discount_total,
        delivery_total=order.delivery_fee,
        seller_snapshot=snapshot.get("seller") or seller_snapshot(shop, settings),
        customer_snapshot=snapshot.get("customer")
        or {
            "name": order.customer_name,
            "email": order.customer_email,
            "address": order.delivery_address,
        },
    )
    InvoiceItem.objects.bulk_create([InvoiceItem(invoice=invoice, **line) for line in lines])
    return invoice
