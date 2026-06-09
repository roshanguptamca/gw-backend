"""
Migration 0014: Apply seed_nl_questions

Seeds the 72 hardcoded Dutch (NL) translations for the
"Introduction to Dutch Driving" topic questions and their options.

This migration is safe to run on both:
- Production (existing data preserved, NL fields updated)
- Fresh installs (after 0012 populates base questions)

No network access required — translations are hardcoded in seed_nl_questions.py.
Fully idempotent (overwrites with same data on re-run).
"""

from django.db import migrations


def apply_nl_seeds(apps, schema_editor):
    from django.core.management import call_command
    call_command("seed_nl_questions", verbosity=0)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("driving_theory", "0013_add_anonymous_mock_test_completion"),
    ]

    operations = [
        migrations.RunPython(apply_nl_seeds, reverse_code=noop),
    ]
