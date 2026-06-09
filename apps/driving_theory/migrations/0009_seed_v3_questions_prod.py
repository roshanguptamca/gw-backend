"""
Seeds the full 3000+ v3 question bank into production.

Migration 0008 was deployed with only seed_driving_theory (180 questions).
This migration runs seed_v3_questions on top to add the remaining 3000+ questions.
Idempotent: uses get_or_create so re-running is always safe.
"""

from django.db import migrations


def seed_v3(apps, schema_editor):
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
