from django.db import migrations

# Example seller configuration, matched by stable SKU within the shop. Products
# are never created here; missing SKUs are skipped. Weights are taken from each
# product's existing catalogue value (weight_grams), never guessed.
SHOP_PRODUCT_CONFIGURATION = {
    "rishi-kitchen": {
        "RK-IDLI-2": {
            "selling_unit": "PACK",
            "units_per_pack": 2,
            "minimum_physical_units": 10,
            "minimum_order_amount": "20.00",
            "preparation_time_minutes": 48 * 60,
        },
        "RK-SAM-2": {
            "selling_unit": "PACK",
            "units_per_pack": 2,
            "minimum_physical_units": 10,
            "minimum_order_amount": "20.00",
            "preparation_time_minutes": 24 * 60,
        },
        "RK-VP-2": {"selling_unit": "PACK", "units_per_pack": 2},
        "RK-MG-2": {"selling_unit": "PACK", "units_per_pack": 2},
        "RK-NP-500": {"selling_unit": "WEIGHT"},
        "RK-MN-250": {"selling_unit": "WEIGHT"},
        "RK-MN-500": {"selling_unit": "WEIGHT"},
        "RK-GJ-500": {"selling_unit": "WEIGHT"},
        "RK-GR-250": {"selling_unit": "WEIGHT"},
        "RK-GR-500": {"selling_unit": "WEIGHT"},
        "RK-GM-250": {"selling_unit": "WEIGHT"},
        "RK-GM-500": {"selling_unit": "WEIGHT"},
    }
}


def forwards(apps, schema_editor):
    Product = apps.get_model("marketplace", "Product")

    # Generic: carry the legacy gram weight into the new weight fields (selling unit unchanged).
    for product in Product.objects.filter(weight_grams__isnull=False, weight_value__isnull=True):
        product.weight_value = product.weight_grams
        product.weight_unit = "GRAM"
        product.save(update_fields=["weight_value", "weight_unit"])

    for shop_slug, products in SHOP_PRODUCT_CONFIGURATION.items():
        for product in Product.objects.filter(shop__slug=shop_slug, sku__in=list(products)):
            config = dict(products[product.sku])
            if config.get("selling_unit") == "WEIGHT" and product.weight_value is None:
                # No catalogue weight available: leave the product unchanged.
                continue
            for field, value in config.items():
                setattr(product, field, value)
            product.save(update_fields=list(config))


class Migration(migrations.Migration):
    dependencies = [
        ("marketplace", "0012_product_selling_format_rules_and_pickup_slots"),
    ]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
