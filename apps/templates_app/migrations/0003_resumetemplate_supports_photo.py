from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("templates_app", "0002_seed_classic_template")]

    operations = [
        migrations.AddField(
            model_name="resumetemplate",
            name="supports_photo",
            field=models.BooleanField(default=True),
        ),
    ]
