# apps/doc_x/admin.py
from django.contrib import admin

from .models import (
    ChatMessage,
    ChatSession,
    Conversation,
    Document,
    DocumentChunk,
    DocumentFile,
    DocumentInteraction,
    ProcessingJob,
    UserQuestionLimit,
)


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("id", "s3_key_short", "has_summary", "conversation_count", "created_at")
    list_filter = ("created_at",)
    search_fields = ("s3_key", "content", "summary")
    readonly_fields = ("id", "created_at", "content_preview", "summary_preview")

    fieldsets = (
        ("Document Info", {"fields": ("id", "s3_key", "created_at")}),
        ("Content", {"fields": ("content_preview", "content"), "classes": ("collapse",)}),
        ("Summary", {"fields": ("summary_preview", "summary"), "classes": ("collapse",)}),
    )

    def s3_key_short(self, obj):
        """Display shortened S3 key"""
        if len(obj.s3_key) > 50:
            return f"{obj.s3_key[:47]}..."
        return obj.s3_key

    s3_key_short.short_description = "S3 Key"

    def has_summary(self, obj):
        """Show if document has a summary"""
        return bool(obj.summary)

    has_summary.short_description = "Summary"
    has_summary.boolean = True

    def conversation_count(self, obj):
        """Count of conversations for this document"""
        return obj.conversations.count()

    conversation_count.short_description = "Conversations"

    def content_preview(self, obj):
        """Show preview of content"""
        if obj.content:
            preview = obj.content[:200]
            if len(obj.content) > 200:
                preview += "..."
            return preview
        return "No content"

    content_preview.short_description = "Content Preview"

    def summary_preview(self, obj):
        """Show preview of summary"""
        if obj.summary:
            preview = obj.summary[:200]
            if len(obj.summary) > 200:
                preview += "..."
            return preview
        return "No summary"

    summary_preview.short_description = "Summary Preview"


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ("id", "document_id", "role", "message_preview", "created_at")
    list_filter = ("role", "created_at")
    search_fields = ("message", "document__s3_key")
    readonly_fields = ("id", "created_at")
    raw_id_fields = ("document",)

    fieldsets = (
        ("Conversation Info", {"fields": ("id", "document", "role", "created_at")}),
        ("Message", {"fields": ("message",)}),
    )

    def document_id(self, obj):
        """Display document ID"""
        return obj.document.id if obj.document else "-"

    document_id.short_description = "Document ID"

    def message_preview(self, obj):
        """Show preview of message"""
        if len(obj.message) > 100:
            return f"{obj.message[:97]}..."
        return obj.message

    message_preview.short_description = "Message"


@admin.register(DocumentInteraction)
class DocumentInteractionAdmin(admin.ModelAdmin):
    list_display = ("id", "user_display", "session_key", "document_id", "questions_asked", "last_question_at")
    list_filter = ("last_question_at", "questions_asked")
    search_fields = ("user__username", "session_key", "document__s3_key")
    readonly_fields = ("last_question_at",)
    raw_id_fields = ("user", "document")

    fieldsets = (
        ("User/Session Info", {"fields": ("user", "session_key")}),
        ("Document & Activity", {"fields": ("document", "questions_asked", "last_question_at")}),
    )

    def user_display(self, obj):
        """Display username or Anonymous"""
        return obj.user.username if obj.user else "Anonymous"

    user_display.short_description = "User"

    def document_id(self, obj):
        """Display document ID"""
        return obj.document.id if obj.document else "-"

    document_id.short_description = "Document ID"


@admin.register(UserQuestionLimit)
class UserQuestionLimitAdmin(admin.ModelAdmin):
    list_display = ("id", "user_display", "session_key", "document_id", "count", "last_asked")
    list_filter = ("last_asked", "count")
    search_fields = ("user__username", "session_key", "document__s3_key")
    readonly_fields = ("last_asked",)
    raw_id_fields = ("user", "document")

    fieldsets = (
        ("User/Session Info", {"fields": ("user", "session_key")}),
        ("Limit Tracking", {"fields": ("document", "count", "last_asked")}),
    )

    def user_display(self, obj):
        """Display username or Anonymous"""
        return obj.user.username if obj.user else "Anonymous"

    user_display.short_description = "User"

    def document_id(self, obj):
        """Display document ID"""
        return obj.document.id if obj.document else "-"

    document_id.short_description = "Document ID"


@admin.register(DocumentFile)
class DocumentFileAdmin(admin.ModelAdmin):
    list_display = ("filename", "document", "file_type", "file_size", "storage_backend", "uploaded_by", "uploaded_at")
    list_filter = ("storage_backend", "file_type", "uploaded_at")
    search_fields = ("filename", "s3_key", "document__filename", "uploaded_by__username", "uploaded_by__email")
    readonly_fields = ("id", "uploaded_at")
    raw_id_fields = ("document", "uploaded_by")
    ordering = ("-uploaded_at",)


@admin.register(DocumentChunk)
class DocumentChunkAdmin(admin.ModelAdmin):
    list_display = ("id", "document", "chunk_index", "token_count", "start_page", "end_page", "created_at")
    list_filter = ("created_at",)
    search_fields = ("document__filename", "document__s3_key", "content")
    readonly_fields = ("id", "created_at")
    raw_id_fields = ("document",)
    ordering = ("document", "chunk_index")


@admin.register(ProcessingJob)
class ProcessingJobAdmin(admin.ModelAdmin):
    list_display = ("id", "document", "job_type", "status", "started_at", "completed_at", "created_at")
    list_filter = ("job_type", "status", "created_at")
    search_fields = ("document__filename", "document__s3_key", "celery_task_id", "error_message")
    readonly_fields = ("id", "created_at")
    raw_id_fields = ("document",)
    ordering = ("-created_at",)


class ChatMessageInline(admin.TabularInline):
    model = ChatMessage
    extra = 0
    readonly_fields = ("id", "role", "content", "tokens_used", "model_used", "processing_time_ms", "created_at")
    can_delete = False


@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    list_display = ("id", "document", "user", "session_key", "title", "is_active", "updated_at")
    list_filter = ("is_active", "created_at", "updated_at")
    search_fields = ("=id", "title", "session_key", "document__filename", "user__username", "user__email")
    readonly_fields = ("id", "created_at", "updated_at")
    raw_id_fields = ("document", "user")
    inlines = (ChatMessageInline,)
    ordering = ("-updated_at",)


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ("id", "session", "role", "model_used", "tokens_used", "processing_time_ms", "created_at")
    list_filter = ("role", "model_used", "created_at")
    search_fields = ("content", "session__title", "=session__id")
    readonly_fields = ("id", "created_at")
    raw_id_fields = ("session",)
    ordering = ("-created_at",)
