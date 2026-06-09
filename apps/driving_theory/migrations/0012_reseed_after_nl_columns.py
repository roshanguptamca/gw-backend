"""
Reseeds all driving theory content after the NL-column migrations (0010, 0011)
have been applied.

SAFETY RULE: Only runs seeds on a FRESH INSTALL (no questions in DB yet).
On an existing production database the questions were already seeded by
migrations 0007/0009, so we skip to avoid destroying 3000+ v3 questions.

On a fresh install, migrations 0007-0009 skipped their seeds (title_nl guard),
so this migration runs both seeds to populate everything from scratch.
"""

from django.db import migrations


def reseed_all(apps, schema_editor):
    DrivingQuestion = apps.get_model("driving_theory", "DrivingQuestion")
    if DrivingQuestion.objects.filter(is_active=True).count() > 100:
        # Production — data already seeded by 0007/0009. Skip to preserve data.
        return
    # Fresh install — populate all data now that NL columns exist.
    from django.core.management import call_command
    call_command("seed_driving_theory", verbosity=0)
    call_command("seed_v3_questions", verbosity=0)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("driving_theory", "0011_add_nl_json_fields"),
    ]

    operations = [
        migrations.RunPython(reseed_all, reverse_code=noop),
    ]
