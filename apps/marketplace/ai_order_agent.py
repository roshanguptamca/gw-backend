"""Read-only public tool endpoints for Rishi Kitchen's conversational order assistant.

These endpoints deliberately do not create orders or expose customer information.
Checkout remains a human-confirmed action through the existing marketplace flow.
"""

from decimal import Decimal

from django.db.models import Q
from django.shortcuts import get_object_or_404

from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from . import ordering
from .models import Product, Shop


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
        if len(requested) > 30:
            return Response({"detail": "Too many order lines."}, status=status.HTTP_400_BAD_REQUEST)
        if len({line["product_id"] for line in requested}) != len(requested):
            return Response({"detail": "Duplicate product IDs are not allowed."}, status=status.HTTP_400_BAD_REQUEST)
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
            ordering.pickup_schedule_payload(shop, [products[line["product_id"]] for line in lines])
            if not errors
            else None
        )
        return Response(
            {
                "valid_for_checkout": not errors,
                "errors": errors,
                "items": lines,
                "subtotal_eur": str(subtotal),
                "currency": "EUR",
                "pickup": pickup,
                "checkout_url": f"https://marketplace.guidewisey.com/shop/{shop.slug}",
                "notice": "Estimate only; no stock reserved. The normal checkout calculates final total, fees, discounts and confirms the order.",
            }
        )
