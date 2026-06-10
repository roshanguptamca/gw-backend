from django.db import models


def default_supported_formats():
    return ["pdf", "docx"]


class ResumeTemplate(models.Model):
    CATEGORY_CHOICES = [
        ("ATS Friendly", "ATS Friendly"),
        ("Modern", "Modern"),
        ("Executive", "Executive"),
        ("Creative", "Creative"),
        ("Student / Fresher", "Student / Fresher"),
        ("Developer / Tech", "Developer / Tech"),
        ("European CV", "European CV"),
        ("Minimal", "Minimal"),
        ("Photo CV", "Photo CV"),
    ]

    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=120)
    category = models.CharField(max_length=40, choices=CATEGORY_CHOICES, default="ATS Friendly")
    description = models.TextField(blank=True)
    html_template = models.CharField(max_length=255, default="exports/resume.html")
    css = models.TextField(blank=True)
    preview_image = models.CharField(max_length=255, blank=True)
    preview_url = models.URLField(blank=True)
    supported_locales = models.JSONField(default=list, blank=True)
    supports_photo = models.BooleanField(default=True)
    is_ats_friendly = models.BooleanField(default=False)
    is_premium = models.BooleanField(default=False)
    layout_type = models.CharField(max_length=60, default="single-column")
    supported_formats = models.JSONField(default=default_supported_formats)
    default_settings = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name
