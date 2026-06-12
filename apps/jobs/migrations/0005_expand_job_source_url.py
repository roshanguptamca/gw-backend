from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("jobs", "0004_atsreport_anonymous_identity_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="jobdescription",
            name="source_url",
            field=models.URLField(blank=True, max_length=2048),
        ),
        migrations.AlterField(
            model_name="temporaryjobdescription",
            name="source_url",
            field=models.URLField(blank=True, max_length=2048),
        ),
    ]
