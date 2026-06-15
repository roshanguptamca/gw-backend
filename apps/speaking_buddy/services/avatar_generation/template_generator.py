from ...models import Buddy3DAvatar


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
        avatar.generated_thumbnail = ""
        avatar.generated_thumbnail_url = ""
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
