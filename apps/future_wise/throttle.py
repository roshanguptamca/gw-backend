"""
Custom DRF throttle classes for FutureWise abuse prevention.
These extend DRF's built-in throttling and also log to AbuseLog.
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle

logger = logging.getLogger(__name__)

# ── Per-email limits (applied independent of IP) ──────────────────────────────


def _count_recent_actions(email: str, action: str, window_minutes: int) -> int:
    """Count AbuseLog entries for an email/action within the time window."""
    from .models import AbuseLog

    since = timezone.now() - timedelta(minutes=window_minutes)
    return AbuseLog.objects.filter(email=email, action=action, created_at__gte=since).count()


def check_email_rate(email: str, action: str, max_count: int, window_minutes: int) -> bool:
    """Return True if the email is within rate limits, False if throttled."""
    count = _count_recent_actions(email, action, window_minutes)
    return count < max_count


def log_action(email: str, ip_address, action: str) -> None:
    """Record an action to the AbuseLog for rate-limit tracking."""
    from .models import AbuseLog

    try:
        AbuseLog.objects.create(email=email, ip_address=ip_address, action=action)
    except Exception as exc:  # pragma: no cover
        logger.warning("Failed to write AbuseLog: %s", exc)


def check_daily_reminder_limit(email: str, user=None) -> bool:
    """
    Return True (allowed) if the email/user is under the daily reminder limit.

    Rules:
    - Superusers have no limit.
    - All others are limited to EMAIL_REMINDER_FREE_DAILY_LIMIT per 24-hour rolling window.
    """
    if user and getattr(user, "is_authenticated", False) and getattr(user, "is_superuser", False):
        return True

    limit = getattr(settings, "EMAIL_REMINDER_FREE_DAILY_LIMIT", 3)
    return check_email_rate(email, "create_reminder", max_count=limit, window_minutes=24 * 60)


class CreateReminderAnonThrottle(AnonRateThrottle):
    """
    Limit anonymous reminder creation by IP.
    Default: 5 requests per hour.
    Override FUTUREWAVE_ANON_CREATE_RATE in settings.
    """

    scope = "futurewave_anon_create"

    def get_rate(self):
        return getattr(settings, "FUTUREWAVE_ANON_CREATE_RATE", "5/hour")


class CreateReminderUserThrottle(UserRateThrottle):
    """
    Limit authenticated reminder creation.
    Default: 20 requests per hour.
    Override FUTUREWAVE_USER_CREATE_RATE in settings.
    """

    scope = "futurewave_user_create"

    def get_rate(self):
        return getattr(settings, "FUTUREWAVE_USER_CREATE_RATE", "20/hour")


class VerifyEmailThrottle(AnonRateThrottle):
    """
    Limit verification-email verification attempts.
    Default: 10 per hour per IP.
    """

    scope = "futurewave_verify"

    def get_rate(self):
        return getattr(settings, "FUTUREWAVE_VERIFY_RATE", "10/hour")
