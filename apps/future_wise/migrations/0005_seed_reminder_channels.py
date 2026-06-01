# Data migration: seed the ReminderChannel reference table.
#
# This ensures the email (and other) channels exist after the multi-channel
# migration (0004) so that ReminderDispatcher can route deliveries correctly.
# Without at least an active "email" row, the dispatcher loop is a no-op and
# no emails are sent.
#
# Safe to run repeatedly: uses update_or_create (idempotent).

from django.db import migrations

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


def seed_channels(apps, schema_editor):
    ReminderChannel = apps.get_model("future_wise", "ReminderChannel")
    for data in CHANNELS:
        ReminderChannel.objects.update_or_create(
            code=data["code"],
            defaults={
                "display_name": data["display_name"],
                "provider_class": data["provider_class"],
                "is_active": data["is_active"],
            },
        )


def unseed_channels(apps, schema_editor):
    ReminderChannel = apps.get_model("future_wise", "ReminderChannel")
    ReminderChannel.objects.filter(code__in=[c["code"] for c in CHANNELS]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("future_wise", "0004_multi_channel_reminders"),
    ]

    operations = [
        migrations.RunPython(seed_channels, reverse_code=unseed_channels),
    ]
