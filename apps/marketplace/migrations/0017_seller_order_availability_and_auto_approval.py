from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("marketplace", "0016_order_language_product_translations_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="shopsettings",
            name="accepting_orders",
            field=models.BooleanField(default=True),
        ),
        migrations.AlterField(
            model_name="product",
            name="is_approved",
            field=models.BooleanField(default=True),
        ),
    ]
