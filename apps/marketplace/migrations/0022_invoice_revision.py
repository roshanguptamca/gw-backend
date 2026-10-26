from decimal import Decimal

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("marketplace", "0021_order_manual_discount")]

    operations = [
        migrations.CreateModel(
            name="InvoiceRevision",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("content", models.BinaryField()),
                ("total", models.DecimalField(decimal_places=2, max_digits=12)),
                ("discount_title", models.CharField(blank=True, max_length=120)),
                ("discount_total", models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=12)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "invoice",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="revisions",
                        to="marketplace.invoice",
                    ),
                ),
            ],
        ),
    ]
