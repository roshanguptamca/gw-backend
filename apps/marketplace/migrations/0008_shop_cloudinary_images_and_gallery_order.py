from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("marketplace", "0007_cloudinary_product_images"),
    ]

    operations = [
        migrations.AddField(
            model_name="shop",
            name="banner_public_id",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="shop",
            name="banner_url",
            field=models.URLField(blank=True, max_length=500),
        ),
        migrations.AddField(
            model_name="shop",
            name="logo_public_id",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="shop",
            name="logo_url",
            field=models.URLField(blank=True, max_length=500),
        ),
        migrations.AlterModelOptions(
            name="productimage",
            options={"ordering": ["sort_order", "id"]},
        ),
    ]
