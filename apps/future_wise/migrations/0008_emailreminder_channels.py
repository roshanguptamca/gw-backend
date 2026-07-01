from django.db import migrations, models


def populate_channels(apps, schema_editor):
    EmailReminder = apps.get_model("future_wise", "EmailReminder")
    for reminder in EmailReminder.objects.only("id", "channels_requested").iterator():
        channels = [
            channel.strip()
            for channel in (reminder.channels_requested or "email").split(",")
            if channel.strip()
        ]
        EmailReminder.objects.filter(pk=reminder.pk).update(channels=channels or ["email"])


class Migration(migrations.Migration):
    dependencies = [
        ("future_wise", "0007_email_blank_for_non_email_channels"),
    ]

    operations = [
        migrations.AddField(
            model_name="emailreminder",
            name="channels",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text=(
                    "Canonical list of requested channel codes. "
                    "Falls back to channels_requested for legacy rows."
                ),
            ),
        ),
        migrations.RunPython(populate_channels, migrations.RunPython.noop),
    ]
