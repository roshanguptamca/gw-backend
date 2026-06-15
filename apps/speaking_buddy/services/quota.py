from django.db import transaction
from django.db.models import F

from apps.speaking_buddy.models import BuddySession, BuddyUsageQuota


def get_usage_quota(user):
    quota, _ = BuddyUsageQuota.objects.get_or_create(user=user)
    return quota


def get_remaining_conversations(user):
    quota = get_usage_quota(user)
    return max(quota.free_conversation_limit - quota.conversations_used, 0)


def can_start_conversation(user):
    return get_remaining_conversations(user) > 0


def increment_conversation_usage(user, session):
    if not session or session.usage_counted or session.status != "ended":
        return get_usage_quota(user), False
    if not session.messages.filter(role="user").exists():
        return get_usage_quota(user), False

    with transaction.atomic():
        quota = BuddyUsageQuota.objects.select_for_update().get_or_create(user=user)[0]
        session_updated = BuddySession.objects.filter(id=session.id, usage_counted=False).update(usage_counted=True)
        if not session_updated:
            quota.refresh_from_db()
            return quota, False
        BuddyUsageQuota.objects.filter(id=quota.id).update(conversations_used=F("conversations_used") + 1)
        quota.refresh_from_db()
        return quota, True
