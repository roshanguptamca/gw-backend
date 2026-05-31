"""
Management command: python manage.py seed_channels

Seeds the ReminderChannel reference table with all supported delivery
channels. Safe to run repeatedly (upsert behaviour via update_or_create).

Run this after migrations on every new environment:
    python manage.py migrate
    python manage.py seed_channels
"""

from django.core.management.base import BaseCommand

from apps.future_wise.models import ReminderChannel

CHANNELS = [
    {
        "code": "email",
        "display_name": "Email",
        "provider_class": "apps.future_wise.providers.email_provider.EmailReminderProvider",
        "is_active": True,
    },
    {
        "code": "sms",
        "display_name": "SMS",
        "provider_class": "apps.future_wise.providers.sms_provider.SmsReminderProvider",
        "is_active": True,
    },
    {
        "code": "voice",
        "display_name": "Voice Call",
        "provider_class": "apps.future_wise.providers.voice_provider.VoiceCallReminderProvider",
        "is_active": True,
    },
    {
        "code": "whatsapp",
        "display_name": "WhatsApp",
        "provider_class": "apps.future_wise.providers.whatsapp_provider.WhatsAppReminderProvider",
        "is_active": True,
    },
    {
        "code": "telegram",
        "display_name": "Telegram",
        "provider_class": "apps.future_wise.providers.telegram_provider.TelegramReminderProvider",
        "is_active": True,
    },
]


class Command(BaseCommand):
    help = "Seed ReminderChannel reference data (idempotent — safe to run repeatedly)"

    def handle(self, *args, **options):
        self.stdout.write("Seeding ReminderChannel table...")
        for data in CHANNELS:
            code = data["code"]
            obj, created = ReminderChannel.objects.update_or_create(
                code=code,
                defaults={
                    "display_name": data["display_name"],
                    "provider_class": data["provider_class"],
                    "is_active": data["is_active"],
                },
            )
            verb = "Created" if created else "Updated"
            self.stdout.write(self.style.SUCCESS(f"  {verb}: {obj}"))

        total = ReminderChannel.objects.count()
        self.stdout.write(self.style.SUCCESS(f"\n✅ Done. {total} channel(s) in database."))
