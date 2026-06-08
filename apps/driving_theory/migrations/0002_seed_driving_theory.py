"""
Data migration: seeds all Dutch driving theory topics, lessons, sections,
questions and options. Runs automatically with `python manage.py migrate`.
Idempotent — safe to run on a DB that already has data (uses get_or_create).

NOTE: This migration skips seeding if the v3 schema fields are not yet present
(e.g. on a fresh test DB run). Migration 0008_reseed_all_topics runs the full
seed after all schema migrations are applied.
"""

from django.db import migrations


def seed_data(apps, schema_editor):
    # Guard: if v3 columns aren't in the schema yet (fresh DB run where this
    # migration executes before 0005/0006), skip here — migration 0008 will seed.
    conn = schema_editor.connection
    with conn.cursor() as cursor:
        table_cols = {col.name for col in conn.introspection.get_table_description(cursor, "driving_theory_drivingtopic")}
    if "recommended_next" not in table_cols:
        return  # defer to 0008_reseed_all_topics

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
