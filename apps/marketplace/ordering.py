"""Generic, data-driven selling-format, ordering-rule and pickup-slot logic.

Everything here is driven by Product / ShopSettings / Shop configuration so the
same code serves every marketplace seller. Functions accept either a Product
or an OrderItem snapshot (both expose ``selling_unit``, ``units_per_pack``,
``weight_value`` and ``weight_unit``).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.utils import timezone

from rest_framework.exceptions import APIException

DEFAULT_PICKUP_TIMEZONE = "Europe/Amsterdam"
DEFAULT_PICKUP_SLOT_MINUTES = 30
DEFAULT_PICKUP_BOOKING_WINDOW_DAYS = 14

UNIT_LABELS: dict[str, tuple[str, str]] = {
    "PIECE": ("piece", "pieces"),
    "PACK": ("pack", "packs"),
    "PLATE": ("plate", "plates"),
    "BOX": ("box", "boxes"),
    "TRAY": ("tray", "trays"),
    "BOTTLE": ("bottle", "bottles"),
}
# (base unit, factor to base, symbol)
MEASURE_UNITS: dict[str, tuple[str, Decimal, str]] = {
    "GRAM": ("GRAM", Decimal("1"), "g"),
    "KILOGRAM": ("GRAM", Decimal("1000"), "kg"),
    "MILLILITRE": ("MILLILITRE", Decimal("1"), "ml"),
    "LITRE": ("MILLILITRE", Decimal("1000"), "L"),
}
LARGE_UNIT_SYMBOL: dict[str, str] = {"GRAM": "kg", "MILLILITRE": "L"}
PIECE = "PIECE"
PACK = "PACK"
WEIGHT = "WEIGHT"


def current_time() -> datetime:
    """Server time; isolated so tests can freeze it."""
    now: datetime = timezone.now()
    return now


# ---------------------------------------------------------------------------
# Selling format / quantities
# ---------------------------------------------------------------------------


def selling_unit_of(obj) -> str:
    return str(getattr(obj, "selling_unit", "") or PIECE)


def pieces_per_unit(obj) -> int:
    if selling_unit_of(obj) == WEIGHT:
        return 1
    return getattr(obj, "units_per_pack", None) or 1


def physical_quantity(obj, quantity: int) -> int:
    return int(quantity) * pieces_per_unit(obj)


def total_weight(obj, quantity: int) -> Decimal | None:
    weight_value = getattr(obj, "weight_value", None)
    if weight_value is None or not getattr(obj, "weight_unit", ""):
        return None
    return Decimal(weight_value) * int(quantity)


def _trim_decimal(value: Decimal) -> str:
    text = f"{Decimal(value).quantize(Decimal('0.001')):f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def format_measure(value: Decimal | None, unit: str) -> str:
    """Format a weight/volume, normalising to kg / L at 1000 g / ml or more."""
    if value is None or unit not in MEASURE_UNITS:
        return ""
    base_unit, factor, symbol = MEASURE_UNITS[unit]
    base_value = Decimal(value) * factor
    if base_value >= 1000:
        return f"{_trim_decimal(base_value / 1000)} {LARGE_UNIT_SYMBOL[base_unit]}"
    return f"{_trim_decimal(base_value)} {MEASURE_UNITS[base_unit][2]}"


def pluralize_unit(count: int, selling_unit: str) -> str:
    singular, plural = UNIT_LABELS.get(selling_unit, UNIT_LABELS[PIECE])
    return f"{count} {singular if count == 1 else plural}"


def describe_selling_format(obj) -> str:
    """Short label for one selling unit, e.g. '2 pieces', '250 g', '1 plate'."""
    unit = selling_unit_of(obj)
    if unit == WEIGHT:
        return format_measure(getattr(obj, "weight_value", None), getattr(obj, "weight_unit", ""))
    per_unit = pieces_per_unit(obj)
    if unit in (PIECE, PACK) and per_unit > 1:
        return pluralize_unit(per_unit, PIECE)
    if per_unit > 1:
        return f"1 {UNIT_LABELS[unit][0]} ({pluralize_unit(per_unit, PIECE)})"
    return f"1 {UNIT_LABELS.get(unit, UNIT_LABELS[PIECE])[0]}"


def describe_quantity(obj, quantity: int) -> str:
    """Human description of a cart line, e.g. '5 packs × 2 pieces (10 pieces)' or '2 × 250 g (500 g)'."""
    quantity = int(quantity)
    unit = selling_unit_of(obj)
    if unit == WEIGHT:
        weight_unit = getattr(obj, "weight_unit", "")
        each = format_measure(getattr(obj, "weight_value", None), weight_unit)
        total = format_measure(total_weight(obj, quantity), weight_unit)
        return f"{quantity} × {each} ({total})" if each else str(quantity)
    per_unit = pieces_per_unit(obj)
    if per_unit > 1:
        label_unit = PACK if unit == PIECE else unit
        return (
            f"{pluralize_unit(quantity, label_unit)} × {pluralize_unit(per_unit, PIECE)} "
            f"({pluralize_unit(quantity * per_unit, PIECE)})"
        )
    return pluralize_unit(quantity, unit)


# ---------------------------------------------------------------------------
# Ordering rules
# ---------------------------------------------------------------------------


def lead_time_hours(minutes: int | None) -> int | float:
    minutes = int(minutes or 0)
    return minutes // 60 if minutes % 60 == 0 else round(minutes / 60, 2)


def effective_minimum_quantity(product) -> int:
    """Smallest cart quantity that satisfies every configured product minimum."""
    minimum = product.minimum_order_quantity or 1
    if product.minimum_physical_units:
        minimum = max(minimum, math.ceil(product.minimum_physical_units / pieces_per_unit(product)))
    if product.minimum_order_amount and product.price and product.price > 0:
        minimum = max(minimum, math.ceil(Decimal(product.minimum_order_amount) / Decimal(product.price)))
    return minimum


def ordering_rules(product) -> dict:
    return {
        "minimum_order_quantity": product.minimum_order_quantity,
        "minimum_physical_units": product.minimum_physical_units,
        "minimum_order_amount": (
            str(product.minimum_order_amount) if product.minimum_order_amount is not None else None
        ),
        "order_lead_time_minutes": product.preparation_time_minutes or 0,
        "order_lead_time_hours": lead_time_hours(product.preparation_time_minutes),
        "effective_minimum_quantity": effective_minimum_quantity(product),
    }


def product_rule_violations(product, quantity: int, line_total: Decimal) -> list[dict]:
    errors = []
    base = {"product_id": product.id, "product_name": product.name}
    if product.minimum_order_quantity and quantity < product.minimum_order_quantity:
        errors.append(
            {
                "code": "PRODUCT_MINIMUM_QUANTITY_NOT_MET",
                "message": f"{product.name} requires a minimum of {product.minimum_order_quantity}.",
                **base,
                "minimum_order_quantity": product.minimum_order_quantity,
                "current_quantity": quantity,
            }
        )
    if product.minimum_physical_units:
        current_units = physical_quantity(product, quantity)
        if current_units < product.minimum_physical_units:
            errors.append(
                {
                    "code": "PRODUCT_MINIMUM_UNITS_NOT_MET",
                    "message": (
                        f"{product.name} requires at least " f"{pluralize_unit(product.minimum_physical_units, PIECE)}."
                    ),
                    **base,
                    "minimum_physical_units": product.minimum_physical_units,
                    "current_physical_units": current_units,
                    "minimum_quantity": math.ceil(product.minimum_physical_units / pieces_per_unit(product)),
                }
            )
    if product.minimum_order_amount is not None and line_total < product.minimum_order_amount:
        errors.append(
            {
                "code": "PRODUCT_MINIMUM_AMOUNT_NOT_MET",
                "message": f"{product.name} requires a minimum order of {product.minimum_order_amount}.",
                **base,
                "minimum_amount": str(product.minimum_order_amount),
                "current_amount": str(line_total.quantize(Decimal("0.01"))),
            }
        )
    return errors


class OrderRuleViolation(APIException):
    """Structured 400 error. Top-level keys mirror the first violation; all are under ``errors``."""

    status_code = 400
    default_code = "ORDER_RULES_NOT_MET"

    def __init__(self, errors: list[dict]):
        self.detail = {**errors[0], "errors": errors}


# ---------------------------------------------------------------------------
# Pickup scheduling
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PickupSlot:
    start: datetime
    end: datetime

    def as_dict(self) -> dict:
        return {
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "date": self.start.date().isoformat(),
            "label": f"{self.start:%H:%M}–{self.end:%H:%M}",
        }


def shop_timezone(shop) -> ZoneInfo:
    name = getattr(getattr(shop, "settings", None), "pickup_timezone", "") or DEFAULT_PICKUP_TIMEZONE
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo(DEFAULT_PICKUP_TIMEZONE)


def _parse_time(value) -> time | None:
    if not isinstance(value, str):
        return None
    try:
        return time.fromisoformat(value.strip()[:5])
    except ValueError:
        return None


def pickup_windows(shop) -> dict[int, list[tuple[time, time]]]:
    """Open windows keyed by Python weekday (Monday=0) from Shop.opening_hours.

    opening_hours entries use ``day_of_week`` with 0=Sunday (the seller portal format).
    """
    windows: dict[int, list[tuple[time, time]]] = {}
    for entry in shop.opening_hours or []:
        if not isinstance(entry, dict):
            continue
        day = entry.get("day_of_week", entry.get("dayOfWeek"))
        if entry.get("is_closed", entry.get("isClosed")) or not isinstance(day, int) or not 0 <= day <= 6:
            continue
        opens = _parse_time(entry.get("open_time", entry.get("openTime")))
        closes = _parse_time(entry.get("close_time", entry.get("closeTime")))
        if opens and closes and opens < closes:
            windows.setdefault((day + 6) % 7, []).append((opens, closes))
    for day_windows in windows.values():
        day_windows.sort()
    return windows


def has_pickup_schedule(shop) -> bool:
    return bool(pickup_windows(shop))


def required_lead_minutes(products) -> int:
    return max((product.preparation_time_minutes or 0 for product in products), default=0)


def _slot_minutes(shop) -> int:
    value = getattr(getattr(shop, "settings", None), "pickup_slot_minutes", None)
    return value if value and value > 0 else DEFAULT_PICKUP_SLOT_MINUTES


def _window_days(shop) -> int:
    value = getattr(getattr(shop, "settings", None), "pickup_booking_window_days", None)
    return value if value and value > 0 else DEFAULT_PICKUP_BOOKING_WINDOW_DAYS


def generate_pickup_slots(shop, lead_minutes: int, now: datetime | None = None) -> list[PickupSlot]:
    """All selectable slots that start at or after ``now + lead`` within the booking window."""
    windows = pickup_windows(shop)
    if not windows:
        return []
    tz = shop_timezone(shop)
    now = now or current_time()
    earliest = now + timedelta(minutes=lead_minutes or 0)
    step = timedelta(minutes=_slot_minutes(shop))
    first_day: date = earliest.astimezone(tz).date()
    slots: list[PickupSlot] = []
    for offset in range(_window_days(shop) + 1):
        day = first_day + timedelta(days=offset)
        for opens, closes in windows.get(day.weekday(), []):
            cursor = datetime.combine(day, opens, tzinfo=tz)
            window_end = datetime.combine(day, closes, tzinfo=tz)
            while cursor + step <= window_end:
                if cursor >= earliest:
                    slots.append(PickupSlot(cursor, cursor + step))
                cursor += step
    return slots


def pickup_schedule_payload(shop, products, now: datetime | None = None) -> dict:
    lead = required_lead_minutes(products)
    tz = shop_timezone(shop)
    slots = generate_pickup_slots(shop, lead, now)
    days: dict[str, dict] = {}
    for slot in slots:
        key = slot.start.date().isoformat()
        day = days.setdefault(key, {"date": key, "label": format_pickup_date(slot.start), "slots": []})
        day["slots"].append(slot.as_dict())
    return {
        "scheduling_enabled": has_pickup_schedule(shop),
        "timezone": str(tz),
        "slot_minutes": _slot_minutes(shop),
        "required_lead_time_minutes": lead,
        "required_lead_time_hours": lead_time_hours(lead),
        "earliest_available_pickup": slots[0].start.isoformat() if slots else None,
        "days": list(days.values()),
    }


def format_pickup_date(value: datetime) -> str:
    return f"{value:%A} {value.day} {value:%B %Y}"


def validate_pickup_slot(shop, lead_minutes: int, requested_start: datetime | None, now: datetime | None = None):
    """Return the matching PickupSlot (or None when the shop has no pickup schedule)."""
    if not has_pickup_schedule(shop):
        return None
    now = now or current_time()
    slots = generate_pickup_slots(shop, lead_minutes, now)
    earliest = slots[0].start.isoformat() if slots else None
    if requested_start is None:
        raise OrderRuleViolation(
            [
                {
                    "code": "PICKUP_SLOT_REQUIRED",
                    "message": "Please choose a pickup date and time.",
                    "shop_id": shop.id,
                    "shop_name": shop.name,
                    "required_lead_time_hours": lead_time_hours(lead_minutes),
                    "earliest_available_pickup": earliest,
                }
            ]
        )
    if timezone.is_naive(requested_start):
        requested_start = requested_start.replace(tzinfo=shop_timezone(shop))
    if requested_start < now + timedelta(minutes=lead_minutes or 0):
        raise OrderRuleViolation(
            [
                {
                    "code": "PICKUP_TIME_TOO_EARLY",
                    "message": "The selected pickup time does not allow enough preparation time.",
                    "shop_id": shop.id,
                    "shop_name": shop.name,
                    "required_lead_time_hours": lead_time_hours(lead_minutes),
                    "earliest_available_pickup": earliest,
                }
            ]
        )
    for slot in slots:
        if slot.start == requested_start:
            return slot
    raise OrderRuleViolation(
        [
            {
                "code": "PICKUP_SLOT_INVALID",
                "message": "The selected pickup time is not available for this shop.",
                "shop_id": shop.id,
                "shop_name": shop.name,
                "required_lead_time_hours": lead_time_hours(lead_minutes),
                "earliest_available_pickup": earliest,
            }
        ]
    )
