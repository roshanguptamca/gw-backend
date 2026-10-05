"""Product selling formats, ordering rules, pickup scheduling, snapshots and emails."""

from datetime import datetime
from decimal import Decimal
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import SimpleTestCase, TestCase

from rest_framework.test import APIClient

from apps.marketplace import ordering
from apps.marketplace.models import MeasureUnit, Order, OrderItem, Product, SellingUnit, Shop
from apps.marketplace.services import create_seller_with_shop

from .test_api import _SyncThread

User = get_user_model()
AMS = ZoneInfo("Europe/Amsterdam")
# Thursday 1 October 2026, 14:00 in Amsterdam.
NOW = datetime(2026, 10, 1, 14, 0, tzinfo=AMS)
# Friday 10:00-12:00, Saturday 12:00-18:00; everything else closed (0=Sunday).
PICKUP_HOURS = [
    {"day_of_week": 0, "is_closed": True},
    {"day_of_week": 5, "is_closed": False, "open_time": "10:00", "close_time": "12:00"},
    {"day_of_week": 6, "is_closed": False, "open_time": "12:00", "close_time": "18:00"},
]


def make_product(**fields):
    defaults = {"id": 1, "name": "Item", "price": Decimal("5.00"), "preparation_time_minutes": 0}
    defaults.update(fields)
    return Product(**defaults)


def make_shop(opening_hours=None, **settings):
    from apps.marketplace.models import ShopSettings

    shop = Shop(id=1, name="Shop", slug="shop", opening_hours=opening_hours or [])
    shop.settings = ShopSettings(shop=shop, **settings)
    return shop


class SellingFormatTests(SimpleTestCase):
    def test_label_tables_cover_model_choices(self):
        self.assertEqual(set(ordering.UNIT_LABELS) | {ordering.WEIGHT}, set(SellingUnit.values))
        self.assertEqual(set(ordering.MEASURE_UNITS), set(MeasureUnit.values))

    def test_every_selling_unit_describes_quantity(self):
        cases = {
            SellingUnit.PIECE: "3 pieces",
            SellingUnit.PACK: "3 packs",
            SellingUnit.PLATE: "3 plates",
            SellingUnit.BOX: "3 boxes",
            SellingUnit.TRAY: "3 trays",
            SellingUnit.BOTTLE: "3 bottles",
        }
        for unit, expected in cases.items():
            with self.subTest(unit=unit):
                self.assertEqual(ordering.describe_quantity(make_product(selling_unit=unit), 3), expected)
        weight = make_product(selling_unit=SellingUnit.WEIGHT, weight_value=Decimal("250"), weight_unit="GRAM")
        self.assertEqual(ordering.describe_quantity(weight, 3), "3 × 250 g (750 g)")

    def test_single_unit_labels(self):
        self.assertEqual(ordering.describe_selling_format(make_product()), "1 piece")
        self.assertEqual(
            ordering.describe_selling_format(make_product(selling_unit=SellingUnit.PACK, units_per_pack=2)),
            "2 pieces",
        )
        self.assertEqual(
            ordering.describe_selling_format(make_product(selling_unit=SellingUnit.BOX, units_per_pack=6)),
            "1 box (6 pieces)",
        )
        self.assertEqual(ordering.describe_selling_format(make_product(selling_unit=SellingUnit.TRAY)), "1 tray")

    def test_pack_quantities_are_physical_pieces(self):
        samosa = make_product(selling_unit=SellingUnit.PACK, units_per_pack=2)
        self.assertEqual(ordering.physical_quantity(samosa, 5), 10)
        self.assertEqual(ordering.describe_quantity(samosa, 5), "5 packs × 2 pieces (10 pieces)")
        box = make_product(selling_unit=SellingUnit.BOX, units_per_pack=6)
        self.assertEqual(ordering.describe_quantity(box, 2), "2 boxes × 6 pieces (12 pieces)")

    def test_minimum_physical_units_rounds_required_packs_up(self):
        self.assertEqual(
            ordering.effective_minimum_quantity(
                make_product(selling_unit=SellingUnit.PACK, units_per_pack=2, minimum_physical_units=10)
            ),
            5,
        )
        self.assertEqual(
            ordering.effective_minimum_quantity(
                make_product(selling_unit=SellingUnit.PACK, units_per_pack=4, minimum_physical_units=10)
            ),
            3,
        )
        self.assertEqual(
            ordering.effective_minimum_quantity(make_product(minimum_order_amount=Decimal("12.00"))),
            3,
        )
        self.assertEqual(ordering.effective_minimum_quantity(make_product()), 1)

    def test_weight_totals_and_normalisation(self):
        namak = make_product(selling_unit=SellingUnit.WEIGHT, weight_value=Decimal("250"), weight_unit="GRAM")
        self.assertEqual(ordering.total_weight(namak, 2), Decimal("500"))
        self.assertEqual(ordering.describe_quantity(namak, 2), "2 × 250 g (500 g)")
        big = make_product(selling_unit=SellingUnit.WEIGHT, weight_value=Decimal("500"), weight_unit="GRAM")
        self.assertEqual(ordering.describe_quantity(big, 2), "2 × 500 g (1 kg)")
        decimal_kg = make_product(selling_unit=SellingUnit.WEIGHT, weight_value=Decimal("0.75"), weight_unit="KILOGRAM")
        self.assertEqual(ordering.describe_quantity(decimal_kg, 3), "3 × 750 g (2.25 kg)")
        juice = make_product(selling_unit=SellingUnit.WEIGHT, weight_value=Decimal("330"), weight_unit="MILLILITRE")
        self.assertEqual(ordering.describe_quantity(juice, 4), "4 × 330 ml (1.32 L)")
        self.assertEqual(ordering.format_measure(Decimal("1.5"), MeasureUnit.LITRE), "1.5 L")

    def test_lead_time_hours(self):
        self.assertEqual(ordering.lead_time_hours(48 * 60), 48)
        self.assertEqual(ordering.lead_time_hours(90), 1.5)
        self.assertEqual(ordering.lead_time_hours(None), 0)


class ProductRuleTests(SimpleTestCase):
    def codes(self, product, quantity):
        line_total = product.price * quantity
        return [error["code"] for error in ordering.product_rule_violations(product, quantity, line_total)]

    def test_no_restrictions(self):
        self.assertEqual(self.codes(make_product(), 1), [])

    def test_minimum_quantity(self):
        product = make_product(minimum_order_quantity=2)
        self.assertEqual(self.codes(product, 1), ["PRODUCT_MINIMUM_QUANTITY_NOT_MET"])
        self.assertEqual(self.codes(product, 2), [])

    def test_minimum_physical_units(self):
        samosa = make_product(selling_unit=SellingUnit.PACK, units_per_pack=2, minimum_physical_units=10)
        errors = ordering.product_rule_violations(samosa, 3, Decimal("15.00"))
        self.assertEqual(errors[0]["code"], "PRODUCT_MINIMUM_UNITS_NOT_MET")
        self.assertEqual(errors[0]["minimum_physical_units"], 10)
        self.assertEqual(errors[0]["current_physical_units"], 6)
        self.assertEqual(errors[0]["minimum_quantity"], 5)
        self.assertEqual(self.codes(samosa, 5), [])

    def test_minimum_amount(self):
        idli = make_product(minimum_order_amount=Decimal("20.00"))
        errors = ordering.product_rule_violations(idli, 3, Decimal("15.00"))
        self.assertEqual(
            errors[0],
            {
                "code": "PRODUCT_MINIMUM_AMOUNT_NOT_MET",
                "message": "Item requires a minimum order of 20.00.",
                "product_id": 1,
                "product_name": "Item",
                "minimum_amount": "20.00",
                "current_amount": "15.00",
            },
        )
        self.assertEqual(self.codes(idli, 4), [])

    def test_ordering_rules_payload(self):
        idli = make_product(
            selling_unit=SellingUnit.PACK,
            units_per_pack=2,
            minimum_physical_units=10,
            minimum_order_amount=Decimal("20.00"),
            preparation_time_minutes=48 * 60,
        )
        self.assertEqual(
            ordering.ordering_rules(idli),
            {
                "minimum_order_quantity": None,
                "minimum_physical_units": 10,
                "minimum_order_amount": "20.00",
                "order_lead_time_minutes": 2880,
                "order_lead_time_hours": 48,
                "effective_minimum_quantity": 5,
            },
        )


class PickupSlotTests(SimpleTestCase):
    def test_longest_lead_time_wins(self):
        products = [
            make_product(preparation_time_minutes=24 * 60),
            make_product(preparation_time_minutes=48 * 60),
            make_product(preparation_time_minutes=12 * 60),
        ]
        self.assertEqual(ordering.required_lead_minutes(products), 48 * 60)
        self.assertEqual(ordering.required_lead_minutes([]), 0)

    def test_48_hour_lead_starts_saturday_afternoon(self):
        shop = make_shop(PICKUP_HOURS, pickup_slot_minutes=30, pickup_timezone="Europe/Amsterdam")
        slots = ordering.generate_pickup_slots(shop, 48 * 60, NOW)
        self.assertEqual(slots[0].start, datetime(2026, 10, 3, 14, 0, tzinfo=AMS))
        self.assertEqual(slots[0].as_dict()["label"], "14:00–14:30")
        self.assertEqual(slots[1].start, datetime(2026, 10, 3, 14, 30, tzinfo=AMS))

    def test_24_hour_lead_respects_seller_schedule(self):
        shop = make_shop(PICKUP_HOURS)
        slots = ordering.generate_pickup_slots(shop, 24 * 60, NOW)
        # Friday 14:00 is after Friday's 10:00-12:00 window, so Saturday opening is first.
        self.assertEqual(slots[0].start, datetime(2026, 10, 3, 12, 0, tzinfo=AMS))
        self.assertTrue(all(slot.start.weekday() in (4, 5) for slot in slots))

    def test_slot_duration_is_configurable(self):
        shop = make_shop(PICKUP_HOURS, pickup_slot_minutes=60)
        slots = ordering.generate_pickup_slots(shop, 0, NOW)
        friday = [slot for slot in slots if slot.start.date().isoformat() == "2026-10-02"]
        self.assertEqual([slot.as_dict()["label"] for slot in friday], ["10:00–11:00", "11:00–12:00"])

    def test_booking_window_limits_days(self):
        shop = make_shop(PICKUP_HOURS, pickup_booking_window_days=2)
        slots = ordering.generate_pickup_slots(shop, 0, NOW)
        self.assertEqual({slot.start.date().isoformat() for slot in slots}, {"2026-10-02", "2026-10-03"})

    def test_exact_boundary_is_accepted_and_earlier_rejected(self):
        shop = make_shop(PICKUP_HOURS)
        slot = ordering.validate_pickup_slot(shop, 48 * 60, datetime(2026, 10, 3, 14, 0, tzinfo=AMS), NOW)
        self.assertEqual(slot.start, datetime(2026, 10, 3, 14, 0, tzinfo=AMS))
        with self.assertRaises(ordering.OrderRuleViolation) as raised:
            ordering.validate_pickup_slot(shop, 48 * 60, datetime(2026, 10, 3, 13, 30, tzinfo=AMS), NOW)
        self.assertEqual(raised.exception.detail["code"], "PICKUP_TIME_TOO_EARLY")
        self.assertEqual(raised.exception.detail["required_lead_time_hours"], 48)
        self.assertEqual(raised.exception.detail["earliest_available_pickup"], "2026-10-03T14:00:00+02:00")

    def test_slot_outside_schedule_or_missing_is_rejected(self):
        shop = make_shop(PICKUP_HOURS)
        with self.assertRaises(ordering.OrderRuleViolation) as raised:
            ordering.validate_pickup_slot(shop, 0, datetime(2026, 10, 3, 14, 10, tzinfo=AMS), NOW)
        self.assertEqual(raised.exception.detail["code"], "PICKUP_SLOT_INVALID")
        with self.assertRaises(ordering.OrderRuleViolation) as raised:
            ordering.validate_pickup_slot(shop, 0, None, NOW)
        self.assertEqual(raised.exception.detail["code"], "PICKUP_SLOT_REQUIRED")

    def test_shop_without_schedule_needs_no_slot(self):
        self.assertIsNone(ordering.validate_pickup_slot(make_shop([]), 48 * 60, None, NOW))
        self.assertEqual(ordering.generate_pickup_slots(make_shop([]), 0, NOW), [])

    def test_timezone_handling(self):
        utc_shop = make_shop(PICKUP_HOURS, pickup_timezone="UTC")
        first = ordering.generate_pickup_slots(utc_shop, 48 * 60, NOW)[0]
        # NOW is 12:00 UTC, so +48h is Saturday 12:00 UTC (opening time) in a UTC shop.
        self.assertEqual(first.start.isoformat(), "2026-10-03T12:00:00+00:00")
        # Daylight saving ends on 25 October; later slots carry the winter offset.
        shop = make_shop(PICKUP_HOURS, pickup_booking_window_days=40)
        later = [s for s in ordering.generate_pickup_slots(shop, 0, NOW) if s.start.date().isoformat() == "2026-10-31"]
        self.assertEqual(later[0].as_dict()["start"], "2026-10-31T12:00:00+01:00")

    def test_invalid_timezone_falls_back_to_default(self):
        self.assertEqual(str(ordering.shop_timezone(make_shop([], pickup_timezone="Not/AZone"))), "Europe/Amsterdam")


@patch("apps.marketplace.ordering.current_time", return_value=NOW)
class OrderRulesAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_superuser(username="admin@x.test", email="admin@x.test", password="x")
        self.seller, _, self.shop = create_seller_with_shop(
            email="kitchen@x.test",
            password="pass12345!",
            first_name="K",
            last_name="One",
            business_name="Kitchen One",
            created_by=self.admin,
        )
        self.other_seller, _, self.other_shop = create_seller_with_shop(
            email="bakery@x.test",
            password="pass12345!",
            first_name="B",
            last_name="Two",
            business_name="Bakery Two",
            created_by=self.admin,
        )
        for shop in (self.shop, self.other_shop):
            shop.is_approved = True
            shop.opening_hours = PICKUP_HOURS
            shop.save()
        self.shop.settings.pickup_address_line_1 = "Example Street 1"
        self.shop.settings.pickup_city = "Zoetermeer"
        self.shop.settings.save()
        self.samosa = Product.objects.create(
            shop=self.shop,
            name="Samosa",
            slug="samosa",
            sku="KO-SAM-2",
            price=Decimal("5.00"),
            stock_quantity=100,
            is_approved=True,
            selling_unit=SellingUnit.PACK,
            units_per_pack=2,
            minimum_physical_units=10,
            minimum_order_amount=Decimal("20.00"),
            preparation_time_minutes=24 * 60,
        )
        self.idli = Product.objects.create(
            shop=self.shop,
            name="Idli",
            slug="idli",
            sku="KO-IDLI-2",
            price=Decimal("5.00"),
            stock_quantity=100,
            is_approved=True,
            selling_unit=SellingUnit.PACK,
            units_per_pack=2,
            minimum_physical_units=10,
            preparation_time_minutes=48 * 60,
        )
        self.namak = Product.objects.create(
            shop=self.shop,
            name="Namak Pare",
            slug="namak-pare",
            sku="KO-NP-250",
            price=Decimal("5.00"),
            stock_quantity=100,
            is_approved=True,
            selling_unit=SellingUnit.WEIGHT,
            weight_value=Decimal("250"),
            weight_unit=MeasureUnit.GRAM,
            preparation_time_minutes=12 * 60,
        )
        self.bread = Product.objects.create(
            shop=self.other_shop,
            name="Bread",
            slug="bread",
            price=Decimal("4.00"),
            stock_quantity=100,
            is_approved=True,
            preparation_time_minutes=12 * 60,
        )

    def order(self, shop, items, **extra):
        payload = {
            "shop_id": shop.id,
            "customer_name": "Asha Buyer",
            "customer_email": "buyer@x.test",
            "customer_phone": "+31600000001",
            "order_type": "pickup",
            "terms_accepted": True,
            "items": [{"product_id": product.id, "quantity": quantity} for product, quantity in items],
            **extra,
        }
        with patch("apps.marketplace.services.threading.Thread", _SyncThread):
            return self.client.post("/api/marketplace/orders/", payload, format="json")

    def test_product_api_exposes_selling_format_and_rules(self, _now):
        response = self.client.get(f"/api/marketplace/products/{self.samosa.id}/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["selling_unit"], "PACK")
        self.assertEqual(data["units_per_pack"], 2)
        self.assertEqual(data["selling_format_label"], "2 pieces")
        self.assertEqual(data["order_lead_time_hours"], 24)
        self.assertEqual(data["ordering_rules"]["minimum_physical_units"], 10)
        self.assertEqual(data["ordering_rules"]["minimum_order_amount"], "20.00")
        self.assertEqual(data["ordering_rules"]["effective_minimum_quantity"], 5)
        weight = self.client.get(f"/api/marketplace/products/{self.namak.id}/").json()
        self.assertEqual((weight["weight_value"], weight["weight_unit"]), ("250.000", "GRAM"))
        self.assertEqual(weight["weight_grams"], 250)
        self.assertEqual(weight["selling_format_label"], "250 g")

    def test_legacy_products_default_to_piece_without_rules(self, _now):
        self.assertEqual(self.bread.selling_unit, SellingUnit.PIECE)
        response = self.order(self.other_shop, [(self.bread, 1)], pickup_slot_start="2026-10-02T10:00:00+02:00")
        self.assertEqual(response.status_code, 201, response.content)
        item = OrderItem.objects.get(order_id=response.json()["id"])
        self.assertEqual((item.physical_quantity, item.selling_unit), (1, "PIECE"))

    def test_seller_product_validation(self, _now):
        self.client.force_authenticate(self.seller)
        missing_pack = self.client.post(
            "/api/seller/products/", {"name": "Pakora", "price": "5.00", "selling_unit": "PACK"}, format="json"
        )
        self.assertEqual(missing_pack.status_code, 400)
        self.assertIn("units_per_pack", missing_pack.json())
        missing_weight = self.client.post(
            "/api/seller/products/", {"name": "Chivda", "price": "5.00", "selling_unit": "WEIGHT"}, format="json"
        )
        self.assertEqual(missing_weight.status_code, 400)
        self.assertIn("weight_value", missing_weight.json())
        created = self.client.post(
            "/api/seller/products/",
            {
                "name": "Chivda",
                "price": "8.00",
                "selling_unit": "WEIGHT",
                "weight_value": "0.5",
                "weight_unit": "KILOGRAM",
                "minimum_order_quantity": 2,
                "preparation_time_minutes": 2 * 24 * 60,
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.content)
        self.assertEqual(created.json()["weight_grams"], 500)
        self.assertEqual(created.json()["order_lead_time_hours"], 48)
        self.assertEqual(created.json()["selling_format_label"], "500 g")

    def test_minimum_physical_units_not_met(self, _now):
        response = self.order(self.shop, [(self.samosa, 3)], pickup_slot_start="2026-10-03T12:00:00+02:00")
        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertEqual(body["code"], "PRODUCT_MINIMUM_UNITS_NOT_MET")
        self.assertEqual(body["product_id"], self.samosa.id)
        self.assertEqual(body["minimum_physical_units"], 10)
        self.assertEqual(body["current_physical_units"], 6)
        self.assertIn("PRODUCT_MINIMUM_AMOUNT_NOT_MET", [error["code"] for error in body["errors"]])
        self.assertFalse(Order.objects.exists())

    def test_product_minimum_amount_not_met(self, _now):
        self.samosa.minimum_physical_units = None
        self.samosa.save()
        response = self.order(self.shop, [(self.samosa, 3)], pickup_slot_start="2026-10-03T12:00:00+02:00")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "PRODUCT_MINIMUM_AMOUNT_NOT_MET")
        self.assertEqual(response.json()["minimum_amount"], "20.00")
        self.assertEqual(response.json()["current_amount"], "15.00")

    def test_product_and_shop_minimum_must_both_pass(self, _now):
        self.shop.settings.min_order_amount = Decimal("60.00")
        self.shop.settings.save()
        response = self.order(self.shop, [(self.samosa, 5)], pickup_slot_start="2026-10-03T12:00:00+02:00")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "SHOP_MINIMUM_ORDER_NOT_MET")
        ok = self.order(self.shop, [(self.samosa, 5), (self.idli, 7)], pickup_slot_start="2026-10-03T14:00:00+02:00")
        self.assertEqual(ok.status_code, 201, ok.content)

    def test_pickup_slot_required_and_lead_time_enforced(self, _now):
        missing = self.order(self.shop, [(self.idli, 5)])
        self.assertEqual(missing.json()["code"], "PICKUP_SLOT_REQUIRED")
        too_early = self.order(
            self.shop, [(self.idli, 5), (self.samosa, 5)], pickup_slot_start="2026-10-03T12:00:00+02:00"
        )
        self.assertEqual(too_early.status_code, 400)
        self.assertEqual(too_early.json()["code"], "PICKUP_TIME_TOO_EARLY")
        self.assertEqual(too_early.json()["required_lead_time_hours"], 48)
        self.assertEqual(too_early.json()["earliest_available_pickup"], "2026-10-03T14:00:00+02:00")
        invalid = self.order(self.shop, [(self.idli, 5)], pickup_slot_start="2026-10-04T14:00:00+02:00")
        self.assertEqual(invalid.json()["code"], "PICKUP_SLOT_INVALID")

    def test_delivery_orders_do_not_need_a_pickup_slot(self, _now):
        self.shop.delivery_available = True
        self.shop.save()
        response = self.order(self.shop, [(self.idli, 5)], order_type="delivery", delivery_address="Street 2, City")
        self.assertEqual(response.status_code, 201, response.content)
        self.assertIsNone(Order.objects.get().pickup_slot_start)
        self.assertEqual(Order.objects.get().fulfillment_snapshot["required_lead_time_hours"], 48)

    def test_pickup_slots_endpoint_per_shop(self, _now):
        response = self.client.get(
            f"/api/marketplace/shops/{self.shop.slug}/pickup-slots/",
            {"product_ids": f"{self.samosa.id},{self.idli.id},{self.namak.id},{self.bread.id}"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["required_lead_time_hours"], 48)
        self.assertEqual(data["earliest_available_pickup"], "2026-10-03T14:00:00+02:00")
        self.assertEqual(data["days"][0]["label"], "Saturday 3 October 2026")
        self.assertEqual(data["days"][0]["slots"][0]["label"], "14:00–14:30")
        other = self.client.get(
            f"/api/marketplace/shops/{self.other_shop.slug}/pickup-slots/",
            {"product_ids": f"{self.bread.id},{self.idli.id}"},
        ).json()
        # Another seller's product never affects this shop's lead time.
        self.assertEqual(other["required_lead_time_hours"], 12)
        self.assertEqual(other["earliest_available_pickup"], "2026-10-02T10:00:00+02:00")

    def test_multi_shop_orders_keep_separate_rules_and_pickup(self, _now):
        first = self.order(self.shop, [(self.idli, 5)], pickup_slot_start="2026-10-03T16:00:00+02:00")
        second = self.order(self.other_shop, [(self.bread, 1)], pickup_slot_start="2026-10-02T10:30:00+02:00")
        self.assertEqual(first.status_code, 201, first.content)
        self.assertEqual(second.status_code, 201, second.content)
        self.assertEqual(first.json()["fulfillment_snapshot"]["pickup_time"], "16:00–16:30")
        self.assertEqual(second.json()["fulfillment_snapshot"]["pickup_time"], "10:30–11:00")
        self.assertEqual(second.json()["fulfillment_snapshot"]["required_lead_time_hours"], 12)
        cross_shop = self.order(self.other_shop, [(self.idli, 5)], pickup_slot_start="2026-10-03T16:00:00+02:00")
        self.assertEqual(cross_shop.status_code, 400)

    def test_order_snapshot_survives_catalogue_changes(self, _now):
        response = self.order(
            self.shop, [(self.samosa, 5), (self.namak, 2)], pickup_slot_start="2026-10-03T12:30:00+02:00"
        )
        self.assertEqual(response.status_code, 201, response.content)
        order = Order.objects.get()
        self.assertEqual(order.pickup_slot_start, datetime(2026, 10, 3, 12, 30, tzinfo=AMS))
        snapshot = order.fulfillment_snapshot
        self.assertEqual(snapshot["pickup_date"], "Saturday 3 October 2026")
        self.assertEqual(snapshot["required_lead_time_hours"], 24)
        self.assertEqual(snapshot["minimum_order_amount"], "0.00")
        self.assertIn("Example Street 1", snapshot["shop_address"])

        self.samosa.units_per_pack = 4
        self.samosa.price = Decimal("9.00")
        self.samosa.minimum_physical_units = 20
        self.samosa.save()
        samosa_line = order.items.get(product=self.samosa)
        self.assertEqual(samosa_line.sku, "KO-SAM-2")
        self.assertEqual(samosa_line.unit_price, Decimal("5.00"))
        self.assertEqual((samosa_line.selling_unit, samosa_line.units_per_pack), ("PACK", 2))
        self.assertEqual(samosa_line.physical_quantity, 10)
        self.assertEqual(samosa_line.ordering_rules_snapshot["minimum_physical_units"], 10)
        self.assertEqual(samosa_line.ordering_rules_snapshot["order_lead_time_hours"], 24)
        namak_line = order.items.get(product=self.namak)
        self.assertEqual(namak_line.total_weight_value, Decimal("500"))
        item_data = {item["product_name"]: item for item in response.json()["items"]}
        self.assertEqual(item_data["Samosa"]["quantity_description"], "5 packs × 2 pieces (10 pieces)")
        self.assertEqual(item_data["Namak Pare"]["quantity_description"], "2 × 250 g (500 g)")

    def test_legacy_order_items_still_serialize(self, _now):
        order = Order.objects.create(
            shop=self.shop,
            order_number="GWLEGACY1",
            customer_name="Old",
            customer_phone="1",
            subtotal=Decimal("5"),
            total=Decimal("5"),
        )
        OrderItem.objects.create(
            order=order, product_name="Old item", unit_price=Decimal("5"), quantity=1, line_total=Decimal("5")
        )
        self.client.force_authenticate(self.seller)
        response = self.client.get(f"/api/seller/orders/{order.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"][0]["quantity_description"], "1")

    def test_buyer_and_seller_emails_include_quantities_and_pickup(self, _now):
        self.shop.settings.whatsapp_group_url = "https://chat.whatsapp.com/AbC123"
        self.shop.settings.notification_email = "orders@kitchen.test"
        self.shop.settings.save()
        mail.outbox = []
        response = self.order(
            self.shop,
            [(self.samosa, 5), (self.idli, 5), (self.namak, 2)],
            pickup_slot_start="2026-10-03T16:00:00+02:00",
            customer_note="No chilli",
        )
        self.assertEqual(response.status_code, 201, response.content)
        buyer = next(message for message in mail.outbox if "buyer@x.test" in message.to)
        seller = next(message for message in mail.outbox if "orders@kitchen.test" in message.to)
        self.assertEqual(len(mail.outbox), 2)
        for body in (buyer.body, buyer.alternatives[0][0]):
            self.assertIn("5 packs × 2 pieces (10 pieces)", body)
            self.assertIn("2 × 250 g (500 g)", body)
            self.assertIn("Saturday 3 October 2026", body)
            self.assertIn("16:00–16:30", body)
            self.assertIn("Example Street 1", body)
            self.assertIn("KO-SAM-2", body)
        self.assertIn("https://chat.whatsapp.com/AbC123", buyer.body)
        for expected in (
            "Asha Buyer",
            "+31600000001",
            "buyer@x.test",
            "Samosa [KO-SAM-2]: 5 packs × 2 pieces (10 pieces) at 5.00 EUR = 25.00 EUR",
            "Namak Pare [KO-NP-250]: 2 × 250 g (500 g)",
            "Pickup date: Saturday 3 October 2026",
            "Pickup time: 16:00–16:30",
            "Required preparation: 48 hours",
            "No chilli",
        ):
            self.assertIn(expected, seller.body)
        self.assertNotIn("Bread", seller.body)


class ConfigureSellingFormatsMigrationTests(TestCase):
    def test_configures_existing_products_by_sku_without_duplicates(self):
        from importlib import import_module

        migration = import_module("apps.marketplace.migrations.0013_configure_product_selling_formats")
        admin = User.objects.create_superuser(username="a@x.test", email="a@x.test", password="x")
        _, _, shop = create_seller_with_shop(
            email="rk@x.test",
            password="pass12345!",
            first_name="R",
            last_name="K",
            business_name="Example Kitchen",
            created_by=admin,
        )
        shop.slug = "rishi-kitchen"
        shop.save()
        idli = Product.objects.create(shop=shop, name="Idli", slug="idli", sku="RK-IDLI-2", price=Decimal("5"))
        weighted = Product.objects.create(
            shop=shop, name="Gulab Jamun", slug="gj", sku="RK-GJ-500", price=Decimal("10"), weight_grams=500
        )
        unknown_weight = Product.objects.create(shop=shop, name="Gujia", slug="gr", sku="RK-GR-250", price=Decimal("5"))
        other_shop_product = Product.objects.create(
            shop=create_seller_with_shop(
                email="o@x.test",
                password="pass12345!",
                first_name="O",
                last_name="S",
                business_name="Other",
                created_by=admin,
            )[2],
            name="Thing",
            slug="thing",
            price=Decimal("3"),
            weight_grams=200,
        )
        count = Product.objects.count()
        migration.forwards(django_apps, None)
        self.assertEqual(Product.objects.count(), count)
        idli.refresh_from_db()
        self.assertEqual((idli.selling_unit, idli.units_per_pack, idli.minimum_physical_units), ("PACK", 2, 10))
        self.assertEqual((idli.minimum_order_amount, idli.preparation_time_minutes), (Decimal("20.00"), 2880))
        weighted.refresh_from_db()
        self.assertEqual((weighted.selling_unit, weighted.weight_value, weighted.weight_unit), ("WEIGHT", 500, "GRAM"))
        unknown_weight.refresh_from_db()
        self.assertEqual((unknown_weight.selling_unit, unknown_weight.weight_value), ("PIECE", None))
        other_shop_product.refresh_from_db()
        self.assertEqual(other_shop_product.selling_unit, "PIECE")
        self.assertEqual((other_shop_product.weight_value, other_shop_product.weight_unit), (200, "GRAM"))
