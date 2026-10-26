"""Current downloadable invoice revisions, preserving previously issued documents."""

from decimal import Decimal
from types import SimpleNamespace

from django.core.mail import EmailMessage
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone

from rest_framework.exceptions import ValidationError

from .billing.models import Invoice, InvoiceRevision
from .billing.pdf_service import _private_url_fetcher
from .billing.vat_service import allocate_discount, extract_vat
from .models import Order, OrderEmailLog


def generate_current_invoice(order):
    from weasyprint import HTML

    invoice = Invoice.objects.select_related("order").get(order=order)
    items = list(order.items.order_by("id"))
    discounts = allocate_discount(order.discount_total, [item.line_total for item in items])
    lines = []
    groups = {}
    for item, discount in zip(items, discounts):
        gross = item.line_total - discount
        net, vat = extract_vat(gross, item.vat_rate)
        lines.append(
            SimpleNamespace(
                description=item.product_name,
                sku=item.sku,
                quantity=item.quantity,
                unit_price_inc_vat=item.unit_price,
                vat_rate=item.vat_rate,
                line_total_ex_vat=net,
                vat_amount=vat,
                line_total_inc_vat=gross,
                discount_inc_vat=discount,
            )
        )
        row = groups.setdefault(
            item.vat_rate, {"rate": item.vat_rate, "net": Decimal("0"), "vat": Decimal("0"), "gross": Decimal("0")}
        )
        row["net"] += net
        row["vat"] += vat
        row["gross"] += gross
    if order.delivery_fee:
        rate = Decimal(order.billing_snapshot.get("delivery_vat_rate", "0"))
        net, vat = extract_vat(order.delivery_fee, rate)
        lines.append(
            SimpleNamespace(
                description="Delivery / Bezorging",
                sku="",
                quantity=1,
                unit_price_inc_vat=order.delivery_fee,
                vat_rate=rate,
                line_total_ex_vat=net,
                vat_amount=vat,
                line_total_inc_vat=order.delivery_fee,
                discount_inc_vat=Decimal("0"),
            )
        )
        row = groups.setdefault(rate, {"rate": rate, "net": Decimal("0"), "vat": Decimal("0"), "gross": Decimal("0")})
        row["net"] += net
        row["vat"] += vat
        row["gross"] += order.delivery_fee
    current = SimpleNamespace(
        invoice_number=invoice.invoice_number,
        issue_date=invoice.issue_date,
        order_number=invoice.order_number,
        order_date=invoice.order_date,
        currency=invoice.currency,
        order=order,
        discount_total=order.discount_total,
        manual_discount_title=order.manual_discount_title,
        manual_discount_amount=order.manual_discount_amount,
        other_discount_total=order.discount_total - order.manual_discount_amount,
        delivery_total=order.delivery_fee,
        subtotal_ex_vat=sum((r["net"] for r in groups.values()), Decimal("0")),
        vat_total=sum((r["vat"] for r in groups.values()), Decimal("0")),
        total_inc_vat=order.total,
    )
    markup = render_to_string(
        "marketplace/billing/invoice.html",
        {
            "invoice": current,
            "seller": invoice.seller_snapshot,
            "customer": invoice.customer_snapshot,
            "items": lines,
            "vat_summary": [groups[rate] for rate in sorted(groups)],
        },
    )
    return HTML(string=markup, url_fetcher=_private_url_fetcher).write_pdf()


@transaction.atomic
def refresh_invoice(order_id):
    order = Order.objects.select_for_update().get(pk=order_id)
    if order.status in (Order.STATUS_CANCELLED, Order.STATUS_REJECTED):
        raise ValidationError("Cannot regenerate a cancelled or rejected order invoice.")
    if order.payment_method == "online" and order.payment_status != "paid":
        raise ValidationError("Online invoice requires successful payment.")
    invoice = Invoice.objects.filter(order=order).first()
    if not invoice:
        from .billing.invoice_service import create_invoice

        invoice = create_invoice(order)
    if (
        invoice.total_inc_vat == order.total
        and invoice.discount_total == order.discount_total
        and not InvoiceRevision.objects.filter(invoice=invoice).exists()
    ):
        return invoice
    latest = InvoiceRevision.objects.filter(invoice=invoice).order_by("-created_at", "-id").first()
    if latest and latest.total == order.total and latest.discount_title == order.manual_discount_title:
        return invoice
    binary = generate_current_invoice(order)
    InvoiceRevision.objects.create(
        invoice=invoice,
        content=binary,
        total=order.total,
        discount_title=order.manual_discount_title,
        discount_total=order.discount_total,
    )
    return invoice


def current_invoice_pdf(invoice):
    latest = InvoiceRevision.objects.filter(invoice=invoice).order_by("-created_at", "-id").first()
    if latest:
        return bytes(latest.content)
    from .billing.pdf_service import invoice_pdf

    return invoice_pdf(invoice)


def resend_current_invoice(order_id):
    invoice = refresh_invoice(order_id)
    order = invoice.order
    if not order.customer_email:
        raise ValidationError("This order has no buyer email address.")
    shop_name = order.shop.name
    subject = f"Factuur van {shop_name}" if order.language == "nl" else f"Invoice from {shop_name}"
    message = EmailMessage(
        subject=subject,
        body=f"Attached is the latest invoice for order {order.order_number}. / Bijgevoegd de bijgewerkte factuur.",
        to=[order.customer_email],
    )
    message.attach(f"{invoice.invoice_number}.pdf", current_invoice_pdf(invoice), "application/pdf")
    log = OrderEmailLog.objects.create(
        order=order, email_type=OrderEmailLog.EMAIL_TYPE_INVOICE_RESEND, recipient=order.customer_email
    )
    try:
        message.send(fail_silently=False)
    except Exception as exc:
        log.status = OrderEmailLog.STATUS_FAILED
        log.error_message = str(exc)[:1000]
        log.save(update_fields=["status", "error_message"])
        raise
    log.status = OrderEmailLog.STATUS_SENT
    log.sent_at = timezone.now()
    log.save(update_fields=["status", "sent_at"])
    return invoice
