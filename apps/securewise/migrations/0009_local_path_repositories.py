from django.core.validators import URLValidator
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("securewise", "0008_scan_policy_templates"),
    ]

    operations = [
        migrations.AddField(
            model_name="securewiserepository",
            name="local_path",
            field=models.CharField(
                blank=True,
                help_text="Server-local repository path used when access_mode='local_path'.",
                max_length=1000,
            ),
        ),
        migrations.AlterField(
            model_name="securewiserepository",
            name="access_mode",
            field=models.CharField(
                choices=[
                    ("public", "Public"),
                    ("integration", "Integration"),
                    ("local_path", "Local Path"),
                ],
                default="public",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="securewiserepository",
            name="repository_url",
            field=models.CharField(blank=True, max_length=500, validators=[URLValidator()]),
        ),
    ]
