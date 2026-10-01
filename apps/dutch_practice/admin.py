from django.contrib import admin

from .models import AttemptQuestion, PracticeAttempt, PracticeMedia, PracticeQuestion


@admin.register(PracticeQuestion)
class PracticeQuestionAdmin(admin.ModelAdmin):
    list_display = ("code", "level", "skill", "review_status", "is_active")
    list_filter = ("level", "skill", "review_status", "is_active")
    search_fields = ("code",)


class AttemptQuestionInline(admin.TabularInline):
    model = AttemptQuestion
    extra = 0
    can_delete = False
    readonly_fields = ("position", "snapshot", "response", "answered_at", "media")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(PracticeAttempt)
class PracticeAttemptAdmin(admin.ModelAdmin):
    list_display = ("user", "level", "skill", "mock_test", "status", "score", "created_at")
    list_filter = ("level", "skill", "status")
    readonly_fields = tuple(field.name for field in PracticeAttempt._meta.fields)
    inlines = (AttemptQuestionInline,)

    def has_add_permission(self, request):
        return False


@admin.register(PracticeMedia)
class PracticeMediaAdmin(admin.ModelAdmin):
    list_display = ("code", "mime_type", "duration_seconds", "sha256")
    readonly_fields = ("code", "mime_type", "duration_seconds", "sha256")
    exclude = ("content",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
