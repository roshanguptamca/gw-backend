import base64
from io import BytesIO
from unittest.mock import Mock, patch

from PIL import Image
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.speaking_buddy.models import BuddyAvatar, BuddyMemory, BuddyProfile, BuddySession

User = get_user_model()


def make_png():
    image = Image.new("RGB", (2, 2), color="purple")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


@override_settings(OPENAI_API_KEY="test-key", SPEAKING_BUDDY_MODEL="gpt-4o-mini")
class SpeakingBuddyApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user1 = User.objects.create_user("buddy1", "buddy1@example.com", "password")
        self.user2 = User.objects.create_user("buddy2", "buddy2@example.com", "password")
        self.profile1 = BuddyProfile.objects.create(user=self.user1, buddy_name="Mila", native_language="en", target_language="nl")
        BuddyProfile.objects.create(user=self.user2, buddy_name="Other", native_language="en", target_language="en")
        BuddyMemory.objects.create(profile=self.profile1, memory_type="note", key="welcome", value={"text": "hello"})

    def auth(self, user):
        self.client.force_authenticate(user=user)

    def test_profile_and_settings_crud(self):
        self.auth(self.user1)
        response = self.client.get("/api/buddy/profile/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["profile"]["buddy_name"], "Mila")

        response = self.client.patch("/api/buddy/profile/", {"buddy_name": "Luna", "learning_goal": "Practice Dutch"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["profile"]["buddy_name"], "Luna")

        response = self.client.get("/api/buddy/settings/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("personality", response.data)

        response = self.client.patch("/api/buddy/settings/", {"personality": "teacher", "default_topic": "Travel"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["personality"], "teacher")

    def test_avatar_upload_requires_consent(self):
        self.auth(self.user1)
        upload = SimpleUploadedFile("avatar.png", make_png(), content_type="image/png")
        response = self.client.post(
            "/api/buddy/avatar/",
            {"avatar_type": "uploaded", "name": "My Avatar", "image": upload, "consent_confirmed": False},
            format="multipart",
        )
        self.assertEqual(response.status_code, 400)

        upload = SimpleUploadedFile("avatar.png", make_png(), content_type="image/png")
        response = self.client.post(
            "/api/buddy/avatar/",
            {"avatar_type": "uploaded", "name": "My Avatar", "image": upload, "consent_confirmed": True},
            format="multipart",
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(BuddyAvatar.objects.filter(profile=self.profile1, is_active=True).exists())

    def test_memory_is_scoped_to_current_user(self):
        self.auth(self.user2)
        response = self.client.get("/api/buddy/memory/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [])

        response = self.client.delete(f"/api/buddy/memory/{BuddyMemory.objects.first().id}/")
        self.assertEqual(response.status_code, 404)

    @patch("apps.speaking_buddy.views.generate_buddy_reply")
    @patch("apps.speaking_buddy.views.summarize_session")
    def test_session_start_message_and_end(self, summarize_session, generate_buddy_reply):
        generate_buddy_reply.side_effect = ["Welcome to practice.", "Great answer."]
        summarize_session.return_value = {
            "summary": "Practiced speaking.",
            "weak_areas": ["grammar"],
            "practice_topics": ["travel"],
            "improvement_notes": ["Use longer answers."],
            "vocabulary": [{"word": "trein", "translation": "train", "language": "nl"}],
            "mistakes": [{"original_text": "Ik zijn", "corrected_text": "Ik ben", "mistake_type": "grammar", "language": "nl"}],
            "user_summary": "Practiced Dutch.",
        }
        self.auth(self.user1)

        response = self.client.post("/api/buddy/session/start/", {"topic": "Travel", "language": "nl"}, format="json")
        self.assertEqual(response.status_code, 201)
        session_id = response.data["id"]
        self.assertEqual(response.data["welcome_message"], "Welcome to practice.")

        response = self.client.post("/api/buddy/session/message/", {"session_id": session_id, "text": "Ik wil oefenen."}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["assistant_reply"], "Great answer.")

        response = self.client.post("/api/buddy/session/end/", {"session_id": session_id}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "ended")
        self.assertTrue(response.data["ai_summary"])
        self.assertTrue(BuddyMemory.objects.filter(profile=self.profile1, memory_type="summary").exists())

        response = self.client.get("/api/buddy/history/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(len(response.data) >= 1)

    @patch("apps.speaking_buddy.services.openai_buddy.OpenAI")
    def test_realtime_token_endpoint_mocks_external_api(self, openai_client_cls):
        client = Mock()
        client.realtime.client_secrets.create.return_value = {
            "client_secret": "token-123",
            "session_id": "session-123",
            "expires_at": "2030-01-01T00:00:00Z",
        }
        openai_client_cls.return_value = client
        self.auth(self.user1)
        response = self.client.post("/api/buddy/realtime-token/", {}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["client_secret"], "token-123")

    def test_other_user_cannot_delete_foreign_memory(self):
        self.auth(self.user2)
        foreign_memory = BuddyMemory.objects.filter(profile=self.profile1).first()
        response = self.client.delete(f"/api/buddy/memory/{foreign_memory.id}/")
        self.assertEqual(response.status_code, 404)
