from django.db import migrations


def seed_v3_questions(apps, schema_editor):
    from django.core.management import call_command
    call_command("seed_v3_questions", verbosity=0)


def reverse_v3_questions(apps, schema_editor):
    pass  # irreversible seed


class Migration(migrations.Migration):

    dependencies = [
        ("driving_theory", "0006_v3_add_tags_image_url_topic_breakdown"),
    ]

    operations = [
        migrations.RunPython(seed_v3_questions, reverse_v3_questions),
    ]
