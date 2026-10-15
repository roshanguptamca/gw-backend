"""Remove expired, unused checkout reviews containing duplicate guest contact data."""

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.marketplace.models import AgentCheckout


class Command(BaseCommand):
    help = "Delete expired AI checkout drafts; retain consumed tokens for idempotent retries."

    def handle(self, *args, **options):
        count, _ = AgentCheckout.objects.filter(order__isnull=True, expires_at__lte=timezone.now()).delete()
        self.stdout.write(f"Removed {count} expired checkout drafts.")
