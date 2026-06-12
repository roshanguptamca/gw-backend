from django.contrib import admin

from .models import ResumeTemplate


@admin.register(ResumeTemplate)
class ResumeTemplateAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "slug",
        "category",
        "layout_type",
        "supports_photo",
        "is_ats_friendly",
        "is_premium",
        "is_active",
        "sort_order",
    )
    list_filter = ("category", "supports_photo", "is_ats_friendly", "is_premium", "is_active")
    search_fields = ("name", "slug", "description", "html_template")
    list_editable = ("is_active", "sort_order")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("sort_order", "name")
