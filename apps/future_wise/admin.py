"""
Django Admin configuration for FutureWise / DearTomorrow.
"""

from django.contrib import admin
from django.utils.html import format_html

from .models import (
    AbuseLog,
    EmailReminder,
    ReminderAttachment,
    ReminderChannel,
    ReminderDeliveryLog,
    UserNotificationPreference,
)


class ReminderAttachmentInline(admin.TabularInline):
    model = ReminderAttachment
    extra = 0
    readonly_fields = ("id", "original_filename", "content_type", "size_bytes", "s3_key", "storage_key", "created_at")
    can_delete = False


class DeliveryLogInline(admin.TabularInline):
    model = ReminderDeliveryLog
    extra = 0
    readonly_fields = (
        "channel",
        "attempt_number",
        "status",
        "provider_message_id",
        "error_message",
        "attempted_at",
        "completed_at",
    )
    can_delete = False
    ordering = ("channel__code", "attempt_number")


@admin.register(EmailReminder)
class EmailReminderAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "email",
        "tier",
        "status_badge",
        "channels_requested",
        "scheduled_at",
        "retry_count",
        "created_at",
    )
    list_filter = ("status", "tier", "email_verified")
    search_fields = ("email", "subject", "id")
    readonly_fields = (
        "id",
        "verification_token",
        "brevo_message_id",
        "sent_at",
        "created_at",
        "updated_at",
    )
    ordering = ("-created_at",)
    inlines = [ReminderAttachmentInline, DeliveryLogInline]
    actions = ["cancel_selected", "requeue_dead_letters"]

    def status_badge(self, obj):
        colors = {
            "pending_verification": "#f0ad4e",
            "scheduled": "#5bc0de",
            "queued": "#0275d8",
            "sent": "#5cb85c",
            "failed": "#d9534f",
            "cancelled": "#aaa",
            "dead_letter": "#c9302c",
        }
        color = colors.get(obj.status, "#999")
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:4px">{}</span>',
            color,
            obj.get_status_display(),
        )

    status_badge.short_description = "Status"

    @admin.action(description="Cancel selected reminders")
    def cancel_selected(self, request, queryset):
        updated = queryset.exclude(status__in=["sent", "cancelled", "dead_letter"]).update(
            status=EmailReminder.Status.CANCELLED
        )
        self.message_user(request, f"{updated} reminder(s) cancelled.")

    @admin.action(description="Re-queue dead-letter reminders")
    def requeue_dead_letters(self, request, queryset):
        # Reset dead-letter reminders to SCHEDULED so APScheduler picks them up
        requeued = queryset.filter(status=EmailReminder.Status.DEAD_LETTER).update(
            status=EmailReminder.Status.SCHEDULED,
            retry_count=0,
            last_error="",
        )
        self.message_user(request, f"{requeued} reminder(s) re-queued for next scheduler run.")


@admin.register(ReminderAttachment)
class ReminderAttachmentAdmin(admin.ModelAdmin):
    list_display = ("id", "reminder", "original_filename", "content_type", "size_bytes", "created_at")
    readonly_fields = ("id", "s3_key", "storage_key", "created_at")
    search_fields = ("original_filename", "reminder__email")


@admin.register(AbuseLog)
class AbuseLogAdmin(admin.ModelAdmin):
    list_display = ("email", "ip_address", "action", "created_at")
    list_filter = ("action",)
    search_fields = ("email", "ip_address")
    readonly_fields = ("email", "ip_address", "action", "created_at")


# ── Multi-Channel Admin ───────────────────────────────────────────────────────


@admin.register(ReminderChannel)
class ReminderChannelAdmin(admin.ModelAdmin):
    list_display = ("code", "display_name", "is_active", "provider_class", "updated_at")
    list_editable = ("is_active",)
    readonly_fields = ("created_at", "updated_at")
    ordering = ("code",)


@admin.register(UserNotificationPreference)
class UserNotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = (
        "email",
        "channel",
        "is_opted_in",
        "phone_number",
        "telegram_chat_id",
        "whatsapp_opted_in",
        "updated_at",
    )
    list_filter = ("channel", "is_opted_in", "whatsapp_opted_in")
    search_fields = ("email", "phone_number", "telegram_chat_id")
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(ReminderDeliveryLog)
class ReminderDeliveryLogAdmin(admin.ModelAdmin):
    list_display = (
        "reminder",
        "channel",
        "attempt_number",
        "status_badge",
        "provider_message_id",
        "attempted_at",
    )
    list_filter = ("status", "channel")
    search_fields = ("reminder__email", "provider_message_id", "error_message")
    readonly_fields = (
        "reminder",
        "channel",
        "attempt_number",
        "status",
        "provider_message_id",
        "provider_response",
        "error_message",
        "attempted_at",
        "completed_at",
    )
    ordering = ("-attempted_at",)

    def status_badge(self, obj):
        colors = {
            "pending": "#f0ad4e",
            "success": "#5cb85c",
            "failed": "#d9534f",
            "skipped": "#aaa",
        }
        color = colors.get(obj.status, "#999")
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:4px">{}</span>',
            color,
            obj.get_status_display(),
        )

    status_badge.short_description = "Status"
