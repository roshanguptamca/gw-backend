# apps/doc_x/models.py
from django.db import models
from django.conf import settings


class Document(models.Model):
    s3_key = models.CharField(max_length=255)
    content = models.TextField()
    summary = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Document {self.id}"


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
        unique_together = ('user', 'document', 'session_key')

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
        on_delete=models.CASCADE
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
