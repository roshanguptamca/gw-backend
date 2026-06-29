# apps/doc_x/models.py
import uuid

from django.conf import settings
from django.db import models


class Document(models.Model):
    """
    Main document model - enhanced for new features while maintaining backward compatibility.
    Existing fields remain unchanged.
    """

    # Existing fields (DO NOT MODIFY - backward compatibility)
    s3_key = models.CharField(max_length=255)
    content = models.TextField()
    summary = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # New optional fields for enhanced functionality
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True, related_name="documents"
    )
    filename = models.CharField(max_length=255, blank=True, null=True)
    file_type = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        choices=[
            ("pdf", "PDF"),
            ("docx", "DOCX"),
            ("txt", "Text"),
            ("csv", "CSV"),
            ("xlsx", "Excel"),
            ("image", "Image"),
        ],
    )
    file_size = models.IntegerField(null=True, blank=True, help_text="File size in bytes")
    processing_status = models.CharField(
        max_length=20,
        default="completed",
        choices=[
            ("pending", "Pending"),
            ("processing", "Processing"),
            ("completed", "Completed"),
            ("failed", "Failed"),
        ],
    )
    metadata = models.JSONField(default=dict, blank=True, help_text="Additional metadata")

    def __str__(self):
        return f"Document {self.id} - {self.filename or self.s3_key}"

    class Meta:
        ordering = ["-created_at"]


class Conversation(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="conversations")
    role = models.CharField(max_length=20)  # 'user' or 'assistant'
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.role} - Doc {self.document.id}"


class DocumentInteraction(models.Model):
    """
    Tracks how many follow-up questions a user has asked for a document.
    (Optional, can be used for analytics or limits)
    """

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True)
    session_key = models.CharField(max_length=40, null=True, blank=True)
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="interactions")
    questions_asked = models.PositiveIntegerField(default=0)
    last_question_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("user", "document", "session_key")

    def __str__(self):
        if self.user:
            return f"{self.user.username} - Doc {self.document.id} ({self.questions_asked})"
        return f"Session {self.session_key} - Doc {self.document.id} ({self.questions_asked})"


class UserQuestionLimit(models.Model):
    """
    Tracks per-user or per-session question limits for a document.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,  # allow null for anonymous session users
        blank=True,
        on_delete=models.CASCADE,
    )
    session_key = models.CharField(max_length=40, null=True, blank=True)
    document = models.ForeignKey(Document, on_delete=models.CASCADE)
    count = models.PositiveIntegerField(default=0)
    last_asked = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("user", "document", "session_key")

    def __str__(self):
        if self.user:
            return f"{self.user.username} - Doc {self.document.id} ({self.count})"
        return f"Session {self.session_key} - Doc {self.document.id} ({self.count})"


# ============================================================================
# NEW MODELS FOR ENHANCED DOCUMENT PROCESSING
# ============================================================================


class DocumentFile(models.Model):
    """
    Stores file metadata separate from document content.
    Allows multiple file versions or related files per document.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="files")
    filename = models.CharField(max_length=255)
    file_type = models.CharField(max_length=50)
    file_size = models.IntegerField(help_text="File size in bytes")
    s3_key = models.CharField(max_length=500, unique=True)
    storage_backend = models.CharField(
        max_length=20, default="db", choices=[("s3", "S3"), ("local", "Local"), ("db", "Database")]
    )
    # Raw file bytes — populated when storage_backend == "db"
    file_data = models.BinaryField(null=True, blank=True, editable=False)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return f"{self.filename} ({self.file_type})"

    class Meta:
        ordering = ["-uploaded_at"]


class DocumentChunk(models.Model):
    """
    Stores document chunks for better AI processing.
    Large documents are split into chunks that fit within AI context limits.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="chunks")
    chunk_index = models.IntegerField(help_text="Order of this chunk in the document")
    content = models.TextField()
    token_count = models.IntegerField(default=0)
    start_page = models.IntegerField(null=True, blank=True)
    end_page = models.IntegerField(null=True, blank=True)
    embedding = models.JSONField(null=True, blank=True, help_text="Vector embedding for semantic search")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Chunk {self.chunk_index} of Doc {self.document.id}"

    class Meta:
        ordering = ["document", "chunk_index"]
        unique_together = ("document", "chunk_index")


class ProcessingJob(models.Model):
    """
    Tracks async document processing jobs.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="processing_jobs")
    job_type = models.CharField(
        max_length=50,
        choices=[
            ("extraction", "Text Extraction"),
            ("chunking", "Document Chunking"),
            ("summarization", "Summarization"),
            ("embedding", "Embedding Generation"),
        ],
    )
    status = models.CharField(
        max_length=20,
        default="pending",
        choices=[
            ("pending", "Pending"),
            ("running", "Running"),
            ("completed", "Completed"),
            ("failed", "Failed"),
        ],
    )
    celery_task_id = models.CharField(max_length=255, null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True, null=True)
    result = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.job_type} job for Doc {self.document.id} - {self.status}"

    class Meta:
        ordering = ["-created_at"]


class ChatSession(models.Model):
    """
    Groups chat interactions for a document.
    Replaces the older Conversation model with better structure.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="chat_sessions")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True)
    session_key = models.CharField(max_length=40, null=True, blank=True, help_text="For anonymous users")
    title = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"Chat {self.id} for Doc {self.document.id}"

    class Meta:
        ordering = ["-updated_at"]


class ChatMessage(models.Model):
    """
    Individual messages within a chat session.
    Replaces Conversation with more detailed tracking.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=20, choices=[("user", "User"), ("assistant", "Assistant"), ("system", "System")])
    content = models.TextField()
    tokens_used = models.IntegerField(null=True, blank=True)
    model_used = models.CharField(max_length=100, null=True, blank=True)
    processing_time_ms = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    metadata = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return f"{self.role} message in session {self.session.id}"

    class Meta:
        ordering = ["created_at"]
