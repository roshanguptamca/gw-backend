# app/serializers.py
from rest_framework import serializers
from .models import (
    Document,
    Conversation,
    DocumentFile,
    DocumentChunk,
    ProcessingJob,
    ChatSession,
    ChatMessage,
)


class DocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = [
            "id",
            "s3_key",
            "content",
            "summary",
            "created_at",
            "user",
            "filename",
            "file_type",
            "file_size",
            "processing_status",
            "metadata",
        ]
        read_only_fields = ["id", "created_at", "processing_status"]


class ConversationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Conversation
        fields = ["id", "document", "role", "message", "created_at"]


class DocumentFileSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentFile
        fields = [
            "id",
            "document",
            "filename",
            "file_type",
            "file_size",
            "s3_key",
            "storage_backend",
            "uploaded_at",
            "uploaded_by",
            "metadata",
        ]
        read_only_fields = ["id", "uploaded_at"]


class DocumentChunkSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentChunk
        fields = ["id", "document", "chunk_index", "content", "token_count", "start_page", "end_page", "created_at"]
        read_only_fields = ["id", "created_at"]


class ProcessingJobSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProcessingJob
        fields = [
            "id",
            "document",
            "job_type",
            "status",
            "celery_task_id",
            "started_at",
            "completed_at",
            "error_message",
            "result",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class ChatSessionSerializer(serializers.ModelSerializer):
    message_count = serializers.SerializerMethodField()

    class Meta:
        model = ChatSession
        fields = [
            "id",
            "document",
            "user",
            "session_key",
            "title",
            "created_at",
            "updated_at",
            "is_active",
            "message_count",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_message_count(self, obj):
        return obj.messages.count()


class ChatMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatMessage
        fields = [
            "id",
            "session",
            "role",
            "content",
            "tokens_used",
            "model_used",
            "processing_time_ms",
            "created_at",
            "metadata",
        ]
        read_only_fields = ["id", "created_at"]
