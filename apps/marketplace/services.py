import logging
import re
import threading
import time
from decimal import Decimal
from urllib.parse import urlsplit
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.mail import EmailMultiAlternatives, send_mail
from django.db import IntegrityError, OperationalError, transaction
from django.db.models import F, Q
from django.utils import formats, timezone, translation
from django.utils.html import escape
from django.utils.text import slugify

from rest_framework import serializers
from rest_framework.exceptions import APIException

logger = logging.getLogger(__name__)


class ShopMinimumOrderNotMet(APIException):
    status_code = 400
    default_code = "SHOP_MINIMUM_ORDER_NOT_MET"

    def __init__(self, shop, subtotal, minimum):
        self.detail = {
            "code": self.default_code,
            "message": "The minimum order for this shop has not been reached.",
            "shop_id": shop.id,
            "shop_name": shop.name,
            "minimum_order_amount": str(minimum),
            "current_subtotal": str(subtotal),
            "remaining_amount": str((minimum - subtotal).quantize(Decimal("0.01"))),
        }


# SQLite only allows a single writer at a time. Even with WAL mode and a
# 20s busy_timeout configured, a request can still occasionally hit
# "database is locked" if it lands in the narrow window right as another
# write transaction is being set up. Rather than surface a raw 500 to the
# shopper for what's usually a sub-second contention blip, retry the whole
# order-creation transaction a few times with a short backoff. This is a
# no-op on Postgres (production) since OperationalError there means
# something else entirely and won't match this narrow retry count anyway.
_DB_LOCK_MAX_RETRIES = 3
_DB_LOCK_RETRY_DELAY_SECONDS = 0.3


def _is_database_locked_error(exc: BaseException) -> bool:
    return isinstance(exc, OperationalError) and "database is locked" in str(exc).lower()


from . import ordering
from .models import (
    Category,
    Coupon,
    Order,
    OrderCancellationRequest,
    OrderEmailLog,
    OrderItem,
    Product,
    SellerProfile,
    Shop,
    ShopSettings,
)

User = get_user_model()

DEFAULT_SELLER_CATEGORIES = ["Featured", "Snacks", "Meals", "Drinks"]


def localized_field(instance, field, language):
    translations = getattr(instance, "translations", None) or {}
    values = translations.get(field, {})
    return values.get(language) or values.get("en") or getattr(instance, field, "")


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
    ShopSettings.objects.create(
        shop=shop,
        legal_business_name=business_name,
        billing_address_line1=address,
        billing_city=city,
    )
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

    rule_errors = [
        error
        for product, quantity, line_total in order_lines
        for error in ordering.product_rule_violations(product, quantity, line_total)
    ]
    if rule_errors:
        raise ordering.OrderRuleViolation(rule_errors)

    settings = getattr(shop, "settings", None)
    language = payload.get("language", "en")
    if settings and subtotal < settings.min_order_amount:
        raise ShopMinimumOrderNotMet(shop, subtotal, settings.min_order_amount)

    order_type = payload.get("order_type", "pickup")
    delivery_address = (payload.get("delivery_address") or "").strip()
    if order_type == "delivery":
        if not shop.delivery_available:
            raise serializers.ValidationError({"order_type": "Delivery is not available for this shop."})
        if not delivery_address:
            raise serializers.ValidationError({"delivery_address": "A delivery address is required."})
    elif not shop.pickup_available:
        raise serializers.ValidationError({"order_type": "Pickup is not available for this shop."})

    lead_minutes = ordering.required_lead_minutes(product for product, _, _ in order_lines)
    pickup_slot = None
    if order_type == "pickup":
        pickup_slot = ordering.validate_pickup_slot(
            shop, lead_minutes, payload.get("pickup_slot_start"), ordering.current_time()
        )

    coupon = active_coupon_for_shop(shop, payload.get("coupon_code"))
    discount_total = calculate_discount(coupon, subtotal)
    delivery_fee = Decimal("0.00")
    delivery_zone = payload.get("delivery_zone") or ""
    if order_type == "delivery":
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
    total = (subtotal - discount_total + delivery_fee).quantize(Decimal("0.01"))
    pickup_address = ", ".join(
        value
        for value in (
            settings.pickup_address_line_1 if settings else "",
            settings.pickup_address_line_2 if settings else "",
            (
                " ".join(value for value in (settings.pickup_postal_code, settings.pickup_city) if value)
                if settings
                else ""
            ),
            settings.pickup_country if settings else "",
        )
        if value
    )
    fulfillment_snapshot = {
        "order_type": order_type,
        "shop_name": shop.name,
        "shop_address": pickup_address or shop.address,
        "shop_phone": shop.phone,
        "shop_email": shop.email,
        "whatsapp_url": settings.whatsapp_url if settings else "",
        "whatsapp_group_url": settings.whatsapp_group_url if settings else "",
        "minimum_order_amount": str(settings.min_order_amount) if settings else "0.00",
        "currency": settings.currency if settings else "EUR",
        "pickup_address_line_1": settings.pickup_address_line_1 if settings else "",
        "pickup_address_line_2": settings.pickup_address_line_2 if settings else "",
        "pickup_postal_code": settings.pickup_postal_code if settings else "",
        "pickup_city": settings.pickup_city if settings else "",
        "pickup_country": settings.pickup_country if settings else "",
        "delivery_area": localized_field(shop, "delivery_area", language) if order_type == "delivery" else "",
        "pickup_instructions": (
            localized_field(settings, "pickup_instructions", language) if settings and order_type == "pickup" else ""
        ),
        "delivery_instructions": (
            localized_field(settings, "delivery_notes", language) if settings and order_type == "delivery" else ""
        ),
        "required_lead_time_minutes": lead_minutes,
        "required_lead_time_hours": ordering.lead_time_hours(lead_minutes),
        "pickup_timezone": str(ordering.shop_timezone(shop)),
        "pickup_slot_start": pickup_slot.start.isoformat() if pickup_slot else "",
        "pickup_slot_end": pickup_slot.end.isoformat() if pickup_slot else "",
        "pickup_date": ordering.format_pickup_date(pickup_slot.start) if pickup_slot else "",
        "pickup_time": pickup_slot.as_dict()["label"] if pickup_slot else "",
    }
    from .billing.invoice_service import seller_snapshot

    billing_snapshot = {
        "seller": seller_snapshot(shop, settings or ShopSettings.objects.get_or_create(shop=shop)[0]),
        "customer": {
            "name": payload["customer_name"],
            "email": payload.get("customer_email", ""),
            "address": payload.get("billing_address") or delivery_address,
        },
        "currency": settings.currency if settings else "EUR",
        "delivery_vat_rate": str(settings.default_vat_rate) if settings else "0.00",
    }
    order = Order.objects.create(
        shop=shop,
        customer=user if user and user.is_authenticated else None,
        order_number=next_order_number(),
        customer_name=payload["customer_name"],
        customer_email=payload.get("customer_email", ""),
        customer_phone=payload["customer_phone"],
        delivery_address=delivery_address,
        fulfillment_snapshot=fulfillment_snapshot,
        billing_snapshot=billing_snapshot,
        pickup_slot_start=pickup_slot.start if pickup_slot else None,
        pickup_slot_end=pickup_slot.end if pickup_slot else None,
        order_type=order_type,
        delivery_zone=delivery_zone,
        payment_method=payload.get("payment_method", "cash"),
        language=language,
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
            vat_rate=(
                product.vat_rate if product.vat_rate is not None else Decimal(billing_snapshot["delivery_vat_rate"])
            ),
            sku=product.sku or "",
            selling_unit=ordering.selling_unit_of(product),
            units_per_pack=product.units_per_pack,
            weight_value=product.weight_value,
            weight_unit=product.weight_unit,
            physical_quantity=ordering.physical_quantity(product, quantity),
            total_weight_value=ordering.total_weight(product, quantity),
            ordering_rules_snapshot=ordering.ordering_rules(product),
        )
        product.stock_quantity -= quantity
        product.save(update_fields=["stock_quantity", "updated_at"])
    if coupon:
        coupon.used_count += 1
        coupon.save(update_fields=["used_count"])

    if order.payment_method != "online":
        from .billing.invoice_service import create_invoice

        create_invoice(order)
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


def _create_account_for_order(payload):
    """Create a customer account during checkout by reusing the existing
    GuideWisey registration flow (UserRegistrationSerializer), so the new
    user gets the same email-confirmation flow as any other signup.

    Raises serializers.ValidationError (never swallows errors) so a
    duplicate-email race — two near-simultaneous checkout submissions with
    the same email — surfaces as a clean ACCOUNT_ALREADY_EXISTS response
    instead of silently creating the order without an account, or bubbling
    up as an unhandled 500."""
    from apps.accounts.serializers import UserRegistrationSerializer

    email = (payload.get("customer_email") or "").strip()
    password = payload.get("password")
    password_confirm = payload.get("password_confirm")
    if not email or not password:
        raise serializers.ValidationError({"customer_email": "Email and password are required to create an account."})

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
        return reg_serializer.save()
    except serializers.ValidationError:
        # UserRegistrationSerializer.validate_email() already raises this when the
        # email is taken — re-raise with our stable code so the frontend can show
        # a "log in instead" CTA rather than a generic error.
        raise serializers.ValidationError(
            {
                "customer_email": ("An account already exists with this email. Please log in to track this order."),
                "code": "ACCOUNT_ALREADY_EXISTS",
            }
        )
    except IntegrityError:
        # Belt-and-suspenders: a concurrent request created the same email/username
        # between our validate() check and this save() — the DB unique constraint
        # is the real source of truth here, so treat it the same way.
        raise serializers.ValidationError(
            {
                "customer_email": ("An account already exists with this email. Please log in to track this order."),
                "code": "ACCOUNT_ALREADY_EXISTS",
            }
        )


def create_order_from_payload(payload, user=None):
    """Public entry point. Commits the DB transaction first, then sends emails
    in a background daemon thread so the HTTP response is immediate.

    When create_account is requested, the account is created FIRST inside the
    same atomic transaction as the order — if account creation fails (e.g. a
    duplicate email race), the whole transaction rolls back so we never end up
    with an order silently created without its requested account."""
    creating_account = not (user and user.is_authenticated) and payload.get("create_account")

    def _create():
        if creating_account:
            with transaction.atomic():
                new_user = _create_account_for_order(payload)
                return _create_order_atomic(payload, user=new_user)
        return _create_order_atomic(payload, user=user)

    order = None
    for attempt in range(1, _DB_LOCK_MAX_RETRIES + 1):
        try:
            order = _create()
            break
        except OperationalError as exc:
            if not _is_database_locked_error(exc) or attempt == _DB_LOCK_MAX_RETRIES:
                raise
            logger.warning(
                "Order creation hit 'database is locked' (attempt %s/%s); retrying shortly.",
                attempt,
                _DB_LOCK_MAX_RETRIES,
            )
            time.sleep(_DB_LOCK_RETRY_DELAY_SECONDS * attempt)

    # Dispatch emails to a background daemon thread — caller gets instant response.
    t = threading.Thread(target=_send_emails_background, args=(order.pk,), daemon=True)
    t.start()
    logger.info("Order %s created; email thread %s dispatched.", order.order_number, t.name)

    return order


def _send_and_log_order_email(order, email_type, recipient, send_fn):
    """Create a pending OrderEmailLog row, attempt to send, then update the
    log (and the matching Order.*_email_sent_at flag) based on the outcome.
    Re-raises on failure so callers can still see/report it, but the audit
    trail in OrderEmailLog is always left in a final (sent/failed) state."""
    log = OrderEmailLog.objects.create(
        order=order,
        email_type=email_type,
        recipient=recipient,
        status=OrderEmailLog.STATUS_PENDING,
    )
    try:
        send_fn()
    except Exception as exc:  # noqa: BLE001
        log.status = OrderEmailLog.STATUS_FAILED
        log.error_message = str(exc)[:2000]
        log.save(update_fields=["status", "error_message"])
        raise
    else:
        log.status = OrderEmailLog.STATUS_SENT
        log.sent_at = timezone.now()
        log.save(update_fields=["status", "sent_at"])
        if email_type == OrderEmailLog.EMAIL_TYPE_BUYER_CONFIRMATION:
            order.buyer_email_sent_at = log.sent_at
            order.save(update_fields=["buyer_email_sent_at"])
        elif email_type == OrderEmailLog.EMAIL_TYPE_SELLER_NOTIFICATION:
            order.seller_email_sent_at = log.sent_at
            order.save(update_fields=["seller_email_sent_at"])


def order_item_quantity_text(item):
    """Quantity description from the order item's snapshot (legacy items fall back to the count)."""
    if not item.selling_unit:
        return str(item.quantity)
    return ordering.describe_quantity(item, item.quantity)


def buyer_order_item_quantity_text(item, language):
    description = order_item_quantity_text(item)
    if language != "nl":
        return description
    for source, translated in (
        ("pieces", "stuks"),
        ("piece", "stuk"),
        ("packs", "verpakkingen"),
        ("pack", "verpakking"),
        ("plates", "borden"),
        ("plate", "bord"),
        ("boxes", "dozen"),
        ("box", "doos"),
        ("trays", "dienbladen"),
        ("tray", "dienblad"),
        ("bottles", "flessen"),
        ("bottle", "fles"),
    ):
        description = re.sub(rf"\b{source}\b", translated, description)
    return description


def _order_pickup_lines(order):
    """(date, time, lead hours) from the fulfilment snapshot; empty strings when not scheduled."""
    snapshot = order.fulfillment_snapshot or {}
    lead_hours = snapshot.get("required_lead_time_hours") or 0
    return snapshot.get("pickup_date", ""), snapshot.get("pickup_time", ""), lead_hours


def send_buyer_confirmation_email(order):
    """Send HTML order confirmation to buyer (if email provided)."""
    if not order.customer_email:
        return
    snapshot = order.fulfillment_snapshot or {}
    currency = snapshot.get("currency") or getattr(getattr(order.shop, "settings", None), "currency", "EUR")
    with translation.override(order.language):
        order_date = formats.date_format(timezone.localtime(order.created_at), "DATETIME_FORMAT")
    labels = (
        {
            "order_confirmed": "Bestelling bevestigd",
            "thank_you": "Bedankt",
            "placed": "Je bestelling van",
            "placed_suffix": "is geplaatst.",
            "order_date": "Besteldatum",
            "email": "e-mail",
            "phone": "telefoon",
            "whatsapp": "Word lid van de WhatsApp-groep",
            "product": "Product",
            "quantity": "Aantal",
            "unit_price": "Prijs per stuk",
            "total": "Totaal",
            "delivery": "Bezorgen",
            "pickup": "Afhalen",
            "delivery_method": "Bezorgmethode",
            "pickup_date": "Afhaaldatum",
            "pickup_time": "Afhaaltijd",
            "preparation": "Benodigde voorbereiding",
            "hours": "uur",
            "delivery_address": "Bezorgadres",
            "pickup_address": "Afhaaladres",
            "instructions": "Instructies",
            "contact": "Contact",
            "subtotal": "Subtotaal winkel",
            "fulfilment_cost": "Afhandelingskosten",
            "discount": "Korting",
            "grand_total": "Eindtotaal",
            "status": "Status",
            "your_note": "Je opmerking",
            "status_values": {
                "pending": "In afwachting",
                "accepted": "Geaccepteerd",
                "preparing": "Wordt bereid",
                "ready": "Klaar",
                "out_for_delivery": "Onderweg",
                "completed": "Voltooid",
                "cancelled": "Geannuleerd",
                "rejected": "Afgewezen",
            },
        }
        if order.language == "nl"
        else {
            "order_confirmed": "Order confirmed",
            "thank_you": "Thank you",
            "placed": "has been placed.",
            "placed_suffix": "",
            "order_date": "Order date",
            "email": "email",
            "phone": "phone",
            "whatsapp": "Join the shop WhatsApp group",
            "product": "Product",
            "quantity": "Qty",
            "unit_price": "Unit price",
            "total": "Total",
            "delivery": "Delivery",
            "pickup": "Pickup",
            "delivery_method": "Delivery method",
            "pickup_date": "Pickup date",
            "pickup_time": "Pickup time",
            "preparation": "Preparation requirement",
            "hours": "hours",
            "delivery_address": "Delivery address",
            "pickup_address": "Pickup address",
            "instructions": "Instructions",
            "contact": "Contact",
            "subtotal": "Shop subtotal",
            "fulfilment_cost": "Fulfilment cost",
            "discount": "Discount",
            "grand_total": "Grand total",
            "status": "Status",
            "your_note": "Your note",
            "status_values": {},
        }
    )
    shop_email = snapshot.get("shop_email", "")
    shop_phone = snapshot.get("shop_phone", "")
    whatsapp_group_url = snapshot.get("whatsapp_group_url", "")
    if whatsapp_group_url:
        parsed_group_url = urlsplit(whatsapp_group_url)
        if (
            parsed_group_url.scheme != "https"
            or parsed_group_url.hostname != "chat.whatsapp.com"
            or not re.fullmatch(r"/[A-Za-z0-9]+/?", parsed_group_url.path)
            or parsed_group_url.query
            or parsed_group_url.fragment
            or parsed_group_url.username
            or parsed_group_url.password
        ):
            whatsapp_group_url = ""
    pickup_date, pickup_time, lead_hours = _order_pickup_lines(order)
    items_html = "".join(
        f"<tr><td>{escape(item.product_name)}"
        f"{f'<br><small>SKU: {escape(item.sku)}</small>' if item.sku else ''}</td>"
        f"<td style='text-align:center'>{escape(buyer_order_item_quantity_text(item, order.language))}</td>"
        f"<td style='text-align:right'>{item.unit_price} {escape(currency)}</td>"
        f"<td style='text-align:right'>{item.line_total} {escape(currency)}</td></tr>"
        for item in order.items.all()
    )
    delivery_label = f"🚚 {labels['delivery']}" if order.order_type == "delivery" else f"🏪 {labels['pickup']}"
    fulfillment_address = order.delivery_address if order.order_type == "delivery" else snapshot.get("shop_address", "")
    instructions = snapshot.get(
        "delivery_instructions" if order.order_type == "delivery" else "pickup_instructions", ""
    )
    contact_html = "".join(
        f"<p><strong>{escape(labels[label])}:</strong> {escape(value)}</p>"
        for label, value in (("email", shop_email), ("phone", shop_phone))
        if value
    )
    whatsapp_html = (
        f'<p><a href="{escape(whatsapp_group_url)}">{escape(labels["whatsapp"])}</a></p>' if whatsapp_group_url else ""
    )
    html_message = f"""
    <h2>{escape(labels["order_confirmed"])} – {escape(order.order_number)}</h2>
    <p>{escape(labels["thank_you"])}, <strong>{escape(order.customer_name)}</strong>! {escape(labels["placed"])} <strong>{escape(snapshot.get("shop_name") or order.shop.name)}</strong> {escape(labels["placed_suffix"])}</p>
    <p><strong>{escape(labels["order_date"])}:</strong> {escape(order_date)}</p>
    {contact_html}
    {whatsapp_html}
    <table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;width:100%">
      <thead><tr><th>{escape(labels["product"])}</th><th>{escape(labels["quantity"])}</th><th>{escape(labels["unit_price"])}</th><th>{escape(labels["total"])}</th></tr></thead>
      <tbody>{items_html}</tbody>
    </table>
    <p><strong>{escape(labels["delivery_method"])}:</strong> {delivery_label}</p>
    {f"<p><strong>{escape(labels['pickup_date'])}:</strong> {escape(pickup_date)}</p>" if pickup_date else ""}
    {f"<p><strong>{escape(labels['pickup_time'])}:</strong> {escape(pickup_time)}</p>" if pickup_time else ""}
    {f"<p><strong>{escape(labels['preparation'])}:</strong> {lead_hours} {escape(labels['hours'])}</p>" if lead_hours else ""}
    {f"<p><strong>{escape(labels['delivery_address'] if order.order_type == 'delivery' else labels['pickup_address'])}:</strong> {escape(fulfillment_address)}</p>" if fulfillment_address else ""}
    {f"<p><strong>{escape(labels['instructions'])}:</strong> {escape(instructions)}</p>" if instructions else ""}
    <p><strong>{escape(labels['contact'])}:</strong> {escape(order.customer_phone)}{f" · {escape(order.customer_email)}" if order.customer_email else ""}</p>
    <p><strong>{escape(labels['subtotal'])}:</strong> {order.subtotal} {escape(currency)}</p>
    <p><strong>{escape(labels['fulfilment_cost'])}:</strong> {order.delivery_fee} {escape(currency)}</p>
    {f"<p><strong>{escape(labels['discount'])}:</strong> -{order.discount_total} {escape(currency)}</p>" if order.discount_total else ""}
    <p><strong>{escape(labels['grand_total'])}:</strong> {order.total} {escape(currency)}</p>
    <p><strong>{escape(labels['status'])}:</strong> {escape(labels['status_values'].get(order.status, order.status))}</p>
    {f"<p><strong>{escape(labels['your_note'])}:</strong> {escape(order.customer_note)}</p>" if order.customer_note else ""}
    """
    plain_items = "\n".join(
        f"- {item.product_name}{f' [{item.sku}]' if item.sku else ''}: {buyer_order_item_quantity_text(item, order.language)}"
        f" at {item.unit_price} {currency} = {item.line_total} {currency}"
        for item in order.items.all()
    )
    plain_lines = [
        f"{labels['order_confirmed']}: {order.order_number} – {snapshot.get('shop_name') or order.shop.name}",
        f"{labels['order_date']}: {order_date}",
    ]
    if shop_email:
        plain_lines.append(f"{labels['email'].capitalize()}: {shop_email}")
    if shop_phone:
        plain_lines.append(f"{labels['phone'].capitalize()}: {shop_phone}")
    if whatsapp_group_url:
        plain_lines.append(f"{labels['whatsapp']}: {whatsapp_group_url}")
    plain_lines.extend(
        [
            f"{labels['thank_you']}, {order.customer_name}.",
            "",
            "Items:",
            plain_items,
            f"{labels['delivery_method']}: {delivery_label}",
        ]
    )
    if pickup_date:
        plain_lines.append(f"{labels['pickup_date']}: {pickup_date}")
    if pickup_time:
        plain_lines.append(f"{labels['pickup_time']}: {pickup_time}")
    if lead_hours:
        plain_lines.append(f"{labels['preparation']}: {lead_hours} {labels['hours']}")
    if fulfillment_address:
        address_label = labels["delivery_address"] if order.order_type == "delivery" else labels["pickup_address"]
        plain_lines.append(f"{address_label}: {fulfillment_address}")
    if instructions:
        plain_lines.append(f"{labels['instructions']}: {instructions}")
    plain_lines.append(
        f"{labels['contact']}: {order.customer_phone}{' / ' + order.customer_email if order.customer_email else ''}"
    )
    plain_lines.extend(
        [
            f"{labels['subtotal']}: {order.subtotal} {currency}",
            f"{labels['discount']}: {order.discount_total} {currency}",
            f"{labels['fulfilment_cost']}: {order.delivery_fee} {currency}",
            f"{labels['grand_total']}: {order.total} {currency}",
            f"{labels['status']}: {labels['status_values'].get(order.status, order.status)}",
        ]
    )
    if order.customer_note:
        plain_lines.append(f"{labels['your_note']}: {order.customer_note}")
    plain_message = "\n".join(plain_lines)

    def _send():
        from .billing.invoice_service import create_invoice
        from .billing.pdf_service import invoice_pdf

        invoices = list(order.invoices.all())
        if not invoices and (order.payment_method != "online" or order.payment_status == "paid"):
            invoices = [create_invoice(order)]
        email = EmailMultiAlternatives(
            subject=f"{labels['order_confirmed']} – {order.order_number} – {snapshot.get('shop_name') or order.shop.name}",
            body=plain_message,
            from_email=None,
            to=[order.customer_email],
        )
        email.attach_alternative(html_message, "text/html")
        for invoice in invoices:
            email.attach(f"{invoice.invoice_number}.pdf", invoice_pdf(invoice), "application/pdf")
        email.send(fail_silently=False)

    _send_and_log_order_email(order, OrderEmailLog.EMAIL_TYPE_BUYER_CONFIRMATION, order.customer_email, _send)


def send_seller_notification_email(order):
    """Notify seller of new order."""
    settings = getattr(order.shop, "settings", None)
    seller_email = (settings.notification_email if settings else "") or getattr(order.shop.owner, "email", None)
    if not seller_email:
        return
    snapshot = order.fulfillment_snapshot or {}
    currency = snapshot.get("currency") or getattr(settings, "currency", "EUR")
    order_date = timezone.localtime(order.created_at).strftime("%d %B %Y, %H:%M")
    delivery_label = "🚚 Delivery" if order.order_type == "delivery" else "🏪 Pickup"
    fulfillment_address = order.delivery_address if order.order_type == "delivery" else snapshot.get("shop_address", "")
    instructions = snapshot.get(
        "delivery_instructions" if order.order_type == "delivery" else "pickup_instructions", ""
    )
    pickup_date, pickup_time, lead_hours = _order_pickup_lines(order)
    items = "\n".join(
        f"- {item.product_name}{f' [{item.sku}]' if item.sku else ''}: {order_item_quantity_text(item)}"
        f" at {item.unit_price} {currency} = {item.line_total} {currency}"
        for item in order.items.all()
    )
    message = (
        f"New order {order.order_number} received for {snapshot.get('shop_name') or order.shop.name}!\n\n"
        f"Order date: {order_date}\n"
        f"Customer: {order.customer_name}\n"
        f"Phone: {order.customer_phone}\n"
        f"Email: {order.customer_email or 'not provided'}\n"
        f"Delivery method: {delivery_label}\n"
        f"{'Pickup date: ' + pickup_date + chr(10) if pickup_date else ''}"
        f"{'Pickup time: ' + pickup_time + chr(10) if pickup_time else ''}"
        f"{'Required preparation: ' + str(lead_hours) + ' hours' + chr(10) if lead_hours else ''}"
        f"{'Address: ' + fulfillment_address + chr(10) if fulfillment_address else ''}"
        f"{'Instructions: ' + instructions + chr(10) if instructions else ''}"
        f"{'Customer note: ' + order.customer_note + chr(10) if order.customer_note else ''}"
        f"Items:\n{items}\n"
        f"Subtotal: {order.subtotal} {currency}\n"
        f"Discount: {order.discount_total} {currency}\n"
        f"Delivery fee: {order.delivery_fee} {currency}\n"
        f"Total: {order.total} {currency}\n"
    )

    def _send():
        send_mail(
            subject=f"New order {order.order_number} – {snapshot.get('shop_name') or order.shop.name}",
            message=message,
            from_email=None,
            recipient_list=[seller_email],
            fail_silently=False,
        )

    _send_and_log_order_email(order, OrderEmailLog.EMAIL_TYPE_SELLER_NOTIFICATION, seller_email, _send)


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
    if order.language == "nl":
        decision_text = "goedgekeurd" if approved else "afgewezen"
        subject = f"Je annuleringsverzoek voor bestelling {order.order_number} is {decision_text}"
        heading = f"Annuleringsverzoek {decision_text}"
        greeting = "Hoi"
        request_text = "Je annuleringsverzoek voor bestelling"
        from_text = "van"
        refund_text = "Je ontvangt het totaalbedrag van"
        refund_suffix = "terug volgens het restitutiebeleid van de winkel."
        seller_note_label = "Opmerking van de verkoper"
        contact_text = "Neem rechtstreeks contact op met de winkel als je vragen hebt."
        plain_message = f"Je annuleringsverzoek voor bestelling {order.order_number} is {decision_text}."
    else:
        decision_text = "approved" if approved else "rejected"
        subject = f"Your cancellation request for {order.order_number} was {decision_text}"
        heading = f"Cancellation Request {decision_text.title()}"
        greeting = "Hi"
        request_text = "Your cancellation request for order"
        from_text = "from"
        refund_text = "Your order total of"
        refund_suffix = "will be refunded according to the shop's refund policy."
        seller_note_label = "Seller note"
        contact_text = "If you have questions, please contact the shop directly."
        plain_message = f"Your cancellation request for order {order.order_number} was {decision_text}."
    color = "#28a745" if approved else "#dc3545"
    html_message = f"""
    <h2>{heading}</h2>
    <p>{greeting} <strong>{order.customer_name}</strong>,</p>
    <p>{request_text} <strong>{order.order_number}</strong>
       {from_text} <strong>{order.shop.name}</strong> is
       <span style="color:{color}"><strong>{decision_text}</strong></span>.</p>
    {"<p>" + refund_text + " <strong>" + str(order.total) + " " + currency + "</strong> " + refund_suffix + "</p>" if approved else ""}
    {"<p><strong>" + seller_note_label + ":</strong> " + cancel_request.seller_note + "</p>" if cancel_request.seller_note else ""}
    <p>{contact_text}</p>
    """
    send_mail(
        subject=subject,
        message=plain_message,
        from_email=None,
        recipient_list=[buyer_email],
        html_message=html_message,
        fail_silently=True,
    )


def send_order_cancelled_by_buyer_email_to_seller(order):
    """Notify seller that a buyer cancelled a still-pending order outright
    (no approval needed, since the seller hadn't accepted it yet)."""
    seller_email = getattr(order.shop.owner, "email", None)
    if not seller_email:
        return
    currency = getattr(getattr(order.shop, "settings", None), "currency", "EUR")
    html_message = f"""
    <h2>Order Cancelled by Buyer – {order.order_number}</h2>
    <p>The buyer cancelled order <strong>{order.order_number}</strong> before it was accepted.
       No action is needed from you.</p>
    <table cellpadding="6" style="border-collapse:collapse">
      <tr><td><strong>Order number:</strong></td><td>{order.order_number}</td></tr>
      <tr><td><strong>Order total:</strong></td><td>{order.total} {currency}</td></tr>
      <tr><td><strong>Buyer name:</strong></td><td>{order.customer_name}</td></tr>
    </table>
    """
    send_mail(
        subject=f"Order {order.order_number} was cancelled by the buyer",
        message=f"Order {order.order_number} was cancelled by the buyer before acceptance. No action needed.",
        from_email=None,
        recipient_list=[seller_email],
        html_message=html_message,
        fail_silently=True,
    )


def send_order_cancelled_confirmation_email_to_buyer(order):
    """Confirm to the buyer that their self-serve cancellation went through."""
    buyer_email = order.customer_email
    if not buyer_email:
        return
    currency = getattr(getattr(order.shop, "settings", None), "currency", "EUR")
    if order.language == "nl":
        subject = f"Bestelling {order.order_number} geannuleerd"
        heading = f"Bestelling geannuleerd – {order.order_number}"
        greeting = "Hoi"
        order_text = "je bestelling"
        from_text = "van"
        cancelled = "is geannuleerd zoals je hebt gevraagd."
        total_label = "Totaalbedrag"
        security_note = "Heb je dit niet aangevraagd? Neem dan rechtstreeks contact op met de winkel."
        plain_message = (
            f"Je bestelling {order.order_number} bij {order.shop.name} is geannuleerd zoals je hebt gevraagd."
        )
    else:
        subject = f"Order {order.order_number} cancelled"
        heading = f"Order Cancelled – {order.order_number}"
        greeting = "Hi"
        order_text = "your order"
        from_text = "from"
        cancelled = "has been cancelled as requested."
        total_label = "Order total"
        security_note = "If you didn't request this, please contact the shop directly."
        plain_message = f"Your order {order.order_number} from {order.shop.name} has been cancelled as requested."
    html_message = f"""
    <h2>{heading}</h2>
    <p>{greeting} <strong>{order.customer_name}</strong>, {order_text} <strong>{order.order_number}</strong>
       {from_text} <strong>{order.shop.name}</strong> {cancelled}</p>
    <p>{total_label}: <strong>{order.total} {currency}</strong></p>
    <p>{security_note}</p>
    """
    send_mail(
        subject=subject,
        message=plain_message,
        from_email=None,
        recipient_list=[buyer_email],
        html_message=html_message,
        fail_silently=True,
    )


# Buyer-facing copy shown/emailed for each status a seller can move an order
# to via the seller "status" action (accept/reject/prepare/ready/etc.).
# Cancellation-request approve/reject and buyer self-cancel have their own
# dedicated, more detailed emails (see above) and are NOT routed through this
# generic map, to avoid sending two emails for the same transition.
ORDER_STATUS_UPDATE_SUBJECTS = {
    Order.STATUS_ACCEPTED: "Your order {order_number} was accepted",
    Order.STATUS_REJECTED: "Your order {order_number} was declined",
    Order.STATUS_PREPARING: "Your order {order_number} is being prepared",
    Order.STATUS_READY: "Your order {order_number} is ready",
    Order.STATUS_OUT_FOR_DELIVERY: "Your order {order_number} is out for delivery",
    Order.STATUS_COMPLETED: "Your order {order_number} is complete",
    Order.STATUS_CANCELLED: "Your order {order_number} was cancelled",
}

ORDER_STATUS_UPDATE_SUBJECTS_NL = {
    Order.STATUS_ACCEPTED: "Je bestelling {order_number} is geaccepteerd",
    Order.STATUS_REJECTED: "Je bestelling {order_number} is afgewezen",
    Order.STATUS_PREPARING: "Je bestelling {order_number} wordt bereid",
    Order.STATUS_READY: "Je bestelling {order_number} is klaar",
    Order.STATUS_OUT_FOR_DELIVERY: "Je bestelling {order_number} is onderweg",
    Order.STATUS_COMPLETED: "Je bestelling {order_number} is afgerond",
    Order.STATUS_CANCELLED: "Je bestelling {order_number} is geannuleerd",
}


def send_order_status_update_email_to_buyer(order, previous_status):
    """Notify the buyer whenever a seller modifies an order's status
    (accept/reject/prepare/ready/out-for-delivery/complete/cancel via the
    seller order-status action). Never blocks the request if email fails."""
    buyer_email = order.customer_email
    if not buyer_email:
        return
    is_dutch = order.language == "nl"
    subject_template = (ORDER_STATUS_UPDATE_SUBJECTS_NL if is_dutch else ORDER_STATUS_UPDATE_SUBJECTS).get(order.status)
    if not subject_template:
        return
    subject = subject_template.format(order_number=order.order_number)
    status_labels = {
        Order.STATUS_ACCEPTED: "geaccepteerd",
        Order.STATUS_REJECTED: "afgewezen",
        Order.STATUS_PREPARING: "wordt bereid",
        Order.STATUS_READY: "klaar",
        Order.STATUS_OUT_FOR_DELIVERY: "onderweg",
        Order.STATUS_COMPLETED: "afgerond",
        Order.STATUS_CANCELLED: "geannuleerd",
    }
    status_label = (
        status_labels.get(order.status, order.status.replace("_", " "))
        if is_dutch
        else order.status.replace("_", " ").title()
    )
    previous_label = previous_status.replace("_", " ").title()
    if is_dutch:
        previous_label = {
            Order.STATUS_PENDING: "in afwachting",
            Order.STATUS_ACCEPTED: "geaccepteerd",
            Order.STATUS_REJECTED: "afgewezen",
            Order.STATUS_PREPARING: "in bereiding",
            Order.STATUS_READY: "klaar",
            Order.STATUS_OUT_FOR_DELIVERY: "onderweg",
            Order.STATUS_COMPLETED: "afgerond",
            Order.STATUS_CANCELLED: "geannuleerd",
        }.get(previous_status, previous_label)
        heading = f"Bestellingsupdate – {order.order_number}"
        greeting = "Hoi"
        message = f"Je bestelling {order.order_number} bij {order.shop.name} heeft nu de status: " f"{status_label}."
        previous_text = f"Vorige status: {previous_label}"
    else:
        heading = f"Order Update – {order.order_number}"
        greeting = "Hi"
        message = f"Your order {order.order_number} from {order.shop.name} status changed to " f"{status_label}."
        previous_text = f"Previous status: {previous_label}"
    html_message = f"""
    <h2>{heading}</h2>
    <p>{greeting} <strong>{order.customer_name}</strong>, {message}</p>
    <p>{previous_text}</p>
    """
    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=None,
            recipient_list=[buyer_email],
            html_message=html_message,
            fail_silently=True,
        )
    except Exception:  # noqa: BLE001
        logger.exception("Failed to send order status update email for order %s", order.order_number)


@transaction.atomic
def cancel_pending_order_by_buyer(order):
    """Instantly cancel an order that is still STATUS_PENDING (the seller
    hasn't accepted it yet, so no approval workflow is needed). Restores
    stock for every item and marks the order cancelled. Raises
    serializers.ValidationError if the order is no longer pending (e.g. the
    seller already accepted/rejected it in the meantime)."""
    # Re-fetch with a row lock so a concurrent seller "accept" can't race
    # with this cancellation.
    locked_order = Order.objects.select_for_update().select_related("shop").get(pk=order.pk)
    if locked_order.status != Order.STATUS_PENDING:
        raise serializers.ValidationError(
            {
                "detail": (
                    "This order can no longer be cancelled directly — it has already "
                    "been accepted, rejected, or completed by the seller."
                )
            }
        )
    for item in locked_order.items.select_related("product"):
        if item.product_id:
            Product.objects.filter(pk=item.product_id).update(stock_quantity=F("stock_quantity") + item.quantity)
    locked_order.status = Order.STATUS_CANCELLED
    locked_order.save(update_fields=["status", "updated_at"])
    return locked_order


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
    previous_status = order.status
    order.status = new_status
    order.save(update_fields=["status", "updated_at"])
    try:
        send_order_status_update_email_to_buyer(order, previous_status)
    except Exception:  # noqa: BLE001
        # Never let an email failure roll back or fail the status change itself.
        logger.exception("Failed to dispatch order status update email for order %s", order.order_number)
    return order


# ── Dutch postcode + house number address lookup ──────────────────────────
# Uses PDOK Locatieserver — the Dutch government's free, keyless open-data
# geocoder (https://www.pdok.nl/), so no paid provider or API key is
# required. Checkout must never be blocked by this: any failure/timeout
# simply returns None and the caller falls back to manual address entry.
POSTCODE_RE = re.compile(r"^\d{4}\s?[A-Za-z]{2}$")


def lookup_dutch_address(postcode: str, house_number: str):
    """Look up street/city for a Dutch postcode + house number.

    Returns a dict {"street", "city", "country"} on success, or None if the
    lookup is disabled, the input is invalid, or the provider call fails.
    """
    from django.conf import settings

    provider_url = getattr(settings, "MARKETPLACE_ADDRESS_LOOKUP_PROVIDER_URL", "")
    if not provider_url:
        return None

    postcode = (postcode or "").strip().upper().replace(" ", "")
    house_number = (house_number or "").strip()
    if not POSTCODE_RE.match(postcode) or not house_number:
        return None

    try:
        import requests

        response = requests.get(
            provider_url,
            params={"q": f"{postcode} {house_number}", "fq": "type:adres", "rows": 1},
            timeout=3,
        )
        response.raise_for_status()
        docs = response.json().get("response", {}).get("docs", [])
        if not docs:
            return None
        doc = docs[0]
        street = doc.get("straatnaam")
        city = doc.get("woonplaatsnaam")
        if not street or not city:
            return None
        return {"street": street, "city": city, "country": "Netherlands"}
    except Exception:  # noqa: BLE001 — any provider hiccup must not block checkout
        logger.warning("Address lookup failed for postcode=%s house_number=%s", postcode, house_number)
        return None
