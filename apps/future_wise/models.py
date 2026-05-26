"""
FutureWise / DearTomorrow — Email Reminder Models

Supports both anonymous verified users (email-OTP flow) and registered
account users. Uses a UUID primary key for privacy.
"""

import secrets
import uuid

from django.contrib.auth import get_user_model
from django.db import models
from django.utils import timezone

User = get_user_model()

# Verification token validity window
VERIFICATION_TOKEN_TTL_MINUTES = 30


class EmailReminder(models.Model):
    """
    Core model for a future self-email reminder.
    Lifecycle: PENDING_VERIFICATION → SCHEDULED → QUEUED → SENT
                                            └─ CANCELLED
                                   QUEUED → FAILED → DEAD_LETTER (after max retries)
    """

    class Status(models.TextChoices):
        PENDING_VERIFICATION = "pending_verification", "Pending Verification"
        SCHEDULED = "scheduled", "Scheduled"
        QUEUED = "queued", "Queued for Delivery"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed (will retry)"
        CANCELLED = "cancelled", "Cancelled"
        DEAD_LETTER = "dead_letter", "Dead Letter (max retries exceeded)"

    class Tier(models.TextChoices):
        FREE = "free", "FutureWise (Free)"
        PREMIUM = "premium", "DearTomorrow (Premium)"

    # ── Identity ──────────────────────────────────────────────────────────────
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="future_wise_reminders",
        help_text="Populated only for registered users; null for anonymous.",
    )

    # ── Email & Verification ───────────────────────────────────────────────────
    email = models.EmailField(db_index=True)
    email_verified = models.BooleanField(default=False)
    verification_token = models.CharField(
        max_length=128,
        unique=True,
        db_index=True,
        help_text="URL-safe token sent to the user for one-click verification.",
    )
    verification_token_expires_at = models.DateTimeField()

    # ── Reminder Content ──────────────────────────────────────────────────────
    subject = models.CharField(max_length=250)
    message = models.TextField()
    scheduled_at = models.DateTimeField(db_index=True)
    tier = models.CharField(
        max_length=20,
        choices=Tier.choices,
        default=Tier.FREE,
        db_index=True,
    )

    # ── Delivery State ────────────────────────────────────────────────────────
    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.PENDING_VERIFICATION,
        db_index=True,
    )
    retry_count = models.PositiveSmallIntegerField(default=0)
    last_error = models.TextField(blank=True)
    brevo_message_id = models.CharField(max_length=255, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    # ── Audit ─────────────────────────────────────────────────────────────────
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "scheduled_at"], name="fw_status_sched_idx"),
            models.Index(fields=["email", "status"], name="fw_email_status_idx"),
        ]

    def __str__(self):
        return f"Reminder<{self.email}> at {self.scheduled_at} [{self.status}]"

    # ── Class Helpers ─────────────────────────────────────────────────────────
    @classmethod
    def generate_verification_token(cls) -> str:
        return secrets.token_urlsafe(64)

    @classmethod
    def make_token_expiry(cls):
        return timezone.now() + timezone.timedelta(minutes=VERIFICATION_TOKEN_TTL_MINUTES)

    # ── Instance Helpers ──────────────────────────────────────────────────────
    def is_verification_token_valid(self) -> bool:
        return timezone.now() < self.verification_token_expires_at

    def can_retry(self) -> bool:
        from django.conf import settings

        max_retries = getattr(settings, "FUTUREWAVE_MAX_RETRIES", 3)
        return self.retry_count < max_retries

    @property
    def is_anonymous(self) -> bool:
        return self.user_id is None

    @property
    def brand_name(self) -> str:
        return "DearTomorrow" if self.tier == self.Tier.PREMIUM else "FutureWise"


class ReminderAttachment(models.Model):
    """
    File attachment linked to a reminder.
    Stored in DB (file_data) or S3 depending on FILE_STORAGE_BACKEND setting.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reminder = models.ForeignKey(
        EmailReminder,
        on_delete=models.CASCADE,
        related_name="attachments",
    )
    original_filename = models.CharField(max_length=255)
    # storage_key: logical identifier (S3 key or synthetic UUID path for DB backend)
    storage_key = models.CharField(max_length=512, blank=True, default="")
    # Legacy field name kept for migration compatibility
    s3_key = models.CharField(max_length=512, blank=True, default="")
    content_type = models.CharField(max_length=100)
    size_bytes = models.PositiveIntegerField()
    # DB storage: raw bytes stored here when FILE_STORAGE_BACKEND=db
    file_data = models.BinaryField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"Attachment<{self.original_filename}> → Reminder<{self.reminder_id}>"


class AbuseLog(models.Model):
    """
    Lightweight abuse-prevention audit log.
    Tracks per-email and per-IP action rates for throttle decisions.
    """

    class Action(models.TextChoices):
        CREATE_REMINDER = "create_reminder", "Create Reminder"
        VERIFY_EMAIL = "verify_email", "Verify Email"
        RESEND_VERIFICATION = "resend_verification", "Resend Verification"

    id = models.BigAutoField(primary_key=True)
    email = models.EmailField(db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    action = models.CharField(max_length=50, choices=Action.choices)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["email", "created_at"], name="fw_abuse_email_idx"),
            models.Index(fields=["ip_address", "created_at"], name="fw_abuse_ip_idx"),
        ]

    def __str__(self):
        return f"AbuseLog<{self.ip_address}|{self.email}> {self.action}"
