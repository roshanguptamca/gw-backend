from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.speaking_buddy.models import (
    Buddy3DAvatar,
    BuddyAvatar,
    BuddyGeneratedAvatar,
    BuddyMemory,
    BuddyMessage,
    BuddyMistake,
    BuddyPracticeTopic,
    BuddyProfile,
    BuddySession,
    BuddySettings,
    BuddyVocabulary,
)

User = get_user_model()


class SpeakingBuddyModelTests(TestCase):
    def test_core_models_can_be_created(self):
        user = User.objects.create_user("buddy", "buddy@example.com", "password")
        profile = BuddyProfile.objects.create(user=user, buddy_name="Buddy", target_language="nl")
        settings = BuddySettings.objects.create(profile=profile)
        avatar = BuddyAvatar.objects.create(profile=profile, avatar_type="default", name="Default", is_active=True)
        avatar_3d = Buddy3DAvatar.objects.create(
            name="Nova 3D",
            slug="nova-3d",
            gender_style="neutral",
            age_style="adult",
            personality="friendly",
            voice_style="warm",
            thumbnail="data:image/svg+xml,%3Csvg/%3E",
            glb_file="https://example.com/model.glb",
            idle_animation="Idle",
            talking_animation="Talk",
        )
        generated = BuddyGeneratedAvatar.objects.create(user=user, consent_confirmed=True, provider="stub", provider_job_id="job-1")
        session = BuddySession.objects.create(profile=profile, language="nl", topic="Travel", status="active")
        message = BuddyMessage.objects.create(session=session, role="user", text="Hoi!")
        memory = BuddyMemory.objects.create(profile=profile, memory_type="summary", key="session-1", value={"text": "Hi"})
        topic = BuddyPracticeTopic.objects.create(title="Travel", language="nl", level="beginner")
        vocab = BuddyVocabulary.objects.create(profile=profile, word="trein", translation="train", language="nl")
        mistake = BuddyMistake.objects.create(profile=profile, session=session, original_text="Ik zijn", corrected_text="Ik ben", mistake_type="grammar")

        self.assertEqual(profile.user, user)
        self.assertEqual(settings.profile, profile)
        self.assertEqual(avatar.profile, profile)
        self.assertEqual(avatar_3d.slug, "nova-3d")
        self.assertEqual(generated.user, user)
        self.assertEqual(session.profile, profile)
        self.assertEqual(message.session, session)
        self.assertEqual(memory.profile, profile)
        self.assertEqual(topic.title, "Travel")
        self.assertEqual(vocab.word, "trein")
        self.assertEqual(mistake.session, session)

    def test_admin_registers_speaking_buddy_models(self):
        for model in (
            BuddyProfile,
            BuddySettings,
            BuddyAvatar,
            Buddy3DAvatar,
            BuddyGeneratedAvatar,
            BuddySession,
            BuddyMessage,
            BuddyMemory,
            BuddyPracticeTopic,
            BuddyVocabulary,
            BuddyMistake,
        ):
            self.assertIn(model, admin.site._registry)
