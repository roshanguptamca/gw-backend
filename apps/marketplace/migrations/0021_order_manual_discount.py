from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("marketplace", "0020_shop_google_place_id")]

    operations = [
        migrations.AddField(
            model_name="order",
            name="manual_discount_title",
            field=models.CharField(max_length=120, blank=True),
        ),
        migrations.AddField(
            model_name="order",
            name="manual_discount_amount",
            field=models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0")),
        ),
    ]
