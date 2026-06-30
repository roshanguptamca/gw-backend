from django.db import migrations, models


def prepare_skus_for_unique_constraint(apps, schema_editor):
    Product = apps.get_model("marketplace", "Product")
    Product.objects.filter(sku="").update(sku=None)
    seen = set()
    for product in Product.objects.exclude(sku__isnull=True).order_by("id").only("id", "sku"):
        if product.sku not in seen:
            seen.add(product.sku)
            continue
        candidate = f"GW-{product.id}"
        counter = 1
        while candidate in seen:
            counter += 1
            candidate = f"GW-{product.id}-{counter}"
        product.sku = candidate
        product.save(update_fields=["sku"])
        seen.add(candidate)


class Migration(migrations.Migration):

    dependencies = [
        ("marketplace", "0006_product_external_image_url"),
    ]

    operations = [
        migrations.RunPython(prepare_skus_for_unique_constraint, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="product",
            name="sku",
            field=models.CharField(blank=True, max_length=80, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="product",
            name="image_public_id",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="product",
            name="image_url",
            field=models.URLField(blank=True, max_length=500),
        ),
        migrations.AlterField(
            model_name="productimage",
            name="image",
            field=models.ImageField(blank=True, null=True, upload_to="products/gallery/"),
        ),
        migrations.AddField(
            model_name="productimage",
            name="image_public_id",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="productimage",
            name="image_url",
            field=models.URLField(blank=True, max_length=500),
        ),
    ]
