"""
Initial migration for apps.future_wise.
"""
import django.db.models.deletion
import django.utils.timezone
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="EmailReminder",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        help_text="Populated only for registered users; null for anonymous.",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="future_wise_reminders",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                ("email", models.EmailField(db_index=True, max_length=254)),
                ("email_verified", models.BooleanField(default=False)),
                (
                    "verification_token",
                    models.CharField(
                        db_index=True,
                        help_text="URL-safe token sent to the user for one-click verification.",
                        max_length=128,
                        unique=True,
                    ),
                ),
                ("verification_token_expires_at", models.DateTimeField()),
                ("subject", models.CharField(max_length=250)),
                ("message", models.TextField()),
                ("scheduled_at", models.DateTimeField(db_index=True)),
                (
                    "tier",
                    models.CharField(
                        choices=[("free", "FutureWise (Free)"), ("premium", "DearTomorrow (Premium)")],
                        db_index=True,
                        default="free",
                        max_length=20,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending_verification", "Pending Verification"),
                            ("scheduled", "Scheduled"),
                            ("queued", "Queued for Delivery"),
                            ("sent", "Sent"),
                            ("failed", "Failed (will retry)"),
                            ("cancelled", "Cancelled"),
                            ("dead_letter", "Dead Letter (max retries exceeded)"),
                        ],
                        db_index=True,
                        default="pending_verification",
                        max_length=30,
                    ),
                ),
                ("retry_count", models.PositiveSmallIntegerField(default=0)),
                ("last_error", models.TextField(blank=True)),
                ("brevo_message_id", models.CharField(blank=True, max_length=255)),
                ("sent_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="ReminderAttachment",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                (
                    "reminder",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="attachments",
                        to="future_wise.emailreminder",
                    ),
                ),
                ("original_filename", models.CharField(max_length=255)),
                ("s3_key", models.CharField(max_length=512)),
                ("content_type", models.CharField(max_length=100)),
                ("size_bytes", models.PositiveIntegerField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "ordering": ["created_at"],
            },
        ),
        migrations.CreateModel(
            name="AbuseLog",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("email", models.EmailField(db_index=True, max_length=254)),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
                (
                    "action",
                    models.CharField(
                        choices=[
                            ("create_reminder", "Create Reminder"),
                            ("verify_email", "Verify Email"),
                            ("resend_verification", "Resend Verification"),
                        ],
                        max_length=50,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="emailreminder",
            index=models.Index(fields=["status", "scheduled_at"], name="fw_status_sched_idx"),
        ),
        migrations.AddIndex(
            model_name="emailreminder",
            index=models.Index(fields=["email", "status"], name="fw_email_status_idx"),
        ),
        migrations.AddIndex(
            model_name="abuselog",
            index=models.Index(fields=["email", "created_at"], name="fw_abuse_email_idx"),
        ),
        migrations.AddIndex(
            model_name="abuselog",
            index=models.Index(fields=["ip_address", "created_at"], name="fw_abuse_ip_idx"),
        ),
    ]
