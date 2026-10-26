from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("marketplace", "0022_invoice_revision")]

    operations = [
        migrations.AlterField(
            model_name="orderemaillog",
            name="email_type",
            field=models.CharField(
                choices=[
                    ("buyer_confirmation", "Buyer confirmation"),
                    ("seller_notification", "Seller notification"),
                    ("invoice_resend", "Invoice resend"),
                ],
                max_length=30,
            ),
        ),
    ]
