from django.db import migrations


def seed_classic_template(apps, schema_editor):
    ResumeTemplate = apps.get_model("templates_app", "ResumeTemplate")
    ResumeTemplate.objects.get_or_create(
        slug="classic",
        defaults={
            "name": "Classic",
            "description": "Clean single-column ATS-friendly resume template.",
            "html_template": "exports/resume.html",
            "supported_locales": ["en", "nl"],
            "is_active": True,
        },
    )


def remove_classic_template(apps, schema_editor):
    ResumeTemplate = apps.get_model("templates_app", "ResumeTemplate")
    ResumeTemplate.objects.filter(slug="classic").delete()


class Migration(migrations.Migration):
    dependencies = [("templates_app", "0001_initial")]

    operations = [migrations.RunPython(seed_classic_template, remove_classic_template)]
