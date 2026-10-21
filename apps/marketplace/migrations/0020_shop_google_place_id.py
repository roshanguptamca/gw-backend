from django.core.validators import RegexValidator
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("marketplace", "0019_shop_google_review_url")]
    operations = [
        migrations.AddField(
            model_name="shop",
            name="google_place_id",
            field=models.CharField(
                blank=True,
                max_length=255,
                validators=[RegexValidator(r"^[A-Za-z0-9_-]+$", "Enter a Google Place ID, not a URL.")],
            ),
        )
    ]
