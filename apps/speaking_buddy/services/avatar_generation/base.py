from django.conf import settings

from ...models import BuddyGeneratedAvatar
from .image_analysis import ImageAnalysisService
from .template_generator import TemplateAvatarGenerator


class AvatarGenerationError(Exception):
    pass


class AvatarGenerationService:
    generators = {
        "template": TemplateAvatarGenerator,
    }

    def generate_from_photo(self, *, user, image, consent_confirmed, options=None):
        if not consent_confirmed:
            raise AvatarGenerationError("consent_required")

        options = options or {}
        provider = options.get("provider") or getattr(settings, "AVATAR_GENERATION_PROVIDER", "template")
        if provider == "stub":
            provider = "template"
        experimental = getattr(settings, "ENABLE_EXPERIMENTAL_IMAGE_TO_3D", False)
        if provider != "template" and not experimental:
            provider = "template"

        avatar = BuddyGeneratedAvatar.objects.create(
            user=user,
            source_image=image,
            provider=provider,
            generation_method=provider,
            status="uploaded",
            consent_confirmed=True,
            user_generated=True,
            is_active=False,
        )
        return self._run(avatar, options)

    def regenerate(self, avatar, options=None):
        if not avatar.consent_confirmed or not avatar.source_image:
            raise AvatarGenerationError("source_image_required")
        return self._run(avatar, options or {})

    def _run(self, avatar, options):
        avatar.status = "processing"
        avatar.generation_logs = "Generation started."
        avatar.save(update_fields=["status", "generation_logs", "updated_at"])
        try:
            avatar.source_image.open("rb")
            detected = ImageAnalysisService().analyze_photo(avatar.source_image)
            avatar.source_image.seek(0)
            generator_class = self.generators.get(avatar.generation_method, TemplateAvatarGenerator)
            return generator_class().generate(avatar, detected, options)
        except Exception as exc:
            avatar.status = "failed"
            avatar.generation_logs = f"{avatar.generation_logs}\nGeneration failed: {exc}".strip()
            avatar.save(update_fields=["status", "generation_logs", "updated_at"])
            raise AvatarGenerationError("generation_failed") from exc
