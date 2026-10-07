from django.db import migrations


def seed_billing(apps, schema_editor):
    Shop = apps.get_model("marketplace", "Shop")
    ShopSettings = apps.get_model("marketplace", "ShopSettings")
    for shop in Shop.objects.using(schema_editor.connection.alias).all().iterator():
        settings, _ = ShopSettings.objects.using(schema_editor.connection.alias).get_or_create(shop=shop)
        defaults = {
            "legal_business_name": shop.name,
            "billing_address_line1": shop.address,
            "billing_postcode": shop.postal_code,
            "billing_city": shop.city,
            "billing_country": shop.country,
        }
        if shop.slug == "rishi-kitchen" or shop.name.strip().lower() == "rishi kitchen":
            defaults.update(vat_number="1111111111", invoice_prefix="RK", invoice_iban="ABNAXXXXXXXXX")
        changed = []
        for field, value in defaults.items():
            if not getattr(settings, field) and value:
                setattr(settings, field, value)
                changed.append(field)
        if changed:
            settings.save(update_fields=changed)


class Migration(migrations.Migration):
    dependencies = [("marketplace", "0014_order_billing_snapshot_orderitem_vat_rate_and_more")]
    operations = [migrations.RunPython(seed_billing, migrations.RunPython.noop)]
