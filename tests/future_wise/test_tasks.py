"""
Unit tests for FutureWise APScheduler job functions.
(No Celery — tasks are plain Python functions called inline by the scheduler.)
"""

from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.utils import timezone

from apps.future_wise.models import EmailReminder


def make_reminder(**kwargs) -> EmailReminder:
    return EmailReminder.objects.create(
        email=kwargs.pop("email", "user@example.com"),
        email_verified=kwargs.pop("email_verified", True),
        verification_token=EmailReminder.generate_verification_token(),
        verification_token_expires_at=kwargs.pop(
            "verification_token_expires_at", EmailReminder.make_token_expiry()
        ),
        subject="Test Subject",
        message="Hello future me",
        scheduled_at=kwargs.pop("scheduled_at", timezone.now() - timedelta(minutes=1)),
        tier=EmailReminder.Tier.FREE,
        status=kwargs.pop("status", EmailReminder.Status.QUEUED),
        **kwargs,
    )


# ── dispatch_due_reminders ────────────────────────────────────────────────────


class DispatchDueRemindersTest(TestCase):

    @patch("apps.future_wise.tasks._deliver_reminder")
    def test_dispatches_scheduled_due_reminders(self, mock_deliver):
        r1 = make_reminder(status=EmailReminder.Status.SCHEDULED)
        r2 = make_reminder(status=EmailReminder.Status.SCHEDULED)
        # Future reminder — should NOT be dispatched
        make_reminder(
            status=EmailReminder.Status.SCHEDULED,
            scheduled_at=timezone.now() + timedelta(days=1),
        )

        from apps.future_wise.tasks import dispatch_due_reminders

        result = dispatch_due_reminders()

        self.assertEqual(result, 2)
        self.assertEqual(mock_deliver.call_count, 2)

        r1.refresh_from_db()
        r2.refresh_from_db()
        self.assertEqual(r1.status, EmailReminder.Status.QUEUED)
        self.assertEqual(r2.status, EmailReminder.Status.QUEUED)

    @patch("apps.future_wise.tasks._deliver_reminder")
    def test_skips_unverified_reminders(self, mock_deliver):
        make_reminder(status=EmailReminder.Status.SCHEDULED, email_verified=False)

        from apps.future_wise.tasks import dispatch_due_reminders

        result = dispatch_due_reminders()
        self.assertEqual(result, 0)
        mock_deliver.assert_not_called()

    @patch("apps.future_wise.tasks._deliver_reminder")
    def test_no_double_dispatch_on_concurrent_run(self, mock_deliver):
        """Atomic update ensures a reminder is dispatched only once."""
        make_reminder(status=EmailReminder.Status.SCHEDULED)

        from apps.future_wise.tasks import dispatch_due_reminders

        dispatch_due_reminders()
        mock_deliver.reset_mock()
        # Second run — QUEUED reminders are not re-dispatched
        dispatch_due_reminders()
        mock_deliver.assert_not_called()

    @patch("apps.future_wise.tasks._deliver_reminder")
    def test_returns_zero_when_nothing_due(self, mock_deliver):
        from apps.future_wise.tasks import dispatch_due_reminders

        result = dispatch_due_reminders()
        self.assertEqual(result, 0)


# ── expire_unverified_reminders ───────────────────────────────────────────────


class ExpireUnverifiedRemindersTest(TestCase):

    def test_cancels_expired_unverified_reminders(self):
        expired = EmailReminder.objects.create(
            email="u@example.com",
            email_verified=False,
            verification_token=EmailReminder.generate_verification_token(),
            verification_token_expires_at=timezone.now() - timedelta(hours=1),
            subject="Expired",
            message="msg",
            scheduled_at=timezone.now() + timedelta(days=5),
            status=EmailReminder.Status.PENDING_VERIFICATION,
        )
        # Valid (not expired) — should NOT be cancelled
        EmailReminder.objects.create(
            email="v@example.com",
            email_verified=False,
            verification_token=EmailReminder.generate_verification_token(),
            verification_token_expires_at=timezone.now() + timedelta(minutes=20),
            subject="Valid",
            message="msg",
            scheduled_at=timezone.now() + timedelta(days=5),
            status=EmailReminder.Status.PENDING_VERIFICATION,
        )

        from apps.future_wise.tasks import expire_unverified_reminders

        count = expire_unverified_reminders()

        self.assertEqual(count, 1)
        expired.refresh_from_db()
        self.assertEqual(expired.status, EmailReminder.Status.CANCELLED)

    def test_does_not_cancel_valid_tokens(self):
        EmailReminder.objects.create(
            email="valid@example.com",
            email_verified=False,
            verification_token=EmailReminder.generate_verification_token(),
            verification_token_expires_at=timezone.now() + timedelta(hours=1),
            subject="Valid",
            message="msg",
            scheduled_at=timezone.now() + timedelta(days=5),
            status=EmailReminder.Status.PENDING_VERIFICATION,
        )
        from apps.future_wise.tasks import expire_unverified_reminders

        count = expire_unverified_reminders()
        self.assertEqual(count, 0)


# ── _deliver_reminder (inline delivery) ──────────────────────────────────────


class DeliverReminderTest(TestCase):

    @patch("apps.future_wise.tasks.AttachmentStorage")
    @patch("apps.future_wise.tasks.BrevoEmailService")
    def test_successful_delivery_marks_sent(self, mock_brevo_cls, mock_storage_cls):
        mock_brevo_cls.return_value.send_reminder_email.return_value = None
        mock_storage_cls.return_value.download_bytes.return_value = b"bytes"

        reminder = make_reminder()
        from apps.future_wise.tasks import _deliver_reminder

        _deliver_reminder(str(reminder.id))

        reminder.refresh_from_db()
        self.assertEqual(reminder.status, EmailReminder.Status.SENT)
        self.assertIsNotNone(reminder.sent_at)

    @patch("apps.future_wise.tasks.AttachmentStorage")
    @patch("apps.future_wise.tasks.BrevoEmailService")
    def test_delivery_failure_resets_to_scheduled_for_retry(self, mock_brevo_cls, mock_storage_cls):
        from apps.future_wise.email_service import BrevoDeliveryError

        mock_brevo_cls.return_value.send_reminder_email.side_effect = BrevoDeliveryError("SMTP down")
        mock_storage_cls.return_value.download_bytes.return_value = b""

        reminder = make_reminder()
        from apps.future_wise.tasks import _deliver_reminder

        _deliver_reminder(str(reminder.id))

        reminder.refresh_from_db()
        self.assertEqual(reminder.status, EmailReminder.Status.SCHEDULED)
        self.assertEqual(reminder.retry_count, 1)
        self.assertIn("SMTP down", reminder.last_error)

    @patch("apps.future_wise.tasks.AttachmentStorage")
    @patch("apps.future_wise.tasks.BrevoEmailService")
    def test_dead_letter_after_max_retries(self, mock_brevo_cls, mock_storage_cls):
        from apps.future_wise.email_service import BrevoDeliveryError

        mock_brevo_cls.return_value.send_reminder_email.side_effect = BrevoDeliveryError("still down")
        mock_storage_cls.return_value.download_bytes.return_value = b""

        reminder = make_reminder()
        reminder.retry_count = 3  # already at max
        reminder.save()

        from apps.future_wise.tasks import _deliver_reminder

        _deliver_reminder(str(reminder.id))

        reminder.refresh_from_db()
        self.assertEqual(reminder.status, EmailReminder.Status.DEAD_LETTER)

    def test_skips_non_queued_reminder(self):
        """Reminder in SENT status should be silently skipped."""
        reminder = make_reminder(status=EmailReminder.Status.SENT)
        from apps.future_wise.tasks import _deliver_reminder

        _deliver_reminder(str(reminder.id))
        reminder.refresh_from_db()
        self.assertEqual(reminder.status, EmailReminder.Status.SENT)

    def test_skips_missing_reminder(self):
        """Non-existent reminder should not raise."""
        from apps.future_wise.tasks import _deliver_reminder

        _deliver_reminder("00000000-0000-0000-0000-000000000000")  # should not raise



class CleanupUnverifiedRemindersTest(TestCase):
    """Tests for cleanup_unverified_reminders() task and management command."""

    def _make_old_pending(self, user=None) -> EmailReminder:
        """Create an anonymous PENDING_VERIFICATION reminder created 25 h ago."""
        reminder = make_reminder(
            user=user,
            email_verified=False,
            status=EmailReminder.Status.PENDING_VERIFICATION,
        )
        # Use queryset update to bypass auto_now fields
        EmailReminder.objects.filter(pk=reminder.pk).update(
            created_at=timezone.now() - timedelta(hours=25)
        )
        reminder.refresh_from_db()
        return reminder

    def test_deletes_old_anonymous_pending_reminders(self):
        reminder = self._make_old_pending()
        from apps.future_wise.tasks import cleanup_unverified_reminders
        count = cleanup_unverified_reminders()
        self.assertEqual(count, 1)
        self.assertFalse(EmailReminder.objects.filter(pk=reminder.pk).exists())

    def test_does_not_delete_recent_anonymous_pending(self):
        reminder = make_reminder(
            email_verified=False,
            status=EmailReminder.Status.PENDING_VERIFICATION,
        )
        from apps.future_wise.tasks import cleanup_unverified_reminders
        count = cleanup_unverified_reminders()
        self.assertEqual(count, 0)
        self.assertTrue(EmailReminder.objects.filter(pk=reminder.pk).exists())

    def test_does_not_delete_authenticated_user_pending(self):
        """PENDING_VERIFICATION reminders belonging to a real user must not be deleted."""
        from django.contrib.auth import get_user_model
        User = get_user_model()
        user = User.objects.create_user("verifyuser", "verifyuser@example.com", "pass")
        reminder = self._make_old_pending(user=user)
        from apps.future_wise.tasks import cleanup_unverified_reminders
        count = cleanup_unverified_reminders()
        self.assertEqual(count, 0)
        self.assertTrue(EmailReminder.objects.filter(pk=reminder.pk).exists())

    def test_does_not_delete_non_pending_status(self):
        """Old anonymous reminders in CANCELLED or SCHEDULED status must not be deleted."""
        cancelled = make_reminder(
            email_verified=False,
            status=EmailReminder.Status.CANCELLED,
        )
        EmailReminder.objects.filter(pk=cancelled.pk).update(
            created_at=timezone.now() - timedelta(hours=25)
        )
        from apps.future_wise.tasks import cleanup_unverified_reminders
        count = cleanup_unverified_reminders()
        self.assertEqual(count, 0)
        self.assertTrue(EmailReminder.objects.filter(pk=cancelled.pk).exists())

    def test_management_command_output(self):
        """Management command should report the number of deleted reminders."""
        from io import StringIO
        from django.core.management import call_command
        self._make_old_pending()
        out = StringIO()
        call_command("cleanup_unverified_reminders", stdout=out)
        output = out.getvalue()
        self.assertIn("1", output)
        self.assertIn("Deleted", output)

    def test_management_command_no_reminders(self):
        """Management command should report nothing to delete when clean."""
        from io import StringIO
        from django.core.management import call_command
        out = StringIO()
        call_command("cleanup_unverified_reminders", stdout=out)
        self.assertIn("No expired", out.getvalue())
