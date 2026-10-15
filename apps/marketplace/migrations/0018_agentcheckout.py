import uuid

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("marketplace", "0017_seller_order_availability_and_auto_approval")]

    operations = [
        migrations.CreateModel(
            name="AgentCheckout",
            fields=[
                ("token", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("payload", models.JSONField(default=dict)),
                ("quote", models.JSONField(default=dict)),
                ("expires_at", models.DateTimeField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("order", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to="marketplace.order")),
                ("shop", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="marketplace.shop")),
            ],
        ),
    ]
