"""Live menu/quotes and explicitly confirmed guest pickup checkout for AI tools."""

from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone

from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from . import ordering
from .models import AgentCheckout, Product, Shop
from .serializers import OrderCreateSerializer
from .services import create_order_from_payload


def active_shop(slug):
    return get_object_or_404(
        Shop.objects.select_related("settings"),
        slug=slug,
        is_active=True,
        is_approved=True,
    )


def eligible_products(shop):
    return Product.objects.filter(
        shop=shop,
        is_active=True,
        is_approved=True,
    ).order_by("name")


class AgentMenuView(APIView):
    """Public, live catalogue for an ElevenLabs server/webhook tool."""

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "marketplace_order"

    def get(self, request, slug):
        shop = active_shop(slug)
        search = request.query_params.get("search", "").strip()[:100]
        products = eligible_products(shop)
        if search:
            products = products.filter(Q(name__icontains=search) | Q(description__icontains=search))
        items = [
            {
                "product_id": product.id,
                "name": product.name,
                "description": product.description,
                "ingredients": product.ingredients,
                "allergens": product.allergens,
                "price_eur": str(product.price),
                "selling_format": ordering.describe_selling_format(product),
                "stock_quantity": product.stock_quantity,
                "available": product.stock_quantity > 0,
                "ordering_rules": ordering.ordering_rules(product),
            }
            for product in products[:100]
        ]
        return Response(
            {
                "shop": {"name": shop.name, "slug": shop.slug, "city": shop.city},
                "accepting_orders": shop.settings.accepting_orders,
                "pickup_available": shop.pickup_available,
                "currency": "EUR",
                "items": items,
                "checkout_url": f"https://marketplace.guidewisey.com/shop/{shop.slug}",
                "notice": "Prices and availability must be rechecked at checkout. Do not promise an order until checkout confirms it.",
            }
        )


class QuoteItemSerializer(serializers.Serializer):
    product_id = serializers.IntegerField(min_value=1)
    quantity = serializers.IntegerField(min_value=1, max_value=1000)


class QuoteRequestSerializer(serializers.Serializer):
    items = QuoteItemSerializer(many=True, allow_empty=False)


class AgentQuoteView(APIView):
    """Non-binding precheckout quote. Does not reserve stock or place an order."""

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "marketplace_order"

    def post(self, request, slug):
        serializer = QuoteRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        shop = active_shop(slug)
        requested = serializer.validated_data["items"]
        return Response(build_quote(shop, requested))


def build_quote(shop, requested):
    if len(requested) > 30:
        raise serializers.ValidationError({"detail": "Too many order lines."})
    if len({line["product_id"] for line in requested}) != len(requested):
        raise serializers.ValidationError({"detail": "Duplicate product IDs are not allowed."})
    products = {p.id: p for p in eligible_products(shop).filter(id__in=[item["product_id"] for item in requested])}
    errors = []
    subtotal = Decimal("0.00")
    lines = []
    for requested_item in requested:
        product_id = requested_item["product_id"]
        quantity = requested_item["quantity"]
        product = products.get(product_id)
        if product is None:
            errors.append({"product_id": product_id, "code": "NOT_AVAILABLE"})
            continue
        line_total = product.price * quantity
        if quantity > product.stock_quantity:
            errors.append({"product_id": product_id, "code": "INSUFFICIENT_STOCK"})
        errors.extend(ordering.product_rule_violations(product, quantity, line_total))
        subtotal += line_total
        lines.append(
            {
                "product_id": product_id,
                "name": product.name,
                "quantity": quantity,
                "unit_price_eur": str(product.price),
                "line_total_eur": str(line_total),
                "selling_format": ordering.describe_selling_format(product),
            }
        )
    if not shop.settings.accepting_orders:
        errors.append({"code": "SHOP_NOT_ACCEPTING_ORDERS"})
    if not shop.pickup_available:
        errors.append({"code": "PICKUP_UNAVAILABLE"})
    minimum = shop.settings.min_order_amount
    if subtotal < minimum:
        errors.append({"code": "SHOP_MINIMUM_NOT_MET", "minimum_eur": str(minimum)})
    pickup = (
        ordering.pickup_schedule_payload(shop, [products[line["product_id"]] for line in lines]) if not errors else None
    )
    return {
        "valid_for_checkout": not errors,
        "errors": errors,
        "items": lines,
        "subtotal_eur": str(subtotal),
        "currency": "EUR",
        "pickup": pickup,
        "checkout_url": f"https://marketplace.guidewisey.com/shop/{shop.slug}",
        "notice": "Estimate only; no stock reserved. The normal checkout calculates final total, fees, discounts and confirms the order.",
    }


class GuestCheckoutSerializer(serializers.Serializer):
    items = QuoteItemSerializer(many=True, allow_empty=False, max_length=30)
    customer_name = serializers.CharField(max_length=150)
    customer_phone = serializers.CharField(max_length=30)
    customer_email = serializers.EmailField(required=False, allow_blank=True, default="")
    customer_note = serializers.CharField(required=False, allow_blank=True, max_length=2000, default="")
    pickup_slot_start = serializers.DateTimeField(required=False, allow_null=True, default=None)
    language = serializers.ChoiceField(choices=["en", "nl", "hi"], default="en")
    payment_method = serializers.ChoiceField(choices=["cash"], default="cash")
    order_type = serializers.ChoiceField(choices=["pickup"], default="pickup")

    validate_customer_phone = OrderCreateSerializer.validate_customer_phone

    def validate(self, attrs):
        unknown = set(self.initial_data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError({field: "Unsupported checkout field." for field in sorted(unknown)})
        return attrs


class GuestConfirmSerializer(serializers.Serializer):
    confirmation_token = serializers.UUIDField()
    confirmed = serializers.BooleanField()
    terms_accepted = serializers.BooleanField()

    def validate(self, attrs):
        if attrs["confirmed"] is not True or attrs["terms_accepted"] is not True:
            raise serializers.ValidationError(
                "Explicit order confirmation and acceptance of marketplace policies required."
            )
        if set(self.initial_data) - set(self.fields):
            raise serializers.ValidationError(
                "Order details cannot be changed during confirmation. Prepare a new checkout."
            )
        return attrs


class GuestCheckoutView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "marketplace_order"

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if not getattr(settings, "MARKETPLACE_AI_GUEST_CHECKOUT_ENABLED", False):
            from rest_framework.exceptions import NotFound

            raise NotFound("Agent guest checkout is not enabled.")
        allowed_shops = getattr(settings, "MARKETPLACE_AI_GUEST_CHECKOUT_SHOPS", ["rishi-kitchen"])
        if kwargs.get("slug") not in allowed_shops:
            from rest_framework.exceptions import NotFound

            raise NotFound("Agent guest checkout is not enabled for this shop.")

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        return response


class AgentPrepareCheckoutView(GuestCheckoutView):
    """Validate and return a review; never creates an order or reserves inventory."""

    def post(self, request, slug):
        serializer = GuestCheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        shop = active_shop(slug)
        payload = dict(serializer.data)  # JSON-safe datetime representation for the review snapshot.
        quote = build_quote(shop, serializer.validated_data["items"])
        if not quote["valid_for_checkout"]:
            return Response(quote, status=status.HTTP_400_BAD_REQUEST)
        products = eligible_products(shop).filter(id__in=[item["product_id"] for item in payload["items"]])
        slot = ordering.validate_pickup_slot(
            shop, ordering.required_lead_minutes(products), serializer.validated_data["pickup_slot_start"]
        )
        quote["pickup_slot_start"] = slot.start.isoformat() if slot else None
        quote["pickup_slot_end"] = slot.end.isoformat() if slot else None
        payload["pickup_slot_start"] = quote["pickup_slot_start"]
        quote["shop_name"] = shop.name
        quote["pickup_address"] = (
            ", ".join(
                value
                for value in (
                    shop.settings.pickup_address_line_1,
                    shop.settings.pickup_address_line_2,
                    shop.settings.pickup_postal_code,
                    shop.settings.pickup_city,
                    shop.settings.pickup_country,
                )
                if value
            )
            or shop.address
        )
        quote["pickup_instructions"] = shop.settings.pickup_instructions
        quote["total_eur"] = quote["subtotal_eur"]  # Pickup, cash, no coupons or delivery fees.
        quote["payment_method"] = "cash"
        quote["payment_due"] = "at_pickup"
        quote["terms_url"] = "https://www.guidewisey.com/#terms"
        quote["privacy_url"] = "https://www.guidewisey.com/#privacy"
        quote["customer"] = {key: payload[key] for key in ("customer_name", "customer_phone", "customer_email")}
        quote["customer_note"] = payload["customer_note"]
        quote["notice"] = (
            "Review only; no order placed or stock reserved. Read back all items, total, customer details, pickup "
            "and cash payment at pickup. Share marketplace terms and privacy links. Ask the customer to explicitly "
            "confirm the order and accept the policies before calling confirm_order. Never infer consent."
        )
        checkout = AgentCheckout.objects.create(
            shop=shop, payload=payload, quote=quote, expires_at=timezone.now() + timedelta(minutes=15)
        )
        return Response(
            {"confirmation_token": str(checkout.token), "expires_at": checkout.expires_at.isoformat(), "review": quote},
            status=status.HTTP_201_CREATED,
        )


def order_receipt(order, replayed):
    return {
        "order_number": order.order_number,
        "status": order.status,
        "total_eur": str(order.total),
        "currency": "EUR",
        "payment_method": order.payment_method,
        "payment_status": order.payment_status,
        "pickup_slot_start": order.pickup_slot_start.isoformat() if order.pickup_slot_start else None,
        "pickup_slot_end": order.pickup_slot_end.isoformat() if order.pickup_slot_end else None,
        "replayed": replayed,
        "notice": "Order placed. Payment is due at pickup. Report the returned status; pending is awaiting seller acceptance.",
    }


class AgentConfirmOrderView(GuestCheckoutView):
    """Consume one reviewed checkout exactly once, revalidating live prices and rules."""

    @transaction.atomic
    def post(self, request, slug):
        serializer = GuestConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # Serialize confirmations per shop on PostgreSQL. SQLite has no row
        # locks; its development-only concurrency limitations are documented.
        shop = get_object_or_404(Shop.objects.select_for_update(), slug=slug, is_active=True, is_approved=True)
        checkout = get_object_or_404(
            AgentCheckout.objects.select_for_update(), token=serializer.validated_data["confirmation_token"], shop=shop
        )
        if checkout.order_id:
            return Response(order_receipt(checkout.order, replayed=True))
        if checkout.expires_at <= timezone.now():
            return Response({"code": "CHECKOUT_EXPIRED", "detail": "Prepare and confirm a new checkout."}, status=410)
        payload_serializer = GuestCheckoutSerializer(data=checkout.payload)
        payload_serializer.is_valid(raise_exception=True)
        payload = payload_serializer.validated_data
        # Hold product locks through comparison and creation so a concurrent price
        # edit cannot change the amount after the customer reviewed it.
        list(
            eligible_products(shop).select_for_update().filter(id__in=[item["product_id"] for item in payload["items"]])
        )
        current_quote = build_quote(shop, payload["items"])
        if not current_quote["valid_for_checkout"]:
            return Response(current_quote, status=status.HTTP_400_BAD_REQUEST)
        if current_quote["items"] != checkout.quote["items"]:
            return Response(
                {
                    "code": "QUOTE_CHANGED",
                    "detail": "Prices or products changed. Prepare a new review and confirm again.",
                },
                status=status.HTTP_409_CONFLICT,
            )
        # The ordinary checkout service validates stock, shop/product rules and pickup
        # again under its row locks, creates invoices, and schedules notifications on commit.
        payload.update(shop_id=shop.pk, terms_accepted=True, create_account=False)
        if payload["language"] == "hi":
            payload["language"] = "en"  # Existing receipts support English/Dutch; conversation can remain Hindi.
        order = create_order_from_payload(payload, user=None, defer_notifications=True)
        checkout.order = order
        checkout.payload = {}  # Do not retain duplicate customer details after checkout.
        checkout.quote = {}
        checkout.save(update_fields=["order", "payload", "quote"])
        return Response(order_receipt(order, replayed=False), status=status.HTTP_201_CREATED)
