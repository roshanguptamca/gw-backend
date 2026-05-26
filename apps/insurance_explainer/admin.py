from django.contrib import admin
from .models import InsuranceSession, InsuranceMessage


class InsuranceMessageInline(admin.TabularInline):
    model = InsuranceMessage
    extra = 0
    readonly_fields = ["role", "content", "created_at"]
    can_delete = False


@admin.register(InsuranceSession)
class InsuranceSessionAdmin(admin.ModelAdmin):
    list_display = ["id", "user", "country", "language", "insurance_type", "status", "created_at"]
    list_filter = ["status", "country", "language"]
    search_fields = ["user__username", "user__email", "country", "insurance_type"]
    readonly_fields = ["created_at", "updated_at", "analysis", "raw_summary", "status", "error_message"]
    inlines = [InsuranceMessageInline]


@admin.register(InsuranceMessage)
class InsuranceMessageAdmin(admin.ModelAdmin):
    list_display = ["id", "session", "role", "created_at"]
    list_filter = ["role"]
