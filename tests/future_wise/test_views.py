"""
API integration tests for FutureWise views.
"""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from rest_framework import status
from rest_framework.test import APIClient

from apps.future_wise.models import AbuseLog, EmailReminder

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
    @patch("apps.future_wise.views.AttachmentStorage")
    def test_verification_email_uses_frontend_url(self, mock_storage, mock_brevo):
        """Email verification link must point to the frontend, not the backend API."""
        import apps.future_wise.views as fw_views

        mock_brevo.return_value.send_verification_email.return_value = {"messageId": "abc"}
        payload = {
            "email": "anon@example.com",
            "subject": "Hi future me",
            "message": "Stay strong.",
            "scheduled_at": FUTURE.isoformat(),
            "tier": "free",
        }
        with patch.object(fw_views, "_FRONTEND_BASE", "https://example-frontend.com"):
            self.client.post(self.url, payload, format="json")

        call_args = mock_brevo.return_value.send_verification_email.call_args
        verification_url = call_args[0][1] if call_args[0] else call_args[1].get("verification_url")
        self.assertIn("example-frontend.com", verification_url)
        self.assertIn("/future-wise/verify/", verification_url)
        self.assertNotIn("/api/", verification_url)

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

    @patch("apps.future_wise.views.BrevoEmailService")
    def test_authenticated_create_accepts_new_letter_type(self, mock_brevo):
        user = User.objects.create_user("lettertype", "letter@example.com", "pass")
        self.client.force_authenticate(user=user)
        payload = {
            "email": "letter@example.com",
            "subject": "Doctor visit",
            "message": "See you there.",
            "scheduled_at": FUTURE.isoformat(),
            "letter_type": "appointment_reminder",
        }
        response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["letter_type"], "appointment_reminder")
        self.assertIn("letter_type_description", response.data)
        mock_brevo.return_value.send_verification_email.assert_not_called()

    @patch("apps.future_wise.views.BrevoEmailService")
    def test_authenticated_create_allows_blank_letter_type(self, mock_brevo):
        user = User.objects.create_user("blankletter", "blank@example.com", "pass")
        self.client.force_authenticate(user=user)
        payload = {
            "email": "blank@example.com",
            "subject": "Anything",
            "message": "Custom note.",
            "scheduled_at": FUTURE.isoformat(),
            "letter_type": "",
        }
        response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["letter_type"], "")
        mock_brevo.return_value.send_verification_email.assert_not_called()

    def test_create_rejects_unknown_letter_type(self):
        user = User.objects.create_user("badletter", "badletter@example.com", "pass")
        self.client.force_authenticate(user=user)
        payload = {
            "email": "badletter@example.com",
            "subject": "Unknown type",
            "message": "Nope.",
            "scheduled_at": FUTURE.isoformat(),
            "letter_type": "unknown_kind",
        }
        response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("letter_type", response.data)


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

    def test_delete_scheduled_reminder(self):
        reminder = make_reminder(user=self.user)
        url = reverse("future_wise:reminder-detail", kwargs={"pk": reminder.id})
        self.client.force_authenticate(user=self.user)
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(EmailReminder.objects.filter(pk=reminder.pk).exists())

    def test_cannot_delete_sent_reminder(self):
        reminder = make_reminder(user=self.user, status=EmailReminder.Status.SENT)
        url = reverse("future_wise:reminder-detail", kwargs={"pk": reminder.id})
        self.client.force_authenticate(user=self.user)
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class ReminderMetadataAndAIGenerationViewTest(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user("aiuser", "aiuser@example.com", "pass")
        self.letter_types_url = reverse("future_wise:reminder-letter-types")
        self.ai_generate_url = reverse("future_wise:reminder-ai-generate-message")

    def test_letter_types_endpoint_lists_new_types_with_descriptions(self):
        response = self.client.get(self.letter_types_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        values = {item["value"]: item for item in response.data}
        self.assertIn("future_self", values)
        self.assertIn("subscription_renewal_reminder", values)
        self.assertEqual(values["custom_message"]["label"], "Custom Message")
        self.assertTrue(values["meeting_reminder"]["description"])

    @patch("apps.future_wise.views.generate_reminder_message")
    def test_ai_message_generation_success(self, mock_generate):
        self.client.force_authenticate(user=self.user)
        mock_generate.return_value = {
            "subject": "Meeting reminder for Sam",
            "email_body": "Hi Sam,\n\nJust a reminder about tomorrow's project sync.\n\nBest,\nGuideWisey",
            "short_message": "Reminder: project sync tomorrow at 10:00.",
            "call_script": "Hi Sam, this is your reminder about tomorrow's project sync at 10:00.",
        }
        payload = {
            "letter_type": "meeting_reminder",
            "occasion": "Project sync",
            "tone": "professional",
            "recipient_name": "Sam",
            "language": "English",
            "channels": ["email", "voice_call"],
            "extra_context": "Mention tomorrow's 10:00 agenda review.",
        }
        response = self.client.post(self.ai_generate_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, mock_generate.return_value)
        mock_generate.assert_called_once_with(
            letter_type="meeting_reminder",
            occasion="Project sync",
            tone="professional",
            recipient_name="Sam",
            language="English",
            channels=["email", "voice"],
            extra_context="Mention tomorrow's 10:00 agenda review.",
        )

    @override_settings(OPENAI_API_KEY="", AI_PROVIDER_FALLBACKS="openai")
    def test_ai_generation_returns_503_when_provider_unavailable(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.post(
            self.ai_generate_url,
            {"letter_type": "custom_message", "channels": ["email"]},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(
            response.data["error"],
            "AI message generation is currently unavailable. Please write your message manually.",
        )

    def test_ai_generation_requires_authentication(self):
        response = self.client.post(
            self.ai_generate_url,
            {"letter_type": "custom_message", "channels": ["email"]},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


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

    def test_valid_token_changes_status_to_scheduled(self):
        """Valid token must transition reminder from PENDING_VERIFICATION to SCHEDULED."""
        reminder = make_reminder(
            email_verified=False,
            status=EmailReminder.Status.PENDING_VERIFICATION,
        )
        url = reverse("future_wise:verify-email", kwargs={"token": reminder.verification_token})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        reminder.refresh_from_db()
        self.assertEqual(reminder.status, EmailReminder.Status.SCHEDULED)
        self.assertTrue(reminder.email_verified)

    def test_invalid_token_returns_api_error_detail(self):
        """Invalid token should return a JSON error detail, not raw DRF HTML."""
        url = reverse("future_wise:verify-email", kwargs={"token": "no-such-token"})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn("detail", response.data)

    def test_already_used_token_returns_api_error_detail(self):
        """Already-used (SCHEDULED) token should return JSON error detail."""
        reminder = make_reminder(
            email_verified=True,
            status=EmailReminder.Status.SCHEDULED,
        )
        url = reverse("future_wise:verify-email", kwargs={"token": reminder.verification_token})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn("detail", response.data)


class DailyReminderLimitTest(TestCase):
    """Free-user daily limit: 3 email reminders per 24 hours, superusers exempt."""

    def setUp(self):
        self.client = APIClient()
        self.url = reverse("future_wise:reminder-list-create")
        self.payload = {
            "email": "limit@example.com",
            "subject": "Daily limit test",
            "message": "Test message",
            "scheduled_at": FUTURE.isoformat(),
            "tier": "free",
        }

    def _seed_abuse_log(self, email: str, count: int, *, user=None):
        """Insert `count` AbuseLog entries for the email to simulate prior requests."""
        ip = "127.0.0.1"
        for _ in range(count):
            AbuseLog.objects.create(email=email, ip_address=ip, action="create_reminder")

    @patch("apps.future_wise.views.BrevoEmailService")
    @patch("apps.future_wise.views.AttachmentStorage")
    def test_anonymous_blocked_after_daily_limit(self, mock_storage, mock_brevo):
        """Anonymous user is blocked after 3 reminders in 24 hours."""
        mock_brevo.return_value.send_verification_email.return_value = {"messageId": "x"}
        self._seed_abuse_log("limit@example.com", 3)
        response = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertIn("detail", response.data)

    @patch("apps.future_wise.views.BrevoEmailService")
    @patch("apps.future_wise.views.AttachmentStorage")
    def test_authenticated_user_blocked_after_daily_limit(self, mock_storage, mock_brevo):
        """Authenticated non-admin user is blocked after 3 reminders in 24 hours."""
        mock_brevo.return_value.send_verification_email.return_value = {"messageId": "x"}
        user = User.objects.create_user("limituser", "limit@example.com", "pass")
        self.client.force_authenticate(user=user)
        self._seed_abuse_log("limit@example.com", 3)
        response = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    @patch("apps.future_wise.views.BrevoEmailService")
    @patch("apps.future_wise.views.AttachmentStorage")
    def test_superuser_bypasses_daily_limit(self, mock_storage, mock_brevo):
        """Superusers are never blocked by the daily limit."""
        mock_brevo.return_value.send_verification_email.return_value = {"messageId": "x"}
        admin = User.objects.create_superuser("superadmin", "admin@example.com", "pass")
        self.client.force_authenticate(user=admin)
        # Seed 10 entries — way over the free limit
        self._seed_abuse_log("admin@example.com", 10)
        payload = {**self.payload, "email": "admin@example.com"}
        response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_daily_limit_error_message(self):
        """429 from our daily-limit check must include the expected user-facing message."""
        # Use an authenticated user to bypass the IP-based DRF anon throttle,
        # so the only 429 source is our AbuseLog daily-limit check.
        user = User.objects.create_user("msgtest", "limit@example.com", "pass")
        self.client.force_authenticate(user=user)
        self._seed_abuse_log("limit@example.com", 3)
        response = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertIn("3 Smart Reminders per day", response.data["detail"])

    @patch("apps.future_wise.views.BrevoEmailService")
    @patch("apps.future_wise.views.AttachmentStorage")
    def test_authenticated_user_can_use_different_recipient_email(self, mock_storage, mock_brevo):
        """Logged-in users may specify any recipient email and the reminder is SCHEDULED."""
        mock_brevo.return_value.send_verification_email.return_value = {"messageId": "x"}
        user = User.objects.create_user("authuser", "authuser@example.com", "pass")
        self.client.force_authenticate(user=user)
        payload = {
            "email": "someone_else@example.com",
            "subject": "For a friend",
            "message": "Stay well.",
            "scheduled_at": FUTURE.isoformat(),
        }
        response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], "scheduled")
        reminder = EmailReminder.objects.get(id=response.data["id"])
        self.assertEqual(reminder.user, user)
        self.assertEqual(reminder.email, "someone_else@example.com")
