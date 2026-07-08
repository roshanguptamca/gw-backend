"""Tests for the "Generate avatar from photo" flow on /buddy/settings.

Covers: consent validation, Cloudinary-backed photo upload (mocked),
human-like template assignment, no-fake-icon guarantee, avatar selection,
and that the selected avatar surfaces for buddy sessions via the profile
bundle endpoint that the /buddy call page reads from.
"""

from io import BytesIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from PIL import Image
from rest_framework.test import APIClient

from apps.speaking_buddy.models import Buddy3DAvatar, BuddyGeneratedAvatar, BuddyProfile

User = get_user_model()

CLOUDINARY_TEST_SETTINGS = {
    "CLOUDINARY_CLOUD_NAME": "test-cloud",
    "CLOUDINARY_API_KEY": "test-key",
    "CLOUDINARY_API_SECRET": "test-secret",
}


def make_photo(name="selfie.png"):
    buffer = BytesIO()
    Image.new("RGB", (120, 160), color=(180, 140, 110)).save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


def cloudinary_upload_response(suffix="source"):
    return {
        "secure_url": f"https://res.cloudinary.com/test-cloud/image/upload/buddy_avatars/{suffix}.webp",
        "public_id": f"guidewisey/buddy_avatars/1/1/{suffix}",
        "eager": [
            {
                "secure_url": f"https://res.cloudinary.com/test-cloud/image/upload/c_fill,g_face,h_400,w_400/buddy_avatars/{suffix}-thumb.webp"
            }
        ],
    }


@override_settings(**CLOUDINARY_TEST_SETTINGS)
class PhotoAvatarGenerationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user1 = User.objects.create_user("photoavatar1", "photoavatar1@example.com", "password")
        self.user2 = User.objects.create_user("photoavatar2", "photoavatar2@example.com", "password")
        BuddyProfile.objects.create(user=self.user1, buddy_name="Mila", native_language="en", target_language="nl")
        BuddyProfile.objects.create(user=self.user2, buddy_name="Other", native_language="en", target_language="en")
        # A real human-like, full-body base template — required for the
        # template generator to have something to assign.
        Buddy3DAvatar.objects.create(
            name="Emma",
            slug="emma-3d",
            gender_style="female",
            age_style="adult",
            has_full_body=True,
            has_hair=True,
            has_hands=True,
            has_feet=True,
            is_active=True,
            model_url="/assets/buddy3d/emma.vrm",
            thumbnail_url="",
        )

    def auth(self, user):
        self.client.force_authenticate(user=user)

    def test_upload_without_consent_fails(self):
        self.auth(self.user1)
        response = self.client.post(
            "/api/buddy/generated-avatar/",
            {"source_image": make_photo(), "consent_confirmed": False},
            format="multipart",
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(BuddyGeneratedAvatar.objects.filter(user=self.user1).exists())

    @patch("cloudinary.uploader.upload")
    def test_upload_with_photo_creates_completed_generated_avatar(self, upload_mock):
        upload_mock.return_value = cloudinary_upload_response()
        self.auth(self.user1)
        response = self.client.post(
            "/api/buddy/generated-avatar/",
            {"source_image": make_photo(), "consent_confirmed": True},
            format="multipart",
        )
        self.assertEqual(response.status_code, 201)
        data = response.data
        self.assertEqual(data["status"], "completed")
        self.assertEqual(data["generation_method"], "template")
        self.assertTrue(data["consent_confirmed"])
        self.assertIsNotNone(data["selected_base_avatar"])
        self.assertTrue(data["appearance_config"])
        self.assertTrue(data["detected_features"])
        # A real usable model + a real (non-empty, non-generic-icon) thumbnail.
        self.assertTrue(data["generated_glb_url"] or data["generated_model_path"])
        self.assertTrue(data["generated_thumbnail_url"])
        self.assertIn("cloudinary.com", data["generated_thumbnail_url"])
        self.assertIn("cloudinary.com", data["source_image_url"])
        # Cloudinary was actually invoked (mocked), confirming reuse of the
        # existing Cloudinary upload path rather than only local storage.
        self.assertTrue(upload_mock.called)

    @patch("cloudinary.uploader.upload")
    def test_generated_avatar_appears_in_list(self, upload_mock):
        upload_mock.return_value = cloudinary_upload_response()
        self.auth(self.user1)
        created = self.client.post(
            "/api/buddy/generated-avatar/",
            {"source_image": make_photo(), "consent_confirmed": True},
            format="multipart",
        )
        self.assertEqual(created.status_code, 201)
        listing = self.client.get("/api/buddy/generated-avatar/")
        self.assertEqual(listing.status_code, 200)
        ids = [item["id"] for item in listing.data["generated_avatars"]]
        self.assertIn(created.data["id"], ids)

    @patch("cloudinary.uploader.upload")
    def test_generated_avatar_can_be_selected(self, upload_mock):
        upload_mock.return_value = cloudinary_upload_response()
        self.auth(self.user1)
        created = self.client.post(
            "/api/buddy/generated-avatar/",
            {"source_image": make_photo(), "consent_confirmed": True},
            format="multipart",
        )
        avatar_id = created.data["id"]
        select_response = self.client.post(
            "/api/buddy/avatar-3d/",
            {"generated_avatar_id": avatar_id, "avatar_render_mode": "generated_3d"},
            format="json",
        )
        self.assertEqual(select_response.status_code, 200)
        self.assertEqual(select_response.data["avatar_render_mode"], "generated_3d")
        self.assertEqual(select_response.data["selected_generated_avatar"]["id"], avatar_id)

    @patch("cloudinary.uploader.upload")
    def test_selected_avatar_is_used_by_buddy_session(self, upload_mock):
        upload_mock.return_value = cloudinary_upload_response()
        self.auth(self.user1)
        created = self.client.post(
            "/api/buddy/generated-avatar/",
            {"source_image": make_photo(), "consent_confirmed": True},
            format="multipart",
        )
        avatar_id = created.data["id"]
        self.client.post(
            "/api/buddy/avatar-3d/",
            {"generated_avatar_id": avatar_id, "avatar_render_mode": "generated_3d"},
            format="json",
        )
        # The /buddy call page reads the avatar to render from the profile
        # bundle endpoint — confirm the selected generated avatar surfaces
        # there as the renderable avatar for the session.
        profile_response = self.client.get("/api/buddy/profile/")
        self.assertEqual(profile_response.status_code, 200)
        self.assertEqual(profile_response.data["avatar_render_mode"], "generated_3d")
        renderable = profile_response.data["selected_3d_renderable_avatar"]
        self.assertIsNotNone(renderable)
        self.assertEqual(renderable["id"], avatar_id)
        self.assertTrue(renderable["generated_thumbnail_url"])

    def test_cross_user_cannot_access_generated_avatar(self):
        avatar = BuddyGeneratedAvatar.objects.create(
            user=self.user1,
            provider="template",
            status="completed",
            consent_confirmed=True,
        )
        self.auth(self.user2)
        detail = self.client.get(f"/api/buddy/generated-avatar/{avatar.id}/")
        self.assertEqual(detail.status_code, 404)

    @patch("cloudinary.uploader.upload")
    def test_no_dummy_icon_only_avatar_is_created(self, upload_mock):
        """The generated avatar must always carry a real model + real
        thumbnail — never an empty/blank result that would force the
        frontend to fall back to a generic icon."""
        upload_mock.return_value = cloudinary_upload_response()
        self.auth(self.user1)
        response = self.client.post(
            "/api/buddy/generated-avatar/",
            {"source_image": make_photo(), "consent_confirmed": True},
            format="multipart",
        )
        self.assertEqual(response.status_code, 201)
        avatar = BuddyGeneratedAvatar.objects.get(id=response.data["id"])
        self.assertEqual(avatar.status, "completed")
        self.assertTrue(avatar.generated_glb_url)
        self.assertTrue(avatar.generated_thumbnail_url)
        self.assertIsNotNone(avatar.selected_base_avatar)

    def test_no_dummy_icon_when_cloudinary_not_configured(self):
        """Even without Cloudinary configured (e.g. local dev without
        credentials), generation must still fall back to a real, designed
        human-like thumbnail asset — never a blank/no-image result."""
        with override_settings(CLOUDINARY_CLOUD_NAME="", CLOUDINARY_API_KEY="", CLOUDINARY_API_SECRET=""):
            self.auth(self.user1)
            response = self.client.post(
                "/api/buddy/generated-avatar/",
                {"source_image": make_photo(), "consent_confirmed": True},
                format="multipart",
            )
            self.assertEqual(response.status_code, 201)
            self.assertEqual(response.data["status"], "completed")
            self.assertTrue(response.data["generated_thumbnail_url"])
