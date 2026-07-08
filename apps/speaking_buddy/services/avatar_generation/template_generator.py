from ...models import Buddy3DAvatar

# Real, existing human-like illustration assets used as a last-resort
# thumbnail when Cloudinary isn't configured (e.g. local dev without
# credentials) and the selected 3D template has no thumbnail_url of its own.
# These are genuine designed avatar images — never a generic icon.
_FALLBACK_HUMAN_THUMBNAILS = [
    "/assets/images/speaking-buddy/avatar-nova.svg",
    "/assets/images/speaking-buddy/avatar-mila.svg",
    "/assets/images/speaking-buddy/avatar-rio.svg",
]


class TemplateAvatarGenerator:
    def select_base_avatar(self, detected, options):
        queryset = Buddy3DAvatar.objects.filter(
            is_active=True,
            has_full_body=True,
            has_hair=True,
            has_hands=True,
            has_feet=True,
        )
        gender = options.get("preferred_gender_style")
        age = options.get("preferred_age_style")
        if gender:
            queryset = queryset.filter(gender_style=gender)
        if age:
            age_match = queryset.filter(age_style=age).first()
            if age_match:
                return age_match
        return queryset.first() or Buddy3DAvatar.objects.filter(is_active=True).first()

    def build_appearance_config(self, base_avatar, detected, options):
        hair_style = options.get("preferred_hair_style") or detected["hair_style_hint"]
        outfit = options.get("preferred_outfit_style") or "smart-casual"
        return {
            "base_avatar_slug": base_avatar.slug,
            "skin_material": detected["skin_tone"],
            "hair_material": detected["hair_color"],
            "eye_material": detected["eye_color_hint"],
            "hair_mesh": hair_style if detected["hair_presence"] else "close-crop",
            "beard_mesh": "short-beard" if detected["beard_detected"] else "none",
            "glasses_mesh": "classic-frames" if detected["glasses_detected"] else "none",
            "body_type": "balanced",
            "outfit_style": outfit,
            "outfit_color": "#245c73",
            "trouser_color": "#263447",
            "shoe_color": "#171c24",
            "final_model_url": base_avatar.model_url,
            "customization_applied": True,
            "face_shape_hint": detected["face_shape_hint"],
            "realism_level": options.get("realism_level") or "balanced",
        }

    def _fallback_thumbnail(self, base_avatar, avatar_id):
        if base_avatar.thumbnail_url:
            return base_avatar.thumbnail_url
        return _FALLBACK_HUMAN_THUMBNAILS[avatar_id % len(_FALLBACK_HUMAN_THUMBNAILS)]

    def generate(self, avatar, detected, options):
        base_avatar = self.select_base_avatar(detected, options)
        if not base_avatar:
            raise RuntimeError("No full-body human base avatar is active.")
        appearance = self.build_appearance_config(base_avatar, detected, options)
        avatar.selected_base_avatar = base_avatar
        avatar.detected_features = detected
        avatar.appearance_config = appearance
        avatar.generated_model_path = base_avatar.model_url
        avatar.generated_glb_url = base_avatar.model_url
        # A Cloudinary-hosted face-cropped thumbnail may already be set by
        # AvatarGenerationService._sync_source_photo_to_cloudinary(); only
        # fall back to a template/static thumbnail if that didn't happen, so
        # we never leave the avatar with no usable preview image at all.
        if not avatar.generated_thumbnail_url:
            avatar.generated_thumbnail_url = self._fallback_thumbnail(base_avatar, avatar.id or 0)
        avatar.generated_thumbnail = avatar.generated_thumbnail_url
        avatar.generation_method = "template"
        avatar.provider = "template"
        avatar.status = "completed"
        avatar.generation_logs = (
            "Generation started.\n"
            f"Analyzer: {detected['analyzer']}.\n"
            f"Selected full-body base avatar: {base_avatar.slug}.\n"
            "Applied skin, hair, eye, face, accessory, body, and outfit configuration."
        )
        avatar.save()
        return avatar
