"""Dated pickup menus share the existing order transaction and product snapshots."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.db import transaction
from django.db.models import Count, Sum
from django.utils import timezone

from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from . import ordering
from .models import Order, OrderItem, Product, ScheduledMenu, Shop
from .permissions import IsSeller, IsShopOwner

EXCLUDED_STATUSES = [Order.STATUS_CANCELLED, Order.STATUS_REJECTED]


def reserved_orders(menu):
    return menu.orders.exclude(status__in=EXCLUDED_STATUSES)


def remaining_units(menu):
    used = OrderItem.objects.filter(order__in=reserved_orders(menu)).aggregate(total=Sum("quantity"))["total"] or 0
    return max(0, menu.capacity - used)


def menu_slots(menu, products=(), now=None):
    now = now or ordering.current_time()
    settings = getattr(menu.shop, "settings", None)
    if (
        not menu.active
        or not menu.shop.pickup_available
        or (settings and not settings.accepting_orders)
        or now >= menu.order_deadline
    ):
        return []
    tz = ZoneInfo(menu.pickup_timezone)
    cursor = datetime.combine(menu.pickup_date, menu.pickup_start, tzinfo=tz)
    end = datetime.combine(menu.pickup_date, menu.pickup_end, tzinfo=tz)
    earliest = now + timedelta(minutes=ordering.required_lead_minutes(products))
    occupied = dict(
        reserved_orders(menu)
        .values("pickup_slot_start")
        .annotate(total=Count("id"))
        .values_list("pickup_slot_start", "total")
    )
    step = timedelta(minutes=menu.slot_minutes)
    slots = []
    if remaining_units(menu) <= 0:
        return slots
    while cursor + step <= end:
        if cursor >= earliest and cursor > now and occupied.get(cursor, 0) < menu.slot_capacity:
            slots.append(ordering.PickupSlot(cursor, cursor + step))
        cursor += step
    return slots


def menu_schedule(menu, products, now=None):
    slots = menu_slots(menu, products, now)
    allowed = set(menu.products.values_list("id", flat=True))
    if any(product.id not in allowed for product in products):
        slots = []
    return {
        "scheduling_enabled": True,
        "timezone": menu.pickup_timezone,
        "slot_minutes": menu.slot_minutes,
        "required_lead_time_hours": ordering.lead_time_hours(ordering.required_lead_minutes(products)),
        "earliest_available_pickup": slots[0].start.isoformat() if slots else None,
        "days": (
            [
                {
                    "date": menu.pickup_date.isoformat(),
                    "label": menu.pickup_date.isoformat(),
                    "slots": [slot.as_dict() for slot in slots],
                }
            ]
            if slots
            else []
        ),
    }


def validate_menu_order(shop, payload, order_lines, now):
    """Caller holds the shop row lock, also used by seller menu edits and all shop orders."""
    menu_id = payload.get("scheduled_menu_id")
    if menu_id is None:
        return None, None
    menu = ScheduledMenu.objects.filter(pk=menu_id, shop=shop).first()

    def fail(message):
        raise serializers.ValidationError({"scheduled_menu_id": message, "code": "SCHEDULED_MENU_UNAVAILABLE"})

    if not menu or not menu.active or now >= menu.order_deadline:
        fail("This menu is closed. Please choose an available menu or place a regular order.")
    if payload.get("order_type", "pickup") != "pickup":
        fail("Scheduled menus are pickup only.")
    product_ids = set(menu.products.values_list("id", flat=True))
    if any(product.pk not in product_ids for product, _, _ in order_lines):
        fail("One or more products are not part of this menu.")
    if sum(quantity for _, quantity, _ in order_lines) > remaining_units(menu):
        fail("This menu has insufficient remaining capacity. Please reduce the quantity.")
    requested = payload.get("pickup_slot_start")
    for slot in menu_slots(menu, [product for product, _, _ in order_lines], now):
        if requested == slot.start:
            return menu, slot
    fail("This pickup slot is unavailable. Refresh the pickup times and choose another slot.")


class ScheduledMenuSerializer(serializers.ModelSerializer):
    remaining_capacity = serializers.SerializerMethodField()
    timezone = serializers.CharField(source="pickup_timezone", read_only=True)
    is_open = serializers.SerializerMethodField()

    class Meta:
        model = ScheduledMenu
        fields = [
            "id",
            "title",
            "description",
            "products",
            "pickup_date",
            "pickup_start",
            "pickup_end",
            "order_deadline",
            "slot_minutes",
            "capacity",
            "slot_capacity",
            "active",
            "remaining_capacity",
            "timezone",
            "is_open",
        ]
        read_only_fields = ["id"]
        extra_kwargs = {"products": {"allow_empty": False}, "description": {"max_length": 2000}}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request and getattr(request.user, "is_authenticated", False) and hasattr(request.user, "seller_profile"):
            shop = request.user.seller_profile.shop
            self.fields["products"].child_relation.queryset = Product.objects.filter(shop=shop)
            self.fields["order_deadline"].timezone = (
                ZoneInfo(self.instance.pickup_timezone) if self.instance else ordering.shop_timezone(shop)
            )

    def get_remaining_capacity(self, obj):
        return remaining_units(obj)

    def get_is_open(self, obj):
        return bool(menu_slots(obj))

    def validate(self, attrs):
        shop = self.context["request"].user.seller_profile.shop

        def value(key):
            return attrs.get(key, getattr(self.instance, key, ScheduledMenu._meta.get_field(key).get_default()))

        start, end = value("pickup_start"), value("pickup_end")
        if start >= end:
            raise serializers.ValidationError({"pickup_end": "End time must be after start time on the same day."})
        if (
            datetime.combine(value("pickup_date"), end) - datetime.combine(value("pickup_date"), start)
        ).total_seconds() < value("slot_minutes") * 60:
            raise serializers.ValidationError({"slot_minutes": "At least one complete pickup slot must fit."})
        first_pickup = datetime.combine(
            value("pickup_date"),
            start,
            tzinfo=ZoneInfo(self.instance.pickup_timezone) if self.instance else ordering.shop_timezone(shop),
        )
        if value("order_deadline") >= first_pickup:
            raise serializers.ValidationError({"order_deadline": "The order deadline must be before pickup starts."})
        if value("active") and value("order_deadline") <= timezone.now():
            raise serializers.ValidationError({"order_deadline": "Use a future deadline to publish this menu."})
        products = attrs.get("products")
        if products and any(p.shop_id != shop.pk or not p.is_active or not p.is_approved for p in products):
            raise serializers.ValidationError({"products": "Select active, approved products from your own shop."})
        if self.instance and self.instance.orders.exists():
            for field in ("pickup_date", "pickup_start", "pickup_end", "slot_minutes", "products"):
                if field in attrs:
                    old = (
                        set(self.instance.products.values_list("id", flat=True))
                        if field == "products"
                        else getattr(self.instance, field)
                    )
                    new = {p.pk for p in attrs[field]} if field == "products" else attrs[field]
                    if old != new:
                        raise serializers.ValidationError(
                            {
                                field: "Pickup times and products cannot change after orders have been placed. Create a new menu instead."
                            }
                        )
            used = self.instance.capacity - remaining_units(self.instance)
            if value("capacity") < used:
                raise serializers.ValidationError({"capacity": "Capacity cannot be lower than existing reservations."})
            busiest = (
                reserved_orders(self.instance)
                .values("pickup_slot_start")
                .annotate(total=Count("id"))
                .order_by("-total")
                .first()
            )
            if busiest and value("slot_capacity") < busiest["total"]:
                raise serializers.ValidationError(
                    {"slot_capacity": "A slot already contains more orders than this limit."}
                )
        return attrs


class SellerScheduledMenuViewSet(viewsets.ModelViewSet):
    permission_classes = [IsSeller, IsShopOwner]
    serializer_class = ScheduledMenuSerializer
    pagination_class = None
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        return (
            ScheduledMenu.objects.filter(shop=self.request.user.seller_profile.shop)
            .select_related("shop", "shop__settings")
            .prefetch_related("products")
        )

    def perform_create(self, serializer):
        shop = self.request.user.seller_profile.shop
        serializer.save(shop=shop, pickup_timezone=str(ordering.shop_timezone(shop)))

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        Shop.objects.select_for_update().get(pk=request.user.seller_profile.shop.pk)
        return super().create(request, *args, **kwargs)

    @transaction.atomic
    def partial_update(self, request, *args, **kwargs):
        Shop.objects.select_for_update().get(pk=request.user.seller_profile.shop.pk)
        return super().partial_update(request, *args, **kwargs)

    @action(detail=True, methods=["get"])
    def preparation(self, request, pk=None):
        menu = self.get_object()
        orders = reserved_orders(menu).order_by("pickup_slot_start", "order_number").prefetch_related("items")
        confirmed = orders.exclude(status=Order.STATUS_PENDING)

        def quantities(queryset):
            return list(
                OrderItem.objects.filter(order__in=queryset)
                .values("product_name", "sku", "selling_unit", "units_per_pack", "weight_value", "weight_unit")
                .annotate(
                    quantity=Sum("quantity"),
                    physical_quantity=Sum("physical_quantity"),
                    total_weight_value=Sum("total_weight_value"),
                )
                .order_by("product_name", "sku")
            )

        return Response(
            {
                "menu": self.get_serializer(menu).data,
                "confirmed_quantities": quantities(confirmed),
                "pending_quantities": quantities(orders.filter(status=Order.STATUS_PENDING)),
                "pickups": [
                    {
                        "order_number": o.order_number,
                        "customer_name": o.customer_name,
                        "pickup_slot_start": o.pickup_slot_start,
                        "pickup_slot_end": o.pickup_slot_end,
                        "status": o.status,
                        "payment_status": o.payment_status,
                        "items": [
                            {"product_name": i.product_name, "quantity": i.quantity, "sku": i.sku}
                            for i in o.items.all()
                        ],
                    }
                    for o in orders
                ],
            }
        )
