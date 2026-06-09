from django.db import migrations


def _has_nl_columns(schema_editor):
    """Return True only when the NL column migration has been applied."""
    conn = schema_editor.connection
    with conn.cursor() as cursor:
        cols = {c.name for c in conn.introspection.get_table_description(cursor, "driving_theory_drivingtopic")}
    return "title_nl" in cols


def seed_v3_questions(apps, schema_editor):
    # Guard: NL columns added in 0010 must already exist in the schema.
    # On a fresh install this migration runs before 0010, so we skip here;
    # migration 0012_reseed_after_nl_columns will run the seed after 0011.
    if not _has_nl_columns(schema_editor):
        return
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
