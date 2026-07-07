from io import BytesIO
from unittest.mock import ANY, Mock, patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from PIL import Image
from rest_framework.test import APIClient

from apps.speaking_buddy.models import (
    Buddy3DAvatar,
    BuddyAvatar,
    BuddyGeneratedAvatar,
    BuddyMemory,
    BuddyProfile,
    BuddySession,
    BuddySettings,
    BuddyUsageQuota,
    BuddyVocabulary,
)
from apps.speaking_buddy.services.context_builder import build_session_context
from apps.speaking_buddy.services.openai_buddy import generate_buddy_reply

User = get_user_model()


def make_png():
    image = Image.new("RGB", (2, 2), color="purple")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


@override_settings(
    OPENAI_API_KEY="test-key",
    SPEAKING_BUDDY_MODEL="gpt-4o-mini",
    SPEAKING_BUDDY_REALTIME_MODEL="gpt-realtime-test",
)
class SpeakingBuddyApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user1 = User.objects.create_user("buddy1", "buddy1@example.com", "password")
        self.user2 = User.objects.create_user("buddy2", "buddy2@example.com", "password")
        self.profile1 = BuddyProfile.objects.create(
            user=self.user1, buddy_name="Mila", native_language="en", target_language="nl"
        )
        BuddyProfile.objects.create(user=self.user2, buddy_name="Other", native_language="en", target_language="en")
        BuddyMemory.objects.create(profile=self.profile1, memory_type="note", key="welcome", value={"text": "hello"})

    def auth(self, user):
        self.client.force_authenticate(user=user)

    def test_profile_and_settings_crud(self):
        self.auth(self.user1)
        response = self.client.get("/api/buddy/profile/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["profile"]["buddy_name"], "Mila")

        response = self.client.patch(
            "/api/buddy/profile/", {"buddy_name": "Luna", "learning_goal": "Practice Dutch"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["profile"]["buddy_name"], "Luna")

        response = self.client.get("/api/buddy/settings/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("personality", response.data)

        response = self.client.patch(
            "/api/buddy/settings/",
            {"personality": "teacher", "default_topic": "Travel", "selected_voice": "cedar"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["personality"], "teacher")
        self.assertEqual(response.data["selected_voice"], "cedar")

    def test_3d_avatar_catalog_is_available_and_selectable(self):
        Buddy3DAvatar.objects.create(
            name="Nova",
            slug="nova-3d",
            gender_style="neutral",
            age_style="adult",
            personality="friendly",
            default_voice="Nova Warm",
            voice_style="warm",
            mood="encouraging",
            thumbnail="data:image/svg+xml,%3Csvg/%3E",
            glb_file="https://example.com/nova.glb",
            idle_animation="Idle",
            talking_animation="Talk",
        )
        self.auth(self.user1)
        response = self.client.get("/api/buddy/avatar-3d/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(len(response.data["catalog"]) >= 1)

        response = self.client.post("/api/buddy/avatar-3d/", {"avatar_3d_slug": "nova-3d"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["settings"]["selected_3d_avatar_slug"], "nova-3d")

    def test_seeded_avatar_catalog_uses_requested_free_local_models(self):
        expected = {"emma", "leo", "zara", "noah", "luna", "kai", "mila", "omar", "aria", "atlas"}
        avatars = Buddy3DAvatar.objects.filter(slug__in=expected, is_active=True)
        self.assertEqual(set(avatars.values_list("slug", flat=True)), expected)
        for avatar in avatars:
            self.assertEqual(avatar.model_url, f"/assets/buddy3d/{avatar.slug}.vrm")
            self.assertEqual(avatar.thumbnail_url, "")
            self.assertTrue(avatar.supported_blendshapes)
            self.assertTrue(avatar.supported_customizations)
            self.assertTrue(avatar.has_full_body)
            self.assertTrue(avatar.has_hair)
            self.assertTrue(avatar.has_hands)
            self.assertTrue(avatar.has_feet)

    def test_generated_avatar_upload_requires_consent(self):
        self.auth(self.user1)
        upload = SimpleUploadedFile("avatar.png", make_png(), content_type="image/png")
        response = self.client.post(
            "/api/buddy/avatar-generated/",
            {"source_image": upload, "consent_confirmed": False},
            format="multipart",
        )
        self.assertEqual(response.status_code, 400)

    def test_generated_avatar_request_can_be_created(self):
        self.auth(self.user1)
        upload = SimpleUploadedFile("avatar.png", make_png(), content_type="image/png")
        response = self.client.post(
            "/api/buddy/avatar-generated/",
            {
                "source_image": upload,
                "consent_confirmed": True,
                "provider": "template",
                "preferred_gender_style": "female",
                "preferred_hair_style": "long",
                "preferred_outfit_style": "professional",
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["status"], "completed")
        self.assertEqual(response.data["provider"], "template")
        self.assertEqual(response.data["generation_method"], "template")
        self.assertTrue(response.data["detected_features"])
        self.assertTrue(response.data["appearance_config"])
        self.assertEqual(response.data["appearance_config"]["hair_mesh"], "long")
        self.assertEqual(response.data["appearance_config"]["outfit_style"], "professional")
        self.assertNotEqual(response.data["appearance_config"]["outfit_color"].lower(), "#7c3aed")
        self.assertIsNotNone(response.data["selected_base_avatar"])
        self.assertTrue(response.data["generated_model_path"].startswith("/assets/buddy3d/"))
        self.assertTrue(BuddyGeneratedAvatar.objects.filter(user=self.user1).exists())

    def test_generated_avatar_can_be_selected_and_serialized(self):
        avatar = BuddyGeneratedAvatar.objects.create(
            user=self.user1,
            provider="template",
            status="completed",
            consent_confirmed=True,
            generated_model_path="/assets/buddy3d/mila.vrm",
            generated_glb_url="/assets/buddy3d/mila.vrm",
            appearance_config={"base_avatar_slug": "mila"},
        )
        self.auth(self.user1)
        response = self.client.post(
            "/api/buddy/avatar-3d/",
            {"generated_avatar_id": avatar.id, "avatar_render_mode": "generated_3d"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["avatar_render_mode"], "generated_3d")
        self.assertEqual(response.data["selected_generated_avatar"]["id"], avatar.id)
        self.assertEqual(response.data["selected_3d_renderable_avatar"]["id"], avatar.id)
        self.assertEqual(
            response.data["selected_3d_renderable_avatar"]["appearance_config"]["base_avatar_slug"],
            "mila",
        )

    def test_generated_avatar_detail_and_regenerate_are_user_scoped(self):
        self.auth(self.user1)
        upload = SimpleUploadedFile("avatar.png", make_png(), content_type="image/png")
        created = self.client.post(
            "/api/buddy/generated-avatar/",
            {"source_image": upload, "consent_confirmed": True},
            format="multipart",
        )
        self.assertEqual(created.status_code, 201)
        avatar_id = created.data["id"]

        detail = self.client.get(f"/api/buddy/generated-avatar/{avatar_id}/")
        self.assertEqual(detail.status_code, 200)
        self.assertTrue(detail.data["detected_features"])

        regenerated = self.client.post(
            f"/api/buddy/generated-avatar/{avatar_id}/regenerate/",
            {"preferred_hair_style": "close-crop", "preferred_outfit_style": "sport"},
            format="json",
        )
        self.assertEqual(regenerated.status_code, 200)
        self.assertEqual(regenerated.data["status"], "completed")
        self.assertEqual(regenerated.data["appearance_config"]["hair_mesh"], "close-crop")
        self.assertEqual(regenerated.data["appearance_config"]["outfit_style"], "sport")

        self.auth(self.user2)
        self.assertEqual(self.client.get(f"/api/buddy/generated-avatar/{avatar_id}/").status_code, 404)
        self.assertEqual(
            self.client.post(f"/api/buddy/generated-avatar/{avatar_id}/regenerate/", {}, format="json").status_code,
            404,
        )

    def test_generated_avatar_rejects_non_image(self):
        self.auth(self.user1)
        upload = SimpleUploadedFile("avatar.txt", b"not an image", content_type="text/plain")
        response = self.client.post(
            "/api/buddy/generated-avatar/",
            {"source_image": upload, "consent_confirmed": True},
            format="multipart",
        )
        self.assertEqual(response.status_code, 400)

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

    def test_avatar_endpoint_returns_absolute_media_url(self):
        self.auth(self.user1)
        BuddyAvatar.objects.create(
            profile=self.profile1,
            avatar_type="uploaded",
            name="Uploaded",
            image_url="/media/speaking_buddy/avatars/example.jpg",
            consent_confirmed=True,
            is_active=True,
        )
        response = self.client.get("/api/buddy/avatar/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["active_avatar"]["resolved_image_url"].startswith("http://"))
        self.assertIn("/media/", response.data["active_avatar"]["resolved_image_url"])

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
            "mistakes": [
                {"original_text": "Ik zijn", "corrected_text": "Ik ben", "mistake_type": "grammar", "language": "nl"}
            ],
            "user_summary": "Practiced Dutch.",
        }
        self.auth(self.user1)

        response = self.client.post("/api/buddy/session/start/", {"topic": "Travel", "language": "nl"}, format="json")
        self.assertEqual(response.status_code, 201)
        session_id = response.data["id"]
        self.assertEqual(response.data["welcome_message"], "Welcome to practice.")

        response = self.client.post(
            "/api/buddy/session/message/", {"session_id": session_id, "text": "Ik wil oefenen."}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["assistant_reply"], "Great answer.")

        response = self.client.post("/api/buddy/session/end/", {"session_id": session_id}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "ended")
        self.assertEqual(response.data["end_reason"], "")
        self.assertTrue(response.data["ai_summary"])
        self.assertTrue(BuddyMemory.objects.filter(profile=self.profile1, memory_type="summary").exists())
        self.assertEqual(response.data["usage"]["conversations_used"], 1)
        self.assertEqual(response.data["usage"]["conversations_remaining"], 99)
        self.assertTrue(BuddyUsageQuota.objects.filter(user=self.user1, conversations_used=1).exists())

        response = self.client.get("/api/buddy/history/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(len(response.data) >= 1)

    def test_usage_defaults_and_usage_endpoint(self):
        self.auth(self.user1)
        response = self.client.get("/api/buddy/usage/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["free_conversation_limit"], 100)
        self.assertEqual(response.data["conversations_used"], 0)
        self.assertEqual(response.data["conversations_remaining"], 100)
        self.assertFalse(response.data["is_limit_reached"])

    def test_logged_out_user_cannot_start_session(self):
        response = self.client.post("/api/buddy/session/start/", {"topic": "Travel"}, format="json")
        self.assertEqual(response.status_code, 403)

    @patch("apps.speaking_buddy.views.generate_buddy_reply", return_value="Welcome")
    def test_logged_in_user_can_start_session_when_quota_remains(self, generate_buddy_reply):
        self.auth(self.user1)
        response = self.client.post("/api/buddy/session/start/", {"topic": "Travel"}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["status"], "active")
        self.assertEqual(response.data["selected_voice"], "marin")
        self.assertEqual(generate_buddy_reply.call_count, 1)

    @patch("apps.speaking_buddy.views.generate_buddy_reply", return_value="Welcome")
    def test_session_usage_does_not_double_count_same_session(self, generate_buddy_reply):
        self.auth(self.user1)
        start = self.client.post("/api/buddy/session/start/", {"topic": "Travel"}, format="json")
        self.assertEqual(start.status_code, 201)
        session_id = start.data["id"]

        message = self.client.post(
            "/api/buddy/session/message/", {"session_id": session_id, "text": "Ik wil oefenen."}, format="json"
        )
        self.assertEqual(message.status_code, 200)

        with patch("apps.speaking_buddy.views.summarize_session", return_value={"summary": "Done"}):
            first_end = self.client.post("/api/buddy/session/end/", {"session_id": session_id}, format="json")
            second_end = self.client.post("/api/buddy/session/end/", {"session_id": session_id}, format="json")

        self.assertEqual(first_end.status_code, 200)
        self.assertEqual(second_end.status_code, 200)
        quota = BuddyUsageQuota.objects.get(user=self.user1)
        self.assertEqual(quota.conversations_used, 1)
        self.assertTrue(BuddySession.objects.get(id=session_id).usage_counted)

    @patch("apps.speaking_buddy.views.generate_buddy_reply", return_value="Welcome")
    def test_session_end_persists_reason_and_timestamp(self, generate_buddy_reply):
        self.auth(self.user1)
        start = self.client.post("/api/buddy/session/start/", {"topic": "Travel"}, format="json")
        session_id = start.data["id"]
        response = self.client.post(
            "/api/buddy/session/end/",
            {"session_id": session_id, "reason": "route_change"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        session = BuddySession.objects.get(id=session_id)
        self.assertEqual(session.end_reason, "route_change")
        self.assertEqual(response.data["end_reason"], "route_change")

    @patch("apps.speaking_buddy.views.generate_buddy_reply", return_value="Welcome")
    def test_session_end_rejects_foreign_session(self, generate_buddy_reply):
        self.auth(self.user1)
        start = self.client.post("/api/buddy/session/start/", {"topic": "Travel"}, format="json")
        session_id = start.data["id"]
        self.auth(self.user2)
        response = self.client.post("/api/buddy/session/end/", {"session_id": session_id}, format="json")
        self.assertEqual(response.status_code, 404)

    @patch("apps.speaking_buddy.views.generate_buddy_reply", return_value="Welcome")
    def test_user_cannot_start_session_after_100_conversations(self, generate_buddy_reply):
        BuddyUsageQuota.objects.create(user=self.user1, conversations_used=100, free_conversation_limit=100)
        self.auth(self.user1)
        response = self.client.post("/api/buddy/session/start/", {"topic": "Travel"}, format="json")
        self.assertEqual(response.status_code, 403)
        self.assertIn("100 free AI Buddy conversations", response.data["error"])

    def test_multilingual_fallback_reply_uses_target_language(self):
        self.profile1.target_language = "hi"
        self.profile1.save(update_fields=["target_language", "updated_at"])
        context = build_session_context(self.profile1)
        with patch("apps.speaking_buddy.services.openai_buddy._client", return_value=None):
            reply = generate_buddy_reply(context, "hello", [])
        self.assertIn("buddy", reply.lower())
        self.assertIn("धीरे", reply)

    @patch("apps.speaking_buddy.services.openai_buddy.OpenAI")
    def test_realtime_token_endpoint_mocks_external_api(self, openai_client_cls):
        client = Mock()
        client.realtime.client_secrets.create.return_value = {
            "client_secret": "token-123",
            "value": "token-123",
            "session_id": "session-123",
            "expires_at": "2030-01-01T00:00:00Z",
        }
        openai_client_cls.return_value = client
        self.auth(self.user1)
        response = self.client.post("/api/buddy/realtime-token/", {}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["client_secret"], "token-123")
        self.assertEqual(response.data["selected_voice"], "marin")
        self.assertEqual(response.data["audio_source"], "openai_realtime")
        client.realtime.client_secrets.create.assert_called_once_with(
            expires_after={"anchor": "created_at", "seconds": 600},
            session={
                "type": "realtime",
                "model": "gpt-realtime-test",
                "audio": {
                    "output": {"voice": "marin"},
                    "input": {
                        "turn_detection": {
                            "type": "semantic_vad",
                            "eagerness": "auto",
                            "create_response": True,
                            "interrupt_response": True,
                        },
                        "noise_reduction": {"type": "near_field"},
                        "transcription": {
                            "model": "gpt-4o-mini-transcribe",
                            "language": "nl",
                        },
                    },
                },
                "instructions": ANY,
            },
        )

    def test_semantic_vad_eagerness_mapping_is_stable(self):
        """Regression test for the human-like Semantic VAD turn detection:
        shorter silence_timeout_ms settings should respond quicker (higher
        eagerness), longer ones should wait for the learner to finish a
        thought (lower eagerness), and this must stay deterministic."""
        from apps.speaking_buddy.services.openai_buddy import _eagerness_from_silence_timeout

        self.assertEqual(_eagerness_from_silence_timeout(300), "high")
        self.assertEqual(_eagerness_from_silence_timeout(600), "high")
        self.assertEqual(_eagerness_from_silence_timeout(900), "auto")
        self.assertEqual(_eagerness_from_silence_timeout(1199), "auto")
        self.assertEqual(_eagerness_from_silence_timeout(1200), "low")
        self.assertEqual(_eagerness_from_silence_timeout(2000), "low")

    @patch("apps.speaking_buddy.views.generate_buddy_reply", return_value="Welcome")
    def test_session_voice_is_frozen_and_duplicate_start_reuses_session(self, generate_buddy_reply):
        self.auth(self.user1)
        settings_obj, _ = BuddySettings.objects.get_or_create(profile=self.profile1)
        settings_obj.selected_voice = "cedar"
        settings_obj.save(update_fields=["selected_voice", "updated_at"])

        first = self.client.post("/api/buddy/session/start/", {"topic": "Travel"}, format="json")
        second = self.client.post("/api/buddy/session/start/", {"topic": "Work"}, format="json")

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.data["id"], second.data["id"])
        self.assertEqual(first.data["selected_voice"], "cedar")
        self.assertTrue(second.data["reused_session"])
        self.assertEqual(BuddySession.objects.filter(profile=self.profile1, status="active").count(), 1)
        self.assertEqual(generate_buddy_reply.call_count, 1)

    @patch("apps.speaking_buddy.services.openai_buddy.OpenAI")
    def test_reconnect_uses_voice_frozen_on_session(self, openai_client_cls):
        client = Mock()
        client.realtime.client_secrets.create.return_value = {"value": "token"}
        openai_client_cls.return_value = client
        self.auth(self.user1)
        session = BuddySession.objects.create(profile=self.profile1, selected_voice="cedar")
        settings_obj, _ = BuddySettings.objects.get_or_create(profile=self.profile1)
        settings_obj.selected_voice = "marin"
        settings_obj.save(update_fields=["selected_voice", "updated_at"])

        for _ in range(2):
            response = self.client.post("/api/buddy/realtime-token/", {"session_id": session.id}, format="json")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data["selected_voice"], "cedar")

        calls = client.realtime.client_secrets.create.call_args_list
        self.assertEqual(len(calls), 2)
        self.assertTrue(all(call.kwargs["session"]["audio"]["output"]["voice"] == "cedar" for call in calls))

    def test_other_user_cannot_delete_foreign_memory(self):
        self.auth(self.user2)
        foreign_memory = BuddyMemory.objects.filter(profile=self.profile1).first()
        response = self.client.delete(f"/api/buddy/memory/{foreign_memory.id}/")
        self.assertEqual(response.status_code, 404)

    def test_memory_vocabulary_and_mistakes_are_user_scoped(self):
        self.auth(self.user1)
        response = self.client.post(
            "/api/buddy/memory/",
            {"memory_type": "topic", "key": "work", "value": {"text": "Interviews"}, "importance": 3},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        response = self.client.post(
            "/api/buddy/vocabulary/",
            {"word": "sollicitatie", "translation": "job application", "language": "nl"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(BuddyVocabulary.objects.filter(profile=self.profile1, word="sollicitatie").exists())
        response = self.client.post(
            "/api/buddy/mistakes/",
            {"original_text": "Ik zijn", "corrected_text": "Ik ben", "mistake_type": "grammar", "language": "nl"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)

        self.auth(self.user2)
        self.assertEqual(self.client.get("/api/buddy/vocabulary/").data, [])
        self.assertEqual(self.client.get("/api/buddy/mistakes/").data, [])

    def test_settings_patch_saves_every_field(self):
        self.auth(self.user1)
        payload = {
            "personality": "strict_coach",
            "voice_style": "energetic",
            "voice_gender": "male",
            "voice_age": "senior",
            "speaking_speed": 90,
            "correction_level": "strict",
            "difficulty_level": "hard",
            "theme_color": "#112233",
            "default_topic": "Job interviews",
        }
        response = self.client.patch("/api/buddy/settings/", payload, format="json")
        self.assertEqual(response.status_code, 200)
        for field, value in payload.items():
            self.assertEqual(response.data[field], value, field)

        settings_obj = BuddySettings.objects.get(profile=self.profile1)
        for field, value in payload.items():
            self.assertEqual(getattr(settings_obj, field), value, field)

    def test_voice_gender_change_maps_to_consistent_voice_without_explicit_choice(self):
        self.auth(self.user1)
        response = self.client.patch(
            "/api/buddy/settings/", {"voice_gender": "female", "voice_age": "adult"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["selected_voice"], "nova")
        self.assertIn(response.data["selected_voice"], {"nova", "shimmer"})

        response = self.client.patch(
            "/api/buddy/settings/", {"voice_gender": "male", "voice_age": "senior"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["selected_voice"], "onyx")
        self.assertIn(response.data["selected_voice"], {"onyx", "echo"})

    def test_female_voice_gender_never_resolves_to_a_non_female_voice(self):
        """Regression test: female previously mapped to 'alloy' for adult voice
        age, which sounds male/neutral on the Realtime API and caused calls to
        still sound male even after selecting Female. Female must always
        resolve to nova or shimmer, never alloy/echo/onyx."""
        from apps.speaking_buddy.services.voice_mapping import resolve_voice

        for age in ["young", "adult", "senior"]:
            voice = resolve_voice("female", age)
            self.assertIn(voice, {"nova", "shimmer"}, f"female/{age} resolved to {voice}")

        for age in ["young", "adult", "senior"]:
            voice = resolve_voice("male", age)
            self.assertIn(voice, {"echo", "onyx"}, f"male/{age} resolved to {voice}")

        for age in ["young", "adult", "senior"]:
            self.assertEqual(resolve_voice("neutral", age), "alloy")

    def test_voice_mapping_is_stable_for_same_inputs(self):
        from apps.speaking_buddy.services.voice_mapping import resolve_voice

        for gender, age in [("female", "young"), ("female", "adult"), ("male", "senior"), ("neutral", "adult")]:
            first = resolve_voice(gender, age)
            second = resolve_voice(gender, age)
            self.assertEqual(first, second)

    def test_explicit_selected_voice_is_not_overridden_by_gender_change(self):
        self.auth(self.user1)
        response = self.client.patch(
            "/api/buddy/settings/",
            {"voice_gender": "female", "voice_age": "young", "selected_voice": "cedar"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["selected_voice"], "cedar")

    def test_settings_rejects_invalid_enum_values(self):
        self.auth(self.user1)
        response = self.client.patch("/api/buddy/settings/", {"difficulty_level": "impossible"}, format="json")
        self.assertEqual(response.status_code, 400)

        response = self.client.patch("/api/buddy/settings/", {"voice_gender": "robotic"}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_session_prompt_contains_key_settings(self):
        self.profile1.target_language = "nl"
        self.profile1.learning_goal = "Practice Dutch for customer support"
        self.profile1.save(update_fields=["target_language", "learning_goal", "updated_at"])
        settings_obj, _ = BuddySettings.objects.get_or_create(profile=self.profile1)
        settings_obj.personality = "strict_coach"
        settings_obj.correction_level = "strict"
        settings_obj.difficulty_level = "hard"
        settings_obj.save(update_fields=["personality", "correction_level", "difficulty_level", "updated_at"])

        context = build_session_context(self.profile1, settings_obj)
        prompt = context.system_prompt
        self.assertIn("Dutch", prompt)
        self.assertIn("hard", prompt)
        self.assertIn("strict", prompt)
        self.assertIn("strict_coach", prompt)
        self.assertIn("Practice Dutch for customer support", prompt)

    def test_memory_disabled_excludes_memory_from_prompt(self):
        self.profile1.is_memory_enabled = False
        self.profile1.previous_conversation_summary = "Talked about holidays last time."
        self.profile1.weak_areas = ["past tense"]
        self.profile1.save(
            update_fields=["is_memory_enabled", "previous_conversation_summary", "weak_areas", "updated_at"]
        )
        settings_obj, _ = BuddySettings.objects.get_or_create(profile=self.profile1)

        context = build_session_context(self.profile1, settings_obj)
        prompt = context.system_prompt
        self.assertIn("Memory: disabled", prompt)
        self.assertNotIn("Talked about holidays last time.", prompt)
        self.assertNotIn("past tense", prompt)

    def test_memory_enabled_includes_memory_in_prompt(self):
        self.profile1.is_memory_enabled = True
        self.profile1.previous_conversation_summary = "Talked about holidays last time."
        self.profile1.save(update_fields=["is_memory_enabled", "previous_conversation_summary", "updated_at"])
        settings_obj, _ = BuddySettings.objects.get_or_create(profile=self.profile1)

        context = build_session_context(self.profile1, settings_obj)
        prompt = context.system_prompt
        self.assertIn("Memory: enabled", prompt)
        self.assertIn("Talked about holidays last time.", prompt)
