"""
Unit tests for FutureWise models.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.future_wise.models import AbuseLog, EmailReminder, ReminderAttachment

User = get_user_model()


def make_reminder(**kwargs) -> EmailReminder:
    defaults = dict(
        email="test@example.com",
        email_verified=True,
        verification_token=EmailReminder.generate_verification_token(),
        verification_token_expires_at=EmailReminder.make_token_expiry(),
        subject="Hello future me",
        message="Hope you are doing great!",
        scheduled_at=timezone.now() + timedelta(days=30),
        tier=EmailReminder.Tier.FREE,
        status=EmailReminder.Status.SCHEDULED,
    )
    defaults.update(kwargs)
    return EmailReminder.objects.create(**defaults)


class EmailReminderModelTest(TestCase):

    def test_create_reminder_defaults(self):
        reminder = make_reminder()
        self.assertEqual(reminder.status, EmailReminder.Status.SCHEDULED)
        self.assertEqual(reminder.tier, EmailReminder.Tier.FREE)
        self.assertEqual(reminder.retry_count, 0)
        self.assertTrue(reminder.email_verified)

    def test_str_representation(self):
        reminder = make_reminder()
        self.assertIn("test@example.com", str(reminder))
        self.assertIn("scheduled", str(reminder))

    def test_brand_name_free(self):
        reminder = make_reminder(tier=EmailReminder.Tier.FREE)
        self.assertEqual(reminder.brand_name, "FutureWise")

    def test_brand_name_premium(self):
        reminder = make_reminder(tier=EmailReminder.Tier.PREMIUM)
        self.assertEqual(reminder.brand_name, "DearTomorrow")

    def test_is_anonymous_no_user(self):
        reminder = make_reminder()
        self.assertTrue(reminder.is_anonymous)

    def test_is_anonymous_with_user(self):
        user = User.objects.create_user("testuser", "u@example.com", "pass")
        reminder = make_reminder(user=user)
        self.assertFalse(reminder.is_anonymous)

    def test_verification_token_valid(self):
        reminder = make_reminder(verification_token_expires_at=timezone.now() + timedelta(minutes=29))
        self.assertTrue(reminder.is_verification_token_valid())

    def test_verification_token_expired(self):
        reminder = make_reminder(verification_token_expires_at=timezone.now() - timedelta(seconds=1))
        self.assertFalse(reminder.is_verification_token_valid())

    def test_can_retry_within_limit(self):
        reminder = make_reminder()
        reminder.retry_count = 2
        self.assertTrue(reminder.can_retry())

    def test_can_retry_exceeded(self):
        reminder = make_reminder()
        reminder.retry_count = 3
        self.assertFalse(reminder.can_retry())

    def test_generate_verification_token_unique(self):
        tokens = {EmailReminder.generate_verification_token() for _ in range(100)}
        self.assertEqual(len(tokens), 100)

    def test_uuid_primary_key(self):
        reminder = make_reminder()
        import uuid

        self.assertIsInstance(reminder.id, uuid.UUID)

    def test_status_choices(self):
        statuses = [s.value for s in EmailReminder.Status]
        self.assertIn("pending_verification", statuses)
        self.assertIn("dead_letter", statuses)
        self.assertIn("sent", statuses)


class ReminderAttachmentModelTest(TestCase):

    def setUp(self):
        self.reminder = make_reminder()

    def test_create_attachment(self):
        att = ReminderAttachment.objects.create(
            reminder=self.reminder,
            original_filename="notes.pdf",
            s3_key="future_wise/attachments/abc123.pdf",
            content_type="application/pdf",
            size_bytes=1024,
        )
        self.assertEqual(att.reminder, self.reminder)
        self.assertEqual(att.original_filename, "notes.pdf")

    def test_attachment_cascade_delete(self):
        ReminderAttachment.objects.create(
            reminder=self.reminder,
            original_filename="photo.jpg",
            s3_key="future_wise/attachments/xyz.jpg",
            content_type="image/jpeg",
            size_bytes=2048,
        )
        self.reminder.delete()
        self.assertEqual(ReminderAttachment.objects.count(), 0)

    def test_str_representation(self):
        att = ReminderAttachment.objects.create(
            reminder=self.reminder,
            original_filename="doc.txt",
            s3_key="future_wise/attachments/doc.txt",
            content_type="text/plain",
            size_bytes=512,
        )
        self.assertIn("doc.txt", str(att))


class AbuseLogModelTest(TestCase):

    def test_create_abuse_log(self):
        log = AbuseLog.objects.create(
            email="spammer@bad.com",
            ip_address="1.2.3.4",
            action=AbuseLog.Action.CREATE_REMINDER,
        )
        self.assertEqual(log.action, "create_reminder")
        self.assertEqual(log.ip_address, "1.2.3.4")

    def test_str_representation(self):
        log = AbuseLog.objects.create(
            email="spam@bad.com",
            ip_address="10.0.0.1",
            action=AbuseLog.Action.VERIFY_EMAIL,
        )
        self.assertIn("spam@bad.com", str(log))
