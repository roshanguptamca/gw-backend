from django.db import migrations


SECTION_ORDER = [
    "summary",
    "experience",
    "education",
    "skills",
    "projects",
    "certifications",
    "languages",
    "awards",
    "references",
]


TEMPLATES = [
    ("classic-ats", "Classic ATS", "ATS Friendly", False, True, "single-column", "Arial", "#111827", "normal"),
    (
        "modern-professional",
        "Modern Professional",
        "Modern",
        True,
        True,
        "accent-header",
        "Inter",
        "#2563EB",
        "normal",
    ),
    (
        "executive-clean",
        "Executive Clean",
        "Executive",
        False,
        True,
        "centered",
        "Georgia",
        "#374151",
        "relaxed",
    ),
    (
        "developer-tech",
        "Developer Tech",
        "Developer / Tech",
        False,
        True,
        "technical",
        "Roboto Mono",
        "#0F766E",
        "compact",
    ),
    (
        "student-fresher",
        "Student Fresher",
        "Student / Fresher",
        True,
        True,
        "education-first",
        "Inter",
        "#7C3AED",
        "normal",
    ),
    (
        "creative-photo",
        "Creative Photo",
        "Photo CV",
        True,
        False,
        "photo-header",
        "Poppins",
        "#DB2777",
        "relaxed",
    ),
    (
        "european-cv",
        "European CV",
        "European CV",
        True,
        True,
        "eu-standard",
        "Arial",
        "#1D4ED8",
        "normal",
    ),
    (
        "minimal-one-page",
        "Minimal One Page",
        "Minimal",
        False,
        True,
        "compact",
        "Inter",
        "#111827",
        "compact",
    ),
    (
        "elegant-timeline",
        "Elegant Timeline",
        "Creative",
        True,
        False,
        "timeline",
        "Lora",
        "#7C2D12",
        "relaxed",
    ),
    (
        "compact-recruiter",
        "Compact Recruiter",
        "ATS Friendly",
        False,
        True,
        "dense",
        "Arial",
        "#1F2937",
        "compact",
    ),
]


def seed_catalog(apps, schema_editor):
    ResumeTemplate = apps.get_model("templates_app", "ResumeTemplate")
    classic = ResumeTemplate.objects.filter(slug="classic").first()
    if classic:
        if ResumeTemplate.objects.filter(slug="classic-ats").exists():
            classic.is_active = False
            classic.save(update_fields=["is_active"])
        else:
            classic.slug = "classic-ats"
            classic.save(update_fields=["slug"])

    for order, (slug, name, category, photo, ats, layout, font, color, spacing) in enumerate(TEMPLATES, 1):
        ResumeTemplate.objects.update_or_create(
            slug=slug,
            defaults={
                "name": name,
                "category": category,
                "description": f"{name} is an original GuideWisey layout for a clear, professional CV.",
                "html_template": f"resumes/{slug.replace('-', '_')}.html",
                "supports_photo": photo,
                "is_ats_friendly": ats,
                "is_premium": False,
                "layout_type": layout,
                "supported_formats": ["pdf", "docx"],
                "default_settings": {
                    "primary_color": color,
                    "font_family": font,
                    "font_size": "medium",
                    "spacing": spacing,
                    "include_photo": photo,
                    "section_order": SECTION_ORDER,
                    "page_layout": "A4",
                },
                "supported_locales": ["en", "nl"],
                "is_active": True,
                "sort_order": order,
            },
        )


def remove_catalog(apps, schema_editor):
    ResumeTemplate = apps.get_model("templates_app", "ResumeTemplate")
    ResumeTemplate.objects.filter(slug__in=[item[0] for item in TEMPLATES]).delete()


class Migration(migrations.Migration):
    dependencies = [("templates_app", "0004_alter_resumetemplate_options_resumetemplate_category_and_more")]

    operations = [migrations.RunPython(seed_catalog, remove_catalog)]
