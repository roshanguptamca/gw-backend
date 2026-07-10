from django.db import migrations, models
import uuid


TEMPLATES = [
    {
        "key": "latest-market-standard",
        "name": "Latest Market Standard Scan",
        "description": "Broad baseline for modern SaaS and web applications. Runs the full SecureWise engine set when the repository exposes matching assets or runtime targets.",
        "recommended_for": "Default organization policy",
        "scan_types": ["full"],
        "fail_on_severity": "high",
        "max_critical": 0,
        "max_high": 0,
        "max_medium": 10,
        "fail_on_secrets": True,
        "fail_on_new_findings_only": False,
        "allow_accepted_risks": True,
        "allow_false_positives": True,
        "is_recommended": True,
        "sort_order": 10,
    },
    {
        "key": "owasp-web-baseline",
        "name": "OWASP Web Baseline",
        "description": "Balanced web application profile focused on SAST, dependency, secret, IaC, API, and DAST coverage aligned to OWASP-style review.",
        "recommended_for": "Web apps and APIs",
        "scan_types": ["sast", "sca", "secrets", "iac", "api", "dast"],
        "fail_on_severity": "high",
        "max_critical": 0,
        "max_high": 2,
        "max_medium": 20,
        "fail_on_secrets": True,
        "fail_on_new_findings_only": False,
        "allow_accepted_risks": True,
        "allow_false_positives": True,
        "is_recommended": False,
        "sort_order": 20,
    },
    {
        "key": "fast-pr-gate",
        "name": "Fast PR Gate",
        "description": "Fast feedback policy for pull requests. Focuses on source, dependencies, secrets, and IaC without runtime DAST.",
        "recommended_for": "Pull requests",
        "scan_types": ["sast", "sca", "secrets", "iac"],
        "fail_on_severity": "high",
        "max_critical": 0,
        "max_high": 0,
        "max_medium": -1,
        "fail_on_secrets": True,
        "fail_on_new_findings_only": True,
        "allow_accepted_risks": True,
        "allow_false_positives": True,
        "is_recommended": False,
        "sort_order": 30,
    },
    {
        "key": "secrets-dependencies",
        "name": "Secrets and Dependencies",
        "description": "Focused policy for credential leaks and vulnerable packages when a quick supply-chain check is needed.",
        "recommended_for": "Supply-chain checks",
        "scan_types": ["secrets", "sca"],
        "fail_on_severity": "medium",
        "max_critical": 0,
        "max_high": 0,
        "max_medium": 5,
        "fail_on_secrets": True,
        "fail_on_new_findings_only": False,
        "allow_accepted_risks": True,
        "allow_false_positives": True,
        "is_recommended": False,
        "sort_order": 40,
    },
    {
        "key": "runtime-api-dast",
        "name": "Runtime API and DAST",
        "description": "Runtime-focused policy for repositories that can expose an OpenAPI spec, container image, or live application target.",
        "recommended_for": "Runtime scans",
        "scan_types": ["api", "dast", "container"],
        "fail_on_severity": "high",
        "max_critical": 0,
        "max_high": 1,
        "max_medium": 15,
        "fail_on_secrets": False,
        "fail_on_new_findings_only": False,
        "allow_accepted_risks": True,
        "allow_false_positives": True,
        "is_recommended": False,
        "sort_order": 50,
    },
]


def seed_templates(apps, schema_editor):
    Template = apps.get_model("securewise", "SecureWiseScanPolicyTemplate")
    for template in TEMPLATES:
        Template.objects.update_or_create(key=template["key"], defaults={**template, "is_active": True})


def unseed_templates(apps, schema_editor):
    Template = apps.get_model("securewise", "SecureWiseScanPolicyTemplate")
    Template.objects.filter(key__in=[template["key"] for template in TEMPLATES]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("securewise", "0007_alter_securewisefinding_ai_fix_suggestion_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="SecureWiseScanPolicyTemplate",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("key", models.SlugField(max_length=80, unique=True)),
                ("name", models.CharField(max_length=150)),
                ("description", models.TextField(blank=True)),
                ("recommended_for", models.CharField(blank=True, max_length=150)),
                ("scan_types", models.JSONField(default=list)),
                (
                    "fail_on_severity",
                    models.CharField(
                        choices=[
                            ("critical", "Critical"),
                            ("high", "High"),
                            ("medium", "Medium"),
                            ("low", "Low"),
                            ("info", "Info"),
                        ],
                        default="high",
                        max_length=20,
                    ),
                ),
                ("max_critical", models.IntegerField(default=0)),
                ("max_high", models.IntegerField(default=5)),
                ("max_medium", models.IntegerField(default=-1, help_text="-1 = unlimited.")),
                ("fail_on_secrets", models.BooleanField(default=True)),
                ("fail_on_new_findings_only", models.BooleanField(default=False)),
                ("allow_accepted_risks", models.BooleanField(default=True)),
                ("allow_false_positives", models.BooleanField(default=True)),
                ("is_recommended", models.BooleanField(default=False)),
                ("is_active", models.BooleanField(default=True)),
                ("sort_order", models.PositiveIntegerField(default=100)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Scan Policy Template",
                "verbose_name_plural": "Scan Policy Templates",
                "ordering": ["sort_order", "name"],
            },
        ),
        migrations.RunPython(seed_templates, unseed_templates),
    ]
