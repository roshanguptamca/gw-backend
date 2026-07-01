from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from rest_framework import status
from rest_framework.test import APIClient

from apps.future_wise.models import EmailReminder

User = get_user_model()


def reminder_payload(**overrides):
    payload = {
        "email": "owner@example.com",
        "subject": "Future note",
        "message": "Remember this.",
        "scheduled_at": (timezone.now() + timedelta(days=7)).isoformat(),
        "channels": ["email"],
    }
    payload.update(overrides)
    return payload


def make_reminder(user, **overrides):
    values = {
        "user": user,
        "email": "owner@example.com",
        "email_verified": True,
        "verification_token": EmailReminder.generate_verification_token(),
        "verification_token_expires_at": EmailReminder.make_token_expiry(),
        "subject": "Future note",
        "message": "Remember this.",
        "scheduled_at": timezone.now() + timedelta(days=7),
        "channels": ["email"],
        "channels_requested": "email",
        "status": EmailReminder.Status.SCHEDULED,
    }
    values.update(overrides)
    return EmailReminder.objects.create(**values)


class MultiChannelReminderCreateTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("owner", "owner@example.com", "password")
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.url = reverse("future_wise:reminder-list-create")

    def test_create_email_only(self):
        response = self.client.post(self.url, reminder_payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["channels"], ["email"])

    def test_create_sms_only_without_email(self):
        response = self.client.post(
            self.url,
            reminder_payload(email="", channels=["sms"], phone_number="+31612345678"),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["channels"], ["sms"])

    def test_create_multiple_phone_and_email_channels(self):
        channels = ["email", "sms", "voice_call", "whatsapp"]
        response = self.client.post(
            self.url,
            reminder_payload(channels=channels, phone_number="+31612345678"),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["channels"], ["email", "sms", "voice", "whatsapp"])

    def test_multipart_comma_separated_channels_are_supported(self):
        response = self.client.post(
            self.url,
            reminder_payload(channels="email,sms", phone_number="+31612345678"),
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["channels"], ["email", "sms"])

    def test_at_least_one_channel_is_required(self):
        response = self.client.post(
            self.url,
            reminder_payload(channels=[]),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("channels", response.data)

    def test_phone_is_required_for_phone_channels(self):
        response = self.client.post(
            self.url,
            reminder_payload(email="", channels=["sms"]),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("phone_number", response.data)


class FutureReminderCrudTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("owner", "owner@example.com", "password")
        self.other_user = User.objects.create_user("other", "other@example.com", "password")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_user_can_update_own_future_reminder(self):
        reminder = make_reminder(self.user)
        url = reverse("future_wise:reminder-detail", kwargs={"pk": reminder.pk})

        response = self.client.patch(
            url,
            {
                "subject": "Updated subject",
                "channels": ["sms", "call"],
                "email": "",
                "phone_number": "+31612345678",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["channels"], ["sms", "voice"])
        reminder.refresh_from_db()
        self.assertEqual(reminder.subject, "Updated subject")
        self.assertEqual(reminder.channels_requested, "sms,voice")

    def test_user_cannot_update_sent_reminder(self):
        reminder = make_reminder(self.user, status=EmailReminder.Status.SENT)
        url = reverse("future_wise:reminder-detail", kwargs={"pk": reminder.pk})

        response = self.client.patch(url, {"subject": "Too late"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_user_can_delete_own_future_reminder(self):
        reminder = make_reminder(self.user)
        url = reverse("future_wise:reminder-detail", kwargs={"pk": reminder.pk})

        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(EmailReminder.objects.filter(pk=reminder.pk).exists())

    def test_user_cannot_delete_sent_reminder(self):
        reminder = make_reminder(self.user, status=EmailReminder.Status.SENT)
        url = reverse("future_wise:reminder-detail", kwargs={"pk": reminder.pk})

        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_user_cannot_update_or_delete_another_users_reminder(self):
        reminder = make_reminder(self.other_user)
        url = reverse("future_wise:reminder-detail", kwargs={"pk": reminder.pk})

        self.assertEqual(
            self.client.patch(url, {"subject": "Not mine"}, format="json").status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(self.client.delete(url).status_code, status.HTTP_403_FORBIDDEN)

    def test_legacy_single_channel_reminder_serializes_channels(self):
        reminder = make_reminder(
            self.user,
            channels=[],
            channels_requested="telegram",
            telegram_chat_id="123456",
        )
        url = reverse("future_wise:reminder-detail", kwargs={"pk": reminder.pk})

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["channels"], ["telegram"])
