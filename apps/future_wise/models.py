"""
FutureWise / DearTomorrow — Reminder Models

Supports both anonymous verified users (email-OTP flow) and registered
account users. Uses a UUID primary key for privacy.

Multi-channel delivery (email, SMS, voice, WhatsApp, Telegram) is handled
by the ReminderDispatcher + IReminderProvider pattern. New models:
  - ReminderChannel              — lookup / feature-flag table per channel
  - UserNotificationPreference   — per-user opt-in and contact details
  - ReminderDeliveryLog          — immutable audit log per delivery attempt
"""

import secrets
import uuid

from django.contrib.auth import get_user_model
from django.db import models
from django.utils import timezone

from .fields import EncryptedTextField

User = get_user_model()

# Kept for backward-compat reference only; actual window is EMAIL_VERIFICATION_EXPIRY_HOURS from settings
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

    class LetterType(models.TextChoices):
        FUTURE_SELF = "future_self", "Letter to Future Self"
        MILESTONE = "milestone", "Open When… (Milestone)"
        GRIEF = "grief", "In Memory — Grief Letter"
        FORGIVENESS = "forgiveness", "Forgiveness Letter"
        GRATITUDE = "gratitude", "Gratitude Letter"
        GENERAL_REMINDER = "general_reminder", "General Reminder"
        APPOINTMENT_REMINDER = "appointment_reminder", "Appointment Reminder"
        MEDICINE_REMINDER = "medicine_reminder", "Medicine Reminder"
        BILL_PAYMENT_REMINDER = "bill_payment_reminder", "Bill Payment Reminder"
        BIRTHDAY_WISH = "birthday_wish", "Birthday Wish"
        ANNIVERSARY_WISH = "anniversary_wish", "Anniversary Wish"
        WEDDING_ANNIVERSARY_WISH = "wedding_anniversary_wish", "Wedding Anniversary Wish"
        FESTIVAL_WISH = "festival_wish", "Festival Wish"
        HOLIDAY_GREETING = "holiday_greeting", "Holiday Greeting"
        THANK_YOU_MESSAGE = "thank_you_message", "Thank You Message"
        CONGRATULATIONS_MESSAGE = "congratulations_message", "Congratulations Message"
        GET_WELL_SOON_MESSAGE = "get_well_soon_message", "Get Well Soon Message"
        MEETING_REMINDER = "meeting_reminder", "Meeting Reminder"
        SCHOOL_EVENT_REMINDER = "school_event_reminder", "School Event Reminder"
        TRAVEL_REMINDER = "travel_reminder", "Travel Reminder"
        SUBSCRIPTION_RENEWAL_REMINDER = "subscription_renewal_reminder", "Subscription Renewal Reminder"
        CUSTOM_MESSAGE = "custom_message", "Custom Message"

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
    # blank=True / default="" allows non-email delivery methods (SMS, WhatsApp, etc.)
    # to omit the email address without breaking the NOT NULL DB constraint.
    email = models.EmailField(blank=True, default="", db_index=True)
    email_verified = models.BooleanField(default=False)
    verification_token = models.CharField(
        max_length=128,
        unique=True,
        db_index=True,
        help_text="URL-safe token sent to the user for one-click verification.",
    )
    verification_token_expires_at = models.DateTimeField()

    # ── Reminder Content ──────────────────────────────────────────────────────
    # subject and message are stored encrypted (AES-256-GCM) via EncryptedTextField.
    # The plaintext max_length=250 for subject is enforced in the serializer layer.
    subject = EncryptedTextField()
    message = EncryptedTextField()
    scheduled_at = models.DateTimeField(db_index=True)
    tier = models.CharField(
        max_length=20,
        choices=Tier.choices,
        default=Tier.FREE,
        db_index=True,
    )
    letter_type = models.CharField(
        max_length=40,
        choices=LetterType.choices,
        default=LetterType.FUTURE_SELF,
        db_index=True,
    )

    # ── Multi-Channel Fields ──────────────────────────────────────────────────
    phone_number = models.CharField(
        max_length=20,
        blank=True,
        default="",
        help_text="E.164 format e.g. +447700900123. Required for SMS/Voice/WhatsApp channels.",
    )
    telegram_chat_id = models.CharField(
        max_length=50,
        blank=True,
        default="",
        help_text="Obtained when user sends /start to the Telegram bot.",
    )
    channels_requested = models.CharField(
        max_length=200,
        default="email",
        help_text="Comma-separated channel codes e.g. 'email,sms,telegram'.",
    )
    channels = models.JSONField(
        default=list,
        blank=True,
        help_text="Canonical list of requested channel codes. Falls back to channels_requested for legacy rows.",
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
        from django.conf import settings

        hours = getattr(settings, "EMAIL_VERIFICATION_EXPIRY_HOURS", 24)
        return timezone.now() + timezone.timedelta(hours=hours)

    @classmethod
    def get_letter_type_metadata(cls) -> dict[str, dict[str, str]]:
        descriptions = {
            cls.LetterType.FUTURE_SELF: "Write a thoughtful note for your future self to revisit later.",
            cls.LetterType.MILESTONE: "Prepare a message to open when a life milestone or goal is reached.",
            cls.LetterType.GRIEF: "Share comfort, remembrance, or support for a difficult loss.",
            cls.LetterType.FORGIVENESS: "Express healing, understanding, or a sincere apology.",
            cls.LetterType.GRATITUDE: "Capture appreciation for someone who has made a difference.",
            cls.LetterType.GENERAL_REMINDER: "Create a flexible reminder for any personal or practical task.",
            cls.LetterType.APPOINTMENT_REMINDER: "Remind someone about an upcoming appointment and key details.",
            cls.LetterType.MEDICINE_REMINDER: "Prompt a medicine dose with a calm, supportive tone.",
            cls.LetterType.BILL_PAYMENT_REMINDER: "Nudge someone to pay a bill before the due date.",
            cls.LetterType.BIRTHDAY_WISH: "Send a warm birthday greeting with a personal touch.",
            cls.LetterType.ANNIVERSARY_WISH: "Celebrate a meaningful anniversary with a heartfelt message.",
            cls.LetterType.WEDDING_ANNIVERSARY_WISH: "Mark a wedding anniversary with loving, celebratory words.",
            cls.LetterType.FESTIVAL_WISH: "Share festive wishes for a cultural or community celebration.",
            cls.LetterType.HOLIDAY_GREETING: "Send a cheerful holiday greeting for a seasonal occasion.",
            cls.LetterType.THANK_YOU_MESSAGE: "Craft a sincere thank-you note for help, kindness, or support.",
            cls.LetterType.CONGRATULATIONS_MESSAGE: "Celebrate an achievement with an uplifting congratulations message.",
            cls.LetterType.GET_WELL_SOON_MESSAGE: "Offer comfort and encouragement during recovery.",
            cls.LetterType.MEETING_REMINDER: "Remind someone about a meeting, agenda, or next steps.",
            cls.LetterType.SCHOOL_EVENT_REMINDER: "Highlight an upcoming school event for students or parents.",
            cls.LetterType.TRAVEL_REMINDER: "Share travel timing, packing, or itinerary reminders.",
            cls.LetterType.SUBSCRIPTION_RENEWAL_REMINDER: "Warn about an upcoming subscription renewal or expiry.",
            cls.LetterType.CUSTOM_MESSAGE: "Generate a message for a unique situation in your own style.",
            "": "Leave the type blank when you want a fully custom reminder prompt.",
        }
        return {
            choice.value: {
                "value": choice.value,
                "label": str(choice.label),
                "description": descriptions.get(choice.value, ""),
            }
            for choice in cls.LetterType
        } | {"": {"value": "", "label": "No specific type", "description": descriptions[""]}}

    @classmethod
    def get_letter_type_options(cls) -> list[dict[str, str]]:
        metadata = cls.get_letter_type_metadata()
        return [metadata[choice.value] for choice in cls.LetterType]

    # ── Instance Helpers ──────────────────────────────────────────────────────
    def is_verification_token_valid(self) -> bool:
        return timezone.now() < self.verification_token_expires_at

    def can_retry(self) -> bool:
        from django.conf import settings

        max_retries = getattr(settings, "FUTUREWAVE_MAX_RETRIES", 3)
        return self.retry_count < max_retries

    @property
    def selected_channels(self) -> list[str]:
        if isinstance(self.channels, list) and self.channels:
            return [str(channel).strip() for channel in self.channels if str(channel).strip()]
        return [channel.strip() for channel in (self.channels_requested or "email").split(",") if channel.strip()]

    @property
    def is_anonymous(self) -> bool:
        return self.user_id is None

    @property
    def brand_name(self) -> str:
        return "DearTomorrow" if self.tier == self.Tier.PREMIUM else "FutureWise"

    @property
    def letter_type_description(self) -> str:
        return self.get_letter_type_metadata().get(self.letter_type or "", {}).get("description", "")


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


# ── Multi-Channel Reminder Models ─────────────────────────────────────────────


class ReminderChannel(models.Model):
    """
    Lookup / feature-flag table for each delivery channel.
    Seed via: python manage.py seed_channels
    """

    code = models.CharField(max_length=20, unique=True, db_index=True)
    display_name = models.CharField(max_length=50)
    is_active = models.BooleanField(default=True)
    provider_class = models.CharField(
        max_length=200,
        help_text="Dotted Python path to the IReminderProvider subclass.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["code"]

    def __str__(self):
        flag = "✅" if self.is_active else "❌"
        return f"{flag} {self.display_name} ({self.code})"


class UserNotificationPreference(models.Model):
    """
    Per-user opt-in state and contact details for each delivery channel.
    Anonymous users (user=None) store preferences keyed by email only.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="notification_preferences",
    )
    email = models.EmailField(db_index=True)
    channel = models.ForeignKey(
        ReminderChannel,
        on_delete=models.PROTECT,
        related_name="user_preferences",
    )
    is_opted_in = models.BooleanField(default=False)
    phone_number = models.CharField(
        max_length=20,
        blank=True,
        default="",
        help_text="E.164 format e.g. +447700900123",
    )
    telegram_chat_id = models.CharField(max_length=50, blank=True, default="")
    whatsapp_opted_in = models.BooleanField(
        default=False,
        help_text="True only after user sends the Twilio Sandbox join phrase.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["email", "channel__code"]
        indexes = [
            models.Index(fields=["email", "channel"], name="fw_notifpref_email_ch_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["email", "channel"],
                name="fw_notifpref_email_channel_unique",
            ),
        ]

    def __str__(self):
        opted = "opted-in" if self.is_opted_in else "opted-out"
        return f"NotifPref<{self.email} | {self.channel.code} | {opted}>"


class ReminderDeliveryLog(models.Model):
    """
    Immutable audit log — one row per delivery attempt per channel.
    Never deleted; accumulates a full delivery history for each reminder.
    """

    class DeliveryStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"
        SKIPPED = "skipped", "Skipped (channel unavailable or not requested)"

    reminder = models.ForeignKey(
        EmailReminder,
        on_delete=models.CASCADE,
        related_name="delivery_logs",
    )
    channel = models.ForeignKey(
        ReminderChannel,
        on_delete=models.PROTECT,
        related_name="delivery_logs",
    )
    attempt_number = models.PositiveSmallIntegerField(default=1)
    status = models.CharField(
        max_length=20,
        choices=DeliveryStatus.choices,
        default=DeliveryStatus.PENDING,
        db_index=True,
    )
    provider_message_id = models.CharField(max_length=255, blank=True)
    provider_response = models.TextField(blank=True)
    error_message = models.TextField(blank=True)
    attempted_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-attempted_at"]
        indexes = [
            models.Index(
                fields=["reminder", "channel", "attempt_number"],
                name="fw_log_reminder_ch_idx",
            ),
            models.Index(fields=["reminder", "status"], name="fw_log_reminder_status_idx"),
        ]

    def __str__(self):
        return (
            f"DeliveryLog<reminder={self.reminder_id} "
            f"channel={self.channel.code} "
            f"attempt={self.attempt_number} "
            f"status={self.status}>"
        )
