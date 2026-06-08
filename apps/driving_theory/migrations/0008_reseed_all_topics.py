"""
Re-runs the full seed_driving_theory command after all v3 schema migrations
are applied. This is the canonical seed migration — 0002 defers to this
on fresh installs to avoid column-not-found errors.
Idempotent: uses update_or_create internally.
"""

from django.db import migrations


def reseed(apps, schema_editor):
    from django.core.management import call_command
    call_command("seed_driving_theory", verbosity=0)


def noop(apps, schema_editor):
    pass  # seed is idempotent; no rollback needed


class Migration(migrations.Migration):

    dependencies = [
        ("driving_theory", "0007_seed_v3_questions"),
    ]

    operations = [
        migrations.RunPython(reseed, reverse_code=noop),
    ]
