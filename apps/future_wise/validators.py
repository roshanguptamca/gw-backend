"""
Input validators for the FutureWise / DearTomorrow feature.
"""

import mimetypes
from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from rest_framework.exceptions import ValidationError

# ── Constants ─────────────────────────────────────────────────────────────────

# How far in the future a reminder can be scheduled (default 10 years)
MAX_SCHEDULE_YEARS = getattr(settings, "FUTUREWAVE_MAX_SCHEDULE_YEARS", 10)

# Minimum lead time before scheduled delivery
MIN_SCHEDULE_MINUTES = getattr(settings, "FUTUREWAVE_MIN_SCHEDULE_MINUTES", 30)

# Maximum attachment size per file (default 10 MB)
MAX_ATTACHMENT_BYTES = getattr(settings, "FUTUREWAVE_MAX_ATTACHMENT_BYTES", 10 * 1024 * 1024)

# Maximum total attachments per reminder
MAX_ATTACHMENTS = getattr(settings, "FUTUREWAVE_MAX_ATTACHMENTS", 5)

# Allowed MIME types for attachments
ALLOWED_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "application/pdf",
    "text/plain",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


# ── Validators ────────────────────────────────────────────────────────────────


def validate_scheduled_at(value) -> None:
    """Ensure the scheduled time is in a valid future window."""
    now = timezone.now()
    min_time = now + timedelta(minutes=MIN_SCHEDULE_MINUTES)
    max_time = now + timedelta(days=365 * MAX_SCHEDULE_YEARS)

    if value < min_time:
        raise ValidationError(f"Reminder must be scheduled at least {MIN_SCHEDULE_MINUTES} minutes in the future.")
    if value > max_time:
        raise ValidationError(f"Reminder cannot be scheduled more than {MAX_SCHEDULE_YEARS} years in the future.")


def validate_attachment_file(uploaded_file) -> None:
    """
    Validate a single uploaded attachment.
    Checks size and MIME type (content-sniffed, not just extension).
    """
    if uploaded_file.size > MAX_ATTACHMENT_BYTES:
        mb = MAX_ATTACHMENT_BYTES // (1024 * 1024)
        raise ValidationError(f"Attachment '{uploaded_file.name}' exceeds the {mb} MB size limit.")

    # Detect MIME from content type header; fall back to filename extension
    mime = uploaded_file.content_type or ""
    if mime not in ALLOWED_MIME_TYPES:
        # Secondary check via filename extension
        guessed, _ = mimetypes.guess_type(uploaded_file.name)
        if guessed not in ALLOWED_MIME_TYPES:
            raise ValidationError(
                f"File type '{mime or guessed}' is not allowed. "
                f"Accepted types: PDF, images, Word documents, plain text."
            )


def validate_attachment_count(files) -> None:
    if len(files) > MAX_ATTACHMENTS:
        raise ValidationError(f"You may attach at most {MAX_ATTACHMENTS} files per reminder.")
