from django.contrib import admin

from .models import UserFile


@admin.register(UserFile)
class UserFileAdmin(admin.ModelAdmin):
    list_display = ("filename", "content_type", "file_size", "purpose", "owner", "expires_at", "created_at")
    list_filter = ("purpose", "content_type", "created_at", "expires_at")
    search_fields = ("filename", "user__username", "user__email", "anonymous_identity__email")
    readonly_fields = ("id", "created_at")
    raw_id_fields = ("user", "anonymous_identity")
    ordering = ("-created_at",)

    @admin.display(description="Owner")
    def owner(self, obj):
        return obj.user or obj.anonymous_identity
