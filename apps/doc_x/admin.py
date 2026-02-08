# apps/doc_x/admin.py
from django.contrib import admin
from .models import Document, Conversation, DocumentInteraction, UserQuestionLimit


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ('id', 's3_key_short', 'has_summary', 'conversation_count', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('s3_key', 'content', 'summary')
    readonly_fields = ('id', 'created_at', 'content_preview', 'summary_preview')

    fieldsets = (
        ('Document Info', {
            'fields': ('id', 's3_key', 'created_at')
        }),
        ('Content', {
            'fields': ('content_preview', 'content'),
            'classes': ('collapse',)
        }),
        ('Summary', {
            'fields': ('summary_preview', 'summary'),
            'classes': ('collapse',)
        }),
    )

    def s3_key_short(self, obj):
        """Display shortened S3 key"""
        if len(obj.s3_key) > 50:
            return f"{obj.s3_key[:47]}..."
        return obj.s3_key

    s3_key_short.short_description = 'S3 Key'

    def has_summary(self, obj):
        """Show if document has a summary"""
        return bool(obj.summary)

    has_summary.short_description = 'Summary'
    has_summary.boolean = True

    def conversation_count(self, obj):
        """Count of conversations for this document"""
        return obj.conversations.count()

    conversation_count.short_description = 'Conversations'

    def content_preview(self, obj):
        """Show preview of content"""
        if obj.content:
            preview = obj.content[:200]
            if len(obj.content) > 200:
                preview += "..."
            return preview
        return "No content"

    content_preview.short_description = 'Content Preview'

    def summary_preview(self, obj):
        """Show preview of summary"""
        if obj.summary:
            preview = obj.summary[:200]
            if len(obj.summary) > 200:
                preview += "..."
            return preview
        return "No summary"

    summary_preview.short_description = 'Summary Preview'


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ('id', 'document_id', 'role', 'message_preview', 'created_at')
    list_filter = ('role', 'created_at')
    search_fields = ('message', 'document__s3_key')
    readonly_fields = ('id', 'created_at')
    raw_id_fields = ('document',)

    fieldsets = (
        ('Conversation Info', {
            'fields': ('id', 'document', 'role', 'created_at')
        }),
        ('Message', {
            'fields': ('message',)
        }),
    )

    def document_id(self, obj):
        """Display document ID"""
        return obj.document.id if obj.document else '-'

    document_id.short_description = 'Document ID'

    def message_preview(self, obj):
        """Show preview of message"""
        if len(obj.message) > 100:
            return f"{obj.message[:97]}..."
        return obj.message

    message_preview.short_description = 'Message'


@admin.register(DocumentInteraction)
class DocumentInteractionAdmin(admin.ModelAdmin):
    list_display = ('id', 'user_display', 'session_key', 'document_id', 'questions_asked', 'last_question_at')
    list_filter = ('last_question_at', 'questions_asked')
    search_fields = ('user__username', 'session_key', 'document__s3_key')
    readonly_fields = ('last_question_at',)
    raw_id_fields = ('user', 'document')

    fieldsets = (
        ('User/Session Info', {
            'fields': ('user', 'session_key')
        }),
        ('Document & Activity', {
            'fields': ('document', 'questions_asked', 'last_question_at')
        }),
    )

    def user_display(self, obj):
        """Display username or Anonymous"""
        return obj.user.username if obj.user else 'Anonymous'

    user_display.short_description = 'User'

    def document_id(self, obj):
        """Display document ID"""
        return obj.document.id if obj.document else '-'

    document_id.short_description = 'Document ID'


@admin.register(UserQuestionLimit)
class UserQuestionLimitAdmin(admin.ModelAdmin):
    list_display = ('id', 'user_display', 'session_key', 'document_id', 'count', 'last_asked')
    list_filter = ('last_asked', 'count')
    search_fields = ('user__username', 'session_key', 'document__s3_key')
    readonly_fields = ('last_asked',)
    raw_id_fields = ('user', 'document')

    fieldsets = (
        ('User/Session Info', {
            'fields': ('user', 'session_key')
        }),
        ('Limit Tracking', {
            'fields': ('document', 'count', 'last_asked')
        }),
    )

    def user_display(self, obj):
        """Display username or Anonymous"""
        return obj.user.username if obj.user else 'Anonymous'

    user_display.short_description = 'User'

    def document_id(self, obj):
        """Display document ID"""
        return obj.document.id if obj.document else '-'

    document_id.short_description = 'Document ID'