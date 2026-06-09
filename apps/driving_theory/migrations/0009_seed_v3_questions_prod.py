"""
Seeds the full 3000+ v3 question bank into production.

Migration 0008 was deployed with only seed_driving_theory (180 questions).
This migration runs seed_v3_questions on top to add the remaining 3000+ questions.
Idempotent: uses get_or_create so re-running is always safe.

NOTE: On a fresh install this migration runs before the NL-column migrations
(0010/0011). If title_nl is not present yet, seeding is deferred to
migration 0012_reseed_after_nl_columns which runs after all NL schema work.
"""

from django.db import migrations


def _has_nl_columns(schema_editor):
    conn = schema_editor.connection
    with conn.cursor() as cursor:
        cols = {c.name for c in conn.introspection.get_table_description(cursor, "driving_theory_drivingtopic")}
    return "title_nl" in cols


def seed_v3(apps, schema_editor):
    if not _has_nl_columns(schema_editor):
        return  # defer to 0012_reseed_after_nl_columns
    from django.core.management import call_command
    call_command("seed_v3_questions", verbosity=0)


def noop(apps, schema_editor):
    pass  # idempotent; no rollback needed


class Migration(migrations.Migration):

    dependencies = [
        ("driving_theory", "0008_reseed_all_topics"),
    ]

    operations = [
        migrations.RunPython(seed_v3, reverse_code=noop),
    ]
