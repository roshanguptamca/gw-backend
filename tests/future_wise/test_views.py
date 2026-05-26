"""
API integration tests for FutureWise views.
"""

import uuid
from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.future_wise.models import AbuseLog, EmailReminder, ReminderAttachment

User = get_user_model()

FUTURE = timezone.now() + timedelta(days=30)
PAST_FUTURE = timezone.now() + timedelta(minutes=20)  # too soon


def make_reminder(user=None, email="owner@example.com", **kwargs) -> EmailReminder:
    return EmailReminder.objects.create(
        user=user,
        email=email,
        email_verified=kwargs.pop("email_verified", True),
        verification_token=EmailReminder.generate_verification_token(),
        verification_token_expires_at=kwargs.pop("verification_token_expires_at", EmailReminder.make_token_expiry()),
        subject=kwargs.pop("subject", "Test subject"),
        message=kwargs.pop("message", "Hello future me"),
        scheduled_at=kwargs.pop("scheduled_at", FUTURE),
        tier=kwargs.pop("tier", EmailReminder.Tier.FREE),
        status=kwargs.pop("status", EmailReminder.Status.SCHEDULED),
        **kwargs,
    )


class CreateReminderViewTest(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.url = reverse("future_wise:reminder-list-create")

    @patch("apps.future_wise.views.BrevoEmailService")
    @patch("apps.future_wise.views.AttachmentStorage")
    def test_anonymous_create_pending_verification(self, mock_storage, mock_brevo):
        mock_brevo.return_value.send_verification_email.return_value = {"messageId": "abc"}
        payload = {
            "email": "anon@example.com",
            "subject": "Hi future me",
            "message": "Stay strong.",
            "scheduled_at": FUTURE.isoformat(),
            "tier": "free",
        }
        response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], "pending_verification")
        self.assertIn("detail", response.data)
        mock_brevo.return_value.send_verification_email.assert_called_once()

    @patch("apps.future_wise.views.BrevoEmailService")
    def test_authenticated_create_scheduled(self, mock_brevo):
        user = User.objects.create_user("alice", "alice@example.com", "pass")
        self.client.force_authenticate(user=user)
        payload = {
            "email": "alice@example.com",
            "subject": "Future self",
            "message": "Keep going.",
            "scheduled_at": FUTURE.isoformat(),
        }
        response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], "scheduled")
        # No verification email for authenticated users
        mock_brevo.return_value.send_verification_email.assert_not_called()

    def test_scheduled_too_soon_rejected(self):
        payload = {
            "email": "user@example.com",
            "subject": "Too soon",
            "message": "msg",
            "scheduled_at": PAST_FUTURE.isoformat(),
        }
        response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_email_rejected(self):
        payload = {
            "email": "not-an-email",
            "subject": "Test",
            "message": "msg",
            "scheduled_at": FUTURE.isoformat(),
        }
        response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_missing_required_fields(self):
        response = self.client.post(self.url, {"email": "a@b.com"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class ListRemindersViewTest(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.url = reverse("future_wise:reminder-list-create")
        self.user = User.objects.create_user("bob", "bob@example.com", "pass")

    def test_list_requires_authentication(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_list_returns_only_own_reminders(self):
        other_user = User.objects.create_user("carol", "carol@example.com", "pass")
        make_reminder(user=self.user)
        make_reminder(user=self.user)
        make_reminder(user=other_user)

        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)


class ReminderDetailViewTest(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user("dave", "dave@example.com", "pass")

    def test_owner_can_view_reminder(self):
        reminder = make_reminder(user=self.user)
        url = reverse("future_wise:reminder-detail", kwargs={"pk": reminder.id})
        self.client.force_authenticate(user=self.user)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(str(response.data["id"]), str(reminder.id))

    def test_non_owner_cannot_view_reminder(self):
        other = User.objects.create_user("eve", "eve@example.com", "pass")
        reminder = make_reminder(user=other)
        url = reverse("future_wise:reminder-detail", kwargs={"pk": reminder.id})
        self.client.force_authenticate(user=self.user)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_anonymous_can_view_with_token(self):
        reminder = make_reminder(email_verified=False, status=EmailReminder.Status.PENDING_VERIFICATION)
        url = reverse("future_wise:reminder-detail", kwargs={"pk": reminder.id})
        response = self.client.get(url, {"token": reminder.verification_token})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_anonymous_denied_without_token(self):
        reminder = make_reminder(email_verified=False, status=EmailReminder.Status.PENDING_VERIFICATION)
        url = reverse("future_wise:reminder-detail", kwargs={"pk": reminder.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_cancel_scheduled_reminder(self):
        reminder = make_reminder(user=self.user)
        url = reverse("future_wise:reminder-detail", kwargs={"pk": reminder.id})
        self.client.force_authenticate(user=self.user)
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        reminder.refresh_from_db()
        self.assertEqual(reminder.status, EmailReminder.Status.CANCELLED)

    def test_cannot_cancel_sent_reminder(self):
        reminder = make_reminder(user=self.user, status=EmailReminder.Status.SENT)
        url = reverse("future_wise:reminder-detail", kwargs={"pk": reminder.id})
        self.client.force_authenticate(user=self.user)
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class VerifyEmailViewTest(TestCase):

    def setUp(self):
        self.client = APIClient()

    def test_valid_token_activates_reminder(self):
        reminder = make_reminder(
            email_verified=False,
            status=EmailReminder.Status.PENDING_VERIFICATION,
        )
        url = reverse("future_wise:verify-email", kwargs={"token": reminder.verification_token})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        reminder.refresh_from_db()
        self.assertTrue(reminder.email_verified)
        self.assertEqual(reminder.status, EmailReminder.Status.SCHEDULED)

    def test_invalid_token_returns_404(self):
        url = reverse("future_wise:verify-email", kwargs={"token": "invalidtoken123"})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_expired_token_cancels_reminder(self):
        reminder = make_reminder(
            email_verified=False,
            status=EmailReminder.Status.PENDING_VERIFICATION,
            verification_token_expires_at=timezone.now() - timedelta(seconds=1),
        )
        url = reverse("future_wise:verify-email", kwargs={"token": reminder.verification_token})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_410_GONE)
        reminder.refresh_from_db()
        self.assertEqual(reminder.status, EmailReminder.Status.CANCELLED)

    def test_already_verified_token_returns_404(self):
        """A SCHEDULED reminder (already verified) should not match PENDING_VERIFICATION."""
        reminder = make_reminder(
            email_verified=True,
            status=EmailReminder.Status.SCHEDULED,
        )
        url = reverse("future_wise:verify-email", kwargs={"token": reminder.verification_token})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
