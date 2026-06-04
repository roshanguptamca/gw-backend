from django.db import models
from django.contrib.auth.models import User


class InsuranceSession(models.Model):
    """Stores an insurance policy analysis session."""

    class Status(models.TextChoices):
        PENDING = "ins_pending", "Pending"
        PROCESSING = "ins_processing", "Processing"
        COMPLETED = "ins_completed", "Completed"
        FAILED = "ins_failed", "Failed"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="insurance_sessions")

    # Context inputs
    country = models.CharField(max_length=100, default="International")
    language = models.CharField(max_length=50, default="English")
    insurance_type = models.CharField(max_length=100, blank=True, default="")
    provider_url = models.URLField(blank=True, default="")

    # Policy content (text paste or extracted from file)
    policy_text = models.TextField(blank=True, default="")
    filename = models.CharField(max_length=255, blank=True, default="")
    file_data = models.BinaryField(blank=True, null=True)

    # AI output — structured JSON analysis
    analysis = models.JSONField(null=True, blank=True)
    raw_summary = models.TextField(blank=True, default="")

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    error_message = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Insurance session {self.id} ({self.country}/{self.language}) – {self.status}"


class InsuranceMessage(models.Model):
    """Chat messages within an insurance session."""

    class Role(models.TextChoices):
        USER = "user", "User"
        ASSISTANT = "assistant", "Assistant"

    session = models.ForeignKey(InsuranceSession, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=20, choices=Role.choices)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"[{self.role}] session={self.session_id} – {self.content[:60]}"
