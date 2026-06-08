"""
Data migration: seeds all Dutch driving theory topics, lessons, sections,
questions and options. Runs automatically with `python manage.py migrate`.
Idempotent — safe to run on a DB that already has data (uses get_or_create).
"""

from django.db import migrations


def seed_data(apps, schema_editor):
    from django.core.management import call_command
    call_command("seed_driving_theory", verbosity=0)


def unseed_data(apps, schema_editor):
    # Rolling back will clear all driving theory data
    DrivingTopic = apps.get_model("driving_theory", "DrivingTopic")
    DrivingTopic.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("driving_theory", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_data, reverse_code=unseed_data),
    ]
