"""
Re-seeds all topics (seed_driving_theory) then seeds all 3000+ v3 questions
(seed_v3_questions) after all schema migrations are applied.

This is the canonical combined seed migration for fresh installs.
Migrations 0002 and 0004 defer here via column-presence guard.
All seeds are idempotent (update_or_create / get_or_create).

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


def reseed(apps, schema_editor):
    if not _has_nl_columns(schema_editor):
        return  # defer to 0012_reseed_after_nl_columns
    from django.core.management import call_command
    # 1. Ensure all 15 topics, lessons, and base questions exist
    call_command("seed_driving_theory", verbosity=0)
    # 2. Add the full 3000+ v3 question bank on top
    call_command("seed_v3_questions", verbosity=0)


def noop(apps, schema_editor):
    pass  # seeds are idempotent; no rollback needed


class Migration(migrations.Migration):

    dependencies = [
        ("driving_theory", "0007_seed_v3_questions"),
    ]

    operations = [
        migrations.RunPython(reseed, reverse_code=noop),
    ]
