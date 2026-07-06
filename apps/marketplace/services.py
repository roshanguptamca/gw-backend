import logging
import re
import threading
from decimal import Decimal
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.text import slugify

from rest_framework import serializers

logger = logging.getLogger(__name__)

from .models import (
    Category,
    Coupon,
    Order,
    OrderCancellationRequest,
    OrderItem,
    Product,
    SellerProfile,
    Shop,
    ShopSettings,
)

User = get_user_model()

DEFAULT_SELLER_CATEGORIES = ["Featured", "Snacks", "Meals", "Drinks"]


def generate_unique_slug(model, value, *, shop=None):
    base = slugify(value)[:45] or "item"
    slug = base
    counter = 2
    qs = model.objects.all()
    if shop is not None and hasattr(model, "shop"):
        qs = qs.filter(shop=shop)
    while qs.filter(slug=slug).exists():
        suffix = f"-{counter}"
        slug = f"{base[: 50 - len(suffix)]}{suffix}"
        counter += 1
    return slug


def create_default_categories_for_shop(shop):
    for name in DEFAULT_SELLER_CATEGORIES:
        Category.objects.get_or_create(
            shop=shop,
            slug=slugify(name),
            defaults={"name": name, "is_active": True},
        )


@transaction.atomic
def create_seller_with_shop(
    *,
    email,
    password,
    first_name,
    last_name,
    business_name,
    phone="",
    city="",
    address="",
    created_by=None,
):
    user = User.objects.create_user(
        username=email,
        email=email,
        password=password,
        first_name=first_name,
        last_name=last_name,
        is_staff=False,
        is_active=True,
    )
    profile = SellerProfile.objects.create(
        user=user,
        business_name=business_name,
        phone=phone,
        city=city,
        address=address,
        created_by=created_by,
        is_active=True,
    )
    shop = Shop.objects.create(
        owner=user,
        seller_profile=profile,
        name=business_name,
        slug=generate_unique_slug(Shop, business_name),
        city=city,
        pickup_available=True,
        is_active=True,
        is_approved=False,
    )
    ShopSettings.objects.create(shop=shop)
    create_default_categories_for_shop(shop)
    return user, profile, shop


def active_coupon_for_shop(shop, code):
    if not code:
        return None
    now = timezone.now()
    return Coupon.objects.filter(
        Q(starts_at__isnull=True) | Q(starts_at__lte=now),
        Q(ends_at__isnull=True) | Q(ends_at__gte=now),
        shop=shop,
        code__iexact=code.strip(),
        active=True,
    ).first()


def calculate_discount(coupon, subtotal):
    if not coupon:
        return Decimal("0.00")
    if coupon.usage_limit is not None and coupon.used_count >= coupon.usage_limit:
        raise serializers.ValidationError({"coupon_code": "This coupon has reached its usage limit."})
    if subtotal < coupon.min_order_amount:
        raise serializers.ValidationError({"coupon_code": "Order total is below this coupon minimum."})
    if coupon.discount_type == Coupon.DISCOUNT_PERCENTAGE:
        discount = subtotal * (coupon.discount_value / Decimal("100"))
    else:
        discount = coupon.discount_value
    return min(discount, subtotal).quantize(Decimal("0.01"))


def next_order_number():
    return f"GW{timezone.now():%Y%m%d}{uuid4().hex[:8].upper()}"


@transaction.atomic
def _create_order_atomic(payload, user=None):
    """Create the order and all related records inside a single DB transaction.
    Email sending deliberately lives OUTSIDE this function so that a slow or
    failing SMTP connection never holds the transaction open."""
    shop = Shop.objects.select_for_update().get(id=payload["shop_id"], is_active=True, is_approved=True)
    items = payload.get("items") or []
    if not items:
        raise serializers.ValidationError({"items": "At least one item is required."})

    product_ids = [item.get("product_id") for item in items]
    products = {
        product.id: product
        for product in Product.objects.select_for_update().filter(
            id__in=product_ids,
            shop=shop,
            is_active=True,
            is_approved=True,
        )
    }
    subtotal = Decimal("0.00")
    order_lines = []
    for item in items:
        product = products.get(item.get("product_id"))
        if not product:
            raise serializers.ValidationError({"items": "One or more products are unavailable for this shop."})
        quantity = int(item.get("quantity") or 0)
        if quantity <= 0:
            raise serializers.ValidationError({"items": "Quantity must be greater than zero."})
        if product.stock_quantity < quantity:
            raise serializers.ValidationError({"items": f"{product.name} does not have enough stock."})
        line_total = (product.price * quantity).quantize(Decimal("0.01"))
        subtotal += line_total
        order_lines.append((product, quantity, line_total))

    settings = getattr(shop, "settings", None)
    if settings and subtotal < settings.min_order_amount:
        raise serializers.ValidationError({"total": "Order total is below this shop minimum."})

    coupon = active_coupon_for_shop(shop, payload.get("coupon_code"))
    discount_total = calculate_discount(coupon, subtotal)
    delivery_fee = Decimal("0.00")
    delivery_zone = payload.get("delivery_zone") or ""
    if payload.get("order_type") == "delivery":
        if not shop.delivery_available:
            raise serializers.ValidationError({"order_type": "Delivery is not available for this shop."})
        if settings:
            if settings.free_delivery_above and subtotal >= settings.free_delivery_above:
                delivery_fee = Decimal("0.00")
            elif delivery_zone == "international":
                delivery_fee = settings.international_delivery_fee
            else:
                delivery_fee = settings.local_delivery_fee
        else:
            # No shop settings — use safe defaults rather than free
            delivery_fee = Decimal("10.00") if delivery_zone == "international" else Decimal("5.00")
    elif not shop.pickup_available:
        raise serializers.ValidationError({"order_type": "Pickup is not available for this shop."})

    total = (subtotal - discount_total + delivery_fee).quantize(Decimal("0.01"))
    order = Order.objects.create(
        shop=shop,
        customer=user if user and user.is_authenticated else None,
        order_number=next_order_number(),
        customer_name=payload["customer_name"],
        customer_email=payload.get("customer_email", ""),
        customer_phone=payload["customer_phone"],
        delivery_address=payload.get("delivery_address", ""),
        order_type=payload.get("order_type", "pickup"),
        delivery_zone=delivery_zone,
        payment_method=payload.get("payment_method", "cash"),
        subtotal=subtotal,
        discount_total=discount_total,
        delivery_fee=delivery_fee,
        total=total,
        customer_note=payload.get("customer_note", ""),
        terms_accepted=bool(payload.get("terms_accepted", False)),
        status=(
            Order.STATUS_ACCEPTED
            if settings and settings.order_acceptance_mode == ShopSettings.ORDER_ACCEPTANCE_AUTO
            else Order.STATUS_PENDING
        ),
    )
    for product, quantity, line_total in order_lines:
        OrderItem.objects.create(
            order=order,
            product=product,
            product_name=product.name,
            unit_price=product.price,
            quantity=quantity,
            line_total=line_total,
        )
        product.stock_quantity -= quantity
        product.save(update_fields=["stock_quantity", "updated_at"])
    if coupon:
        coupon.used_count += 1
        coupon.save(update_fields=["used_count"])

    return order


def _send_emails_background(order_id: int) -> None:
    """Fire-and-forget helper: fetch the order and send both emails in a daemon thread.
    Using order_id (int) instead of the ORM object avoids passing a Django model
    instance across thread boundaries (closed DB connections, stale state, etc.)."""
    from .models import Order  # local import to avoid circular refs at module load

    try:
        order = Order.objects.select_related("shop__owner", "shop__settings").prefetch_related("items").get(pk=order_id)
        send_buyer_confirmation_email(order)
    except Exception:  # noqa: BLE001
        logger.exception("Background email: buyer confirmation failed for order %s", order_id)

    try:
        order = Order.objects.select_related("shop__owner", "shop__settings").prefetch_related("items").get(pk=order_id)
        send_seller_notification_email(order)
    except Exception:  # noqa: BLE001
        logger.exception("Background email: seller notification failed for order %s", order_id)


def _unique_username_from_email(email):
    """Derive a unique username from an email's local-part, reusing the same
    User model uniqueness rules as normal registration."""
    base = re.sub(r"[^\w.]+", "", email.split("@")[0]).lower() or "customer"
    username = base
    counter = 1
    while User.objects.filter(username=username).exists():
        counter += 1
        username = f"{base}{counter}"
    return username


def _create_account_for_order(order, payload):
    """Create a customer account during checkout by reusing the existing
    GuideWisey registration flow (UserRegistrationSerializer), so the new
    user gets the same email-confirmation flow as any other signup."""
    from apps.accounts.serializers import UserRegistrationSerializer

    email = (payload.get("customer_email") or "").strip()
    password = payload.get("password")
    password_confirm = payload.get("password_confirm")
    if not email or not password:
        return None

    reg_serializer = UserRegistrationSerializer(
        data={
            "username": _unique_username_from_email(email),
            "email": email,
            "password": password,
            "password2": password_confirm,
        }
    )
    try:
        reg_serializer.is_valid(raise_exception=True)
        new_user = reg_serializer.save()
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to create account during order checkout for %s: %s", email, exc)
        return None

    order.customer = new_user
    order.save(update_fields=["customer"])
    return new_user


def create_order_from_payload(payload, user=None):
    """Public entry point. Commits the DB transaction first, then sends emails
    in a background daemon thread so the HTTP response is immediate."""
    order = _create_order_atomic(payload, user=user)

    if not (user and user.is_authenticated) and payload.get("create_account"):
        _create_account_for_order(order, payload)

    # Dispatch emails to a background daemon thread — caller gets instant response.
    t = threading.Thread(target=_send_emails_background, args=(order.pk,), daemon=True)
    t.start()
    logger.info("Order %s created; email thread %s dispatched.", order.order_number, t.name)

    return order


def send_buyer_confirmation_email(order):
    """Send HTML order confirmation to buyer (if email provided)."""
    if not order.customer_email:
        return
    currency = getattr(getattr(order.shop, "settings", None), "currency", "EUR")
    items_html = "".join(
        f"<tr><td>{item.product_name}</td><td style='text-align:center'>{item.quantity}</td>"
        f"<td style='text-align:right'>{item.unit_price} {currency}</td>"
        f"<td style='text-align:right'>{item.line_total} {currency}</td></tr>"
        for item in order.items.all()
    )
    delivery_label = "🚚 Delivery" if order.order_type == "delivery" else "🏪 Pickup"
    html_message = f"""
    <h2>Order Confirmed – {order.order_number}</h2>
    <p>Thank you, <strong>{order.customer_name}</strong>! Your order from <strong>{order.shop.name}</strong> has been placed.</p>
    <table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;width:100%">
      <thead><tr><th>Product</th><th>Qty</th><th>Unit price</th><th>Total</th></tr></thead>
      <tbody>{items_html}</tbody>
    </table>
    <p><strong>Delivery method:</strong> {delivery_label}</p>
    {"<p><strong>Delivery fee:</strong> " + str(order.delivery_fee) + " " + currency + "</p>" if order.delivery_fee else ""}
    {"<p><strong>Discount:</strong> -" + str(order.discount_total) + " " + currency + "</p>" if order.discount_total else ""}
    <p><strong>Grand total:</strong> {order.total} {currency}</p>
    <p><strong>Status:</strong> {order.status}</p>
    """
    send_mail(
        subject=f"Order {order.order_number} confirmed – {order.shop.name}",
        message=f"Order {order.order_number} confirmed. Total: {order.total} {currency}.",
        from_email=None,
        recipient_list=[order.customer_email],
        html_message=html_message,
        fail_silently=True,
    )


def send_seller_notification_email(order):
    """Notify seller of new order."""
    seller_email = getattr(order.shop.owner, "email", None)
    if not seller_email:
        return
    currency = getattr(getattr(order.shop, "settings", None), "currency", "EUR")
    delivery_label = "🚚 Delivery" if order.order_type == "delivery" else "🏪 Pickup"
    message = (
        f"New order {order.order_number} received!\n\n"
        f"Customer: {order.customer_name}\n"
        f"Phone: {order.customer_phone}\n"
        f"Email: {order.customer_email or 'not provided'}\n"
        f"Delivery method: {delivery_label}\n"
        f"Total: {order.total} {currency}\n"
    )
    send_mail(
        subject=f"New order {order.order_number} – {order.shop.name}",
        message=message,
        from_email=None,
        recipient_list=[seller_email],
        fail_silently=True,
    )


def link_guest_orders_to_user(user):
    """After registration, link any guest orders with matching email to the new user account."""
    if not user.email:
        return 0
    updated = Order.objects.filter(
        customer__isnull=True,
        customer_email__iexact=user.email,
    ).update(customer=user)
    return updated


def send_cancellation_request_email_to_seller(cancel_request):
    """Notify seller that a buyer submitted a cancellation request."""
    seller_email = getattr(cancel_request.shop.owner, "email", None)
    if not seller_email:
        return
    order = cancel_request.order
    currency = getattr(getattr(order.shop, "settings", None), "currency", "EUR")
    reason_label = dict(OrderCancellationRequest.REASON_CHOICES).get(cancel_request.reason, cancel_request.reason)
    html_message = f"""
    <h2>Cancellation Request – {order.order_number}</h2>
    <p>A buyer has requested to cancel order <strong>{order.order_number}</strong>.</p>
    <table cellpadding="6" style="border-collapse:collapse">
      <tr><td><strong>Order number:</strong></td><td>{order.order_number}</td></tr>
      <tr><td><strong>Order total:</strong></td><td>{order.total} {currency}</td></tr>
      <tr><td><strong>Buyer name:</strong></td><td>{order.customer_name}</td></tr>
      <tr><td><strong>Buyer email:</strong></td><td>{order.customer_email or "not provided"}</td></tr>
      <tr><td><strong>Buyer phone:</strong></td><td>{order.customer_phone or "not provided"}</td></tr>
      <tr><td><strong>Cancellation reason:</strong></td><td>{reason_label}</td></tr>
      {"<tr><td><strong>Buyer message:</strong></td><td>" + cancel_request.message + "</td></tr>" if cancel_request.message else ""}
    </table>
    <p>Please log in to your seller dashboard to review and approve or reject this request.</p>
    """
    send_mail(
        subject=f"Cancellation request for order {order.order_number}",
        message=(
            f"Cancellation request for order {order.order_number}.\n"
            f"Buyer: {order.customer_name} | Reason: {reason_label}\n"
            "Please review in your seller dashboard."
        ),
        from_email=None,
        recipient_list=[seller_email],
        html_message=html_message,
        fail_silently=True,
    )


def send_cancellation_result_email_to_buyer(cancel_request):
    """Notify buyer of seller's decision on their cancellation request."""
    buyer_email = cancel_request.order.customer_email
    if not buyer_email:
        return
    order = cancel_request.order
    currency = getattr(getattr(order.shop, "settings", None), "currency", "EUR")
    approved = cancel_request.status == OrderCancellationRequest.STATUS_APPROVED
    subject = f"Your cancellation request for {order.order_number} was {'approved' if approved else 'rejected'}"
    decision_text = "approved" if approved else "rejected"
    color = "#28a745" if approved else "#dc3545"
    html_message = f"""
    <h2>Cancellation Request {decision_text.title()}</h2>
    <p>Hi <strong>{order.customer_name}</strong>,</p>
    <p>Your cancellation request for order <strong>{order.order_number}</strong>
       from <strong>{order.shop.name}</strong> has been
       <span style="color:{color}"><strong>{decision_text}</strong></span>.</p>
    {"<p>Your order total of <strong>" + str(order.total) + " " + currency + "</strong> will be refunded according to the shop's refund policy.</p>" if approved else ""}
    {"<p><strong>Seller note:</strong> " + cancel_request.seller_note + "</p>" if cancel_request.seller_note else ""}
    <p>If you have questions, please contact the shop directly.</p>
    """
    send_mail(
        subject=subject,
        message=f"Your cancellation request for order {order.order_number} was {decision_text}.",
        from_email=None,
        recipient_list=[buyer_email],
        html_message=html_message,
        fail_silently=True,
    )


ALLOWED_ORDER_TRANSITIONS = {
    Order.STATUS_PENDING: {Order.STATUS_ACCEPTED, Order.STATUS_REJECTED, Order.STATUS_CANCELLED},
    Order.STATUS_ACCEPTED: {Order.STATUS_PREPARING, Order.STATUS_CANCELLED},
    Order.STATUS_PREPARING: {Order.STATUS_READY, Order.STATUS_CANCELLED},
    Order.STATUS_READY: {Order.STATUS_OUT_FOR_DELIVERY, Order.STATUS_COMPLETED},
    Order.STATUS_OUT_FOR_DELIVERY: {Order.STATUS_COMPLETED},
}


def update_order_status(order, new_status):
    if new_status not in dict(Order.ORDER_STATUS):
        raise serializers.ValidationError({"status": "Invalid order status."})
    if new_status == order.status:
        return order
    if new_status not in ALLOWED_ORDER_TRANSITIONS.get(order.status, set()):
        raise serializers.ValidationError({"status": f"Cannot change order from {order.status} to {new_status}."})
    order.status = new_status
    order.save(update_fields=["status", "updated_at"])
    return order
