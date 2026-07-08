from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


def default_list():
    return []


def default_dict():
    return {}


LANGUAGE_CHOICES = [
    ("en", "English"),
    ("nl", "Dutch"),
    ("hi", "Hindi"),
    ("ur", "Urdu"),
    ("ar", "Arabic"),
    ("es", "Spanish"),
    ("fr", "French"),
    ("de", "German"),
    ("other", "Other"),
]

SPEAKING_LEVEL_CHOICES = [
    ("beginner", "Beginner"),
    ("elementary", "Elementary"),
    ("intermediate", "Intermediate"),
    ("upper_intermediate", "Upper Intermediate"),
    ("advanced", "Advanced"),
]

PERSONALITY_CHOICES = [
    ("friendly", "Friendly"),
    ("teacher", "Teacher"),
    ("interviewer", "Interviewer"),
    ("strict_coach", "Strict Coach"),
    ("casual_friend", "Casual Friend"),
]

VOICE_STYLE_CHOICES = [
    ("warm", "Warm"),
    ("clear", "Clear"),
    ("calm", "Calm"),
    ("energetic", "Energetic"),
]

VOICE_GENDER_CHOICES = [
    ("male", "Male"),
    ("female", "Female"),
    ("neutral", "Neutral"),
]

VOICE_AGE_CHOICES = [
    ("young", "Young"),
    ("adult", "Adult"),
    ("senior", "Senior"),
]

OPENAI_VOICE_CHOICES = [
    ("marin", "Female Adult (legacy)"),
    ("cedar", "Male Adult (legacy)"),
    ("alloy", "Alloy (Neutral/Female Adult)"),
    ("shimmer", "Shimmer (Female Young)"),
    ("nova", "Nova (Female Senior)"),
    ("echo", "Echo (Male Adult/Young)"),
    ("onyx", "Onyx (Male Senior)"),
]

CORRECTION_LEVEL_CHOICES = [
    ("none", "None"),
    ("light", "Light"),
    ("normal", "Normal"),
    ("strict", "Strict"),
]

DIFFICULTY_LEVEL_CHOICES = [
    ("easy", "Easy"),
    ("medium", "Medium"),
    ("hard", "Hard"),
]

AVATAR_TYPE_CHOICES = [
    ("default", "Default"),
    ("uploaded", "Uploaded"),
]

AVATAR_RENDER_MODE_CHOICES = [
    ("2d", "2D"),
    ("3d", "3D"),
    ("generated_3d", "Generated 3D"),
]

GENERATED_AVATAR_STATUS_CHOICES = [
    ("uploaded", "Uploaded"),
    ("processing", "Processing"),
    ("completed", "Completed"),
    ("failed", "Failed"),
]

AVATAR_GENERATION_METHOD_CHOICES = [
    ("template", "Template"),
    ("triposr", "TripoSR"),
    ("instantmesh", "InstantMesh"),
    ("pifuhd", "PIFuHD"),
    ("pshuman", "PSHuman"),
    ("mock", "Mock"),
]

SESSION_STATUS_CHOICES = [
    ("active", "Active"),
    ("ended", "Ended"),
]

MESSAGE_ROLE_CHOICES = [
    ("system", "System"),
    ("user", "User"),
    ("assistant", "Assistant"),
]

MEMORY_TYPE_CHOICES = [
    ("summary", "Summary"),
    ("weak_area", "Weak Area"),
    ("vocabulary", "Vocabulary"),
    ("topic", "Topic"),
    ("correction_style", "Correction Style"),
    ("note", "Note"),
]

NEXT_LESSON_STATUS_CHOICES = [
    ("pending", "Pending"),
    ("started", "Started"),
    ("completed", "Completed"),
    ("skipped", "Skipped"),
]

SCENARIO_CATEGORY_CHOICES = [
    ("government", "Government / Gemeente"),
    ("healthcare", "Healthcare"),
    ("education", "Education"),
    ("work", "Work"),
    ("customer_service", "Customer Service"),
    ("food", "Food & Dining"),
    ("shopping", "Shopping"),
    ("travel", "Travel"),
    ("driving", "Driving"),
    ("daily_life", "Daily Life"),
    ("business", "Business"),
    ("presentation", "Presentation"),
]

WEAK_AREA_TYPE_CHOICES = [
    ("grammar", "Grammar"),
    ("vocabulary", "Vocabulary"),
    ("fluency", "Fluency"),
    ("pronunciation", "Pronunciation"),
    ("listening", "Listening"),
    ("confidence", "Confidence"),
]

WEAK_AREA_SEVERITY_CHOICES = [
    ("low", "Low"),
    ("medium", "Medium"),
    ("high", "High"),
]

WEAK_AREA_STATUS_CHOICES = [
    ("active", "Active"),
    ("improving", "Improving"),
    ("resolved", "Resolved"),
]

VOCAB_REVIEW_STATUS_CHOICES = [
    ("new", "New"),
    ("learning", "Learning"),
    ("mastered", "Mastered"),
]


class BuddyProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="speaking_buddy_profile",
    )
    buddy_name = models.CharField(max_length=120, default="GuideWisey Buddy")
    native_language = models.CharField(max_length=20, choices=LANGUAGE_CHOICES, default="en")
    target_language = models.CharField(max_length=20, choices=LANGUAGE_CHOICES, default="en")
    speaking_level = models.CharField(max_length=30, choices=SPEAKING_LEVEL_CHOICES, default="intermediate")
    learning_goal = models.CharField(max_length=255, blank=True)
    favorite_topics = models.JSONField(default=default_list, blank=True)
    weak_areas = models.JSONField(default=default_list, blank=True)
    preferred_correction_style = models.CharField(max_length=40, default="normal")
    is_memory_enabled = models.BooleanField(default=True)
    previous_conversation_summary = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.buddy_name} ({self.user_id})"


class BuddySettings(models.Model):
    profile = models.OneToOneField(BuddyProfile, on_delete=models.CASCADE, related_name="buddy_settings")
    personality = models.CharField(max_length=40, choices=PERSONALITY_CHOICES, default="friendly")
    voice_style = models.CharField(max_length=40, choices=VOICE_STYLE_CHOICES, default="warm")
    voice_gender = models.CharField(max_length=20, choices=VOICE_GENDER_CHOICES, default="neutral")
    voice_age = models.CharField(max_length=20, choices=VOICE_AGE_CHOICES, default="adult")
    selected_voice = models.CharField(max_length=20, choices=OPENAI_VOICE_CHOICES, default="marin")
    speaking_speed = models.PositiveSmallIntegerField(
        default=50, validators=[MinValueValidator(20), MaxValueValidator(120)]
    )
    correction_level = models.CharField(max_length=20, choices=CORRECTION_LEVEL_CHOICES, default="normal")
    difficulty_level = models.CharField(max_length=20, choices=DIFFICULTY_LEVEL_CHOICES, default="medium")
    theme_color = models.CharField(max_length=24, default="#7c3aed")
    default_topic = models.CharField(max_length=255, blank=True)
    kids_mode = models.BooleanField(default=False)
    avatar_render_mode = models.CharField(max_length=20, choices=AVATAR_RENDER_MODE_CHOICES, default="2d")
    selected_3d_avatar_slug = models.SlugField(max_length=120, blank=True)
    selected_generated_avatar = models.ForeignKey(
        "BuddyGeneratedAvatar",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    selected_avatar = models.ForeignKey(
        "Buddy3DAvatar",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="selected_by_settings",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"BuddySettings({self.profile_id})"


class BuddyAvatar(models.Model):
    profile = models.ForeignKey(BuddyProfile, on_delete=models.CASCADE, related_name="avatars")
    avatar_type = models.CharField(max_length=20, choices=AVATAR_TYPE_CHOICES, default="default")
    name = models.CharField(max_length=120, blank=True)
    image = models.ImageField(upload_to="speaking_buddy/avatars/", blank=True, null=True)
    image_url = models.URLField(max_length=500, blank=True)
    consent_confirmed = models.BooleanField(default=False)
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name or f"{self.avatar_type} avatar"


class Buddy3DAvatar(models.Model):
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=120, unique=True)
    gender_style = models.CharField(max_length=40, blank=True)
    age_style = models.CharField(max_length=40, blank=True)
    personality = models.CharField(max_length=40, blank=True)
    default_voice = models.CharField(max_length=120, blank=True)
    voice_style = models.CharField(max_length=40, blank=True)
    mood = models.CharField(max_length=40, blank=True)
    backstory = models.TextField(blank=True)
    thumbnail = models.TextField(blank=True)
    glb_file = models.CharField(max_length=1000, blank=True)
    model_url = models.CharField(max_length=1000, blank=True)
    thumbnail_url = models.CharField(max_length=1000, blank=True)
    base_skin_material_key = models.CharField(max_length=120, blank=True)
    base_hair_material_key = models.CharField(max_length=120, blank=True)
    supported_customizations = models.JSONField(default=default_dict, blank=True)
    supported_blendshapes = models.JSONField(default=default_dict, blank=True)
    has_full_body = models.BooleanField(default=True)
    has_hair = models.BooleanField(default=True)
    has_hands = models.BooleanField(default=True)
    has_feet = models.BooleanField(default=True)
    idle_animation = models.CharField(max_length=120, blank=True)
    talking_animation = models.CharField(max_length=120, blank=True)
    listening_animation = models.CharField(max_length=120, blank=True)
    thinking_animation = models.CharField(max_length=120, blank=True)
    emotion_set = models.JSONField(default=default_dict, blank=True)
    is_premium = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class BuddyGeneratedAvatar(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="generated_buddy_avatars")
    source_image = models.ImageField(upload_to="speaking_buddy/generated_sources/", blank=True, null=True)
    generated_glb_url = models.CharField(max_length=1000, blank=True)
    generated_thumbnail_url = models.CharField(max_length=1000, blank=True)
    generated_model_path = models.CharField(max_length=1000, blank=True)
    generated_thumbnail = models.CharField(max_length=1000, blank=True)
    appearance_config = models.JSONField(default=default_dict, blank=True)
    detected_features = models.JSONField(default=default_dict, blank=True)
    generation_logs = models.TextField(blank=True)
    generation_method = models.CharField(
        max_length=20,
        choices=AVATAR_GENERATION_METHOD_CHOICES,
        default="template",
    )
    provider = models.CharField(max_length=80, blank=True)
    provider_job_id = models.CharField(max_length=120, blank=True)
    status = models.CharField(max_length=20, choices=GENERATED_AVATAR_STATUS_CHOICES, default="uploaded")
    selected_base_avatar = models.ForeignKey(
        Buddy3DAvatar,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="generated_variants",
    )
    consent_confirmed = models.BooleanField(default=False)
    user_generated = models.BooleanField(default=True)
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Generated avatar({self.user_id}, {self.status})"


class BuddySession(models.Model):
    profile = models.ForeignKey(BuddyProfile, on_delete=models.CASCADE, related_name="sessions")
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    language = models.CharField(max_length=20, choices=LANGUAGE_CHOICES, default="en")
    topic = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=20, choices=SESSION_STATUS_CHOICES, default="active")
    selected_voice = models.CharField(max_length=20, choices=OPENAI_VOICE_CHOICES, default="marin")
    duration_seconds = models.PositiveIntegerField(default=0)
    transcript = models.JSONField(default=default_list, blank=True)
    ai_summary = models.TextField(blank=True)
    user_summary = models.TextField(blank=True)
    mistakes_detected = models.JSONField(default=default_list, blank=True)
    vocabulary_practiced = models.JSONField(default=default_list, blank=True)
    improvement_notes = models.TextField(blank=True)
    selected_avatar = models.ForeignKey(
        Buddy3DAvatar,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sessions",
    )
    selected_scenario = models.ForeignKey(
        "BuddyScenario",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sessions",
    )
    emotion_timeline = models.JSONField(default=default_list, blank=True)
    usage_counted = models.BooleanField(default=False)
    end_reason = models.CharField(max_length=40, blank=True)
    client_closed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"BuddySession({self.profile_id}, {self.status})"


class BuddyUsageQuota(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="speaking_buddy_usage_quota",
    )
    free_conversation_limit = models.PositiveSmallIntegerField(default=100)
    conversations_used = models.PositiveIntegerField(default=0)
    last_reset_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"BuddyUsageQuota({self.user_id})"

    @property
    def conversations_remaining(self):
        return max(self.free_conversation_limit - self.conversations_used, 0)


class BuddyMessage(models.Model):
    session = models.ForeignKey(BuddySession, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=20, choices=MESSAGE_ROLE_CHOICES)
    text = models.TextField()
    audio_url = models.URLField(max_length=500, blank=True)
    metadata = models.JSONField(default=default_dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.role}:{self.session_id}"


class BuddyMemory(models.Model):
    profile = models.ForeignKey(BuddyProfile, on_delete=models.CASCADE, related_name="memories")
    memory_type = models.CharField(max_length=40, choices=MEMORY_TYPE_CHOICES, default="note")
    key = models.CharField(max_length=120)
    value = models.JSONField(default=default_dict, blank=True)
    importance = models.PositiveSmallIntegerField(default=1, validators=[MinValueValidator(1), MaxValueValidator(5)])
    source_session = models.ForeignKey(
        BuddySession,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="memory_entries",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("profile", "memory_type", "key")]

    def __str__(self):
        return f"{self.memory_type}:{self.key}"


class BuddyPracticeTopic(models.Model):
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    language = models.CharField(max_length=20, choices=LANGUAGE_CHOICES, default="en")
    level = models.CharField(max_length=30, choices=SPEAKING_LEVEL_CHOICES, default="intermediate")
    category = models.CharField(max_length=120, blank=True)
    prompt_template = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title


class BuddyVocabulary(models.Model):
    profile = models.ForeignKey(BuddyProfile, on_delete=models.CASCADE, related_name="vocabulary")
    word = models.CharField(max_length=120)
    translation = models.CharField(max_length=255, blank=True)
    example_sentence = models.TextField(blank=True)
    language = models.CharField(max_length=20, choices=LANGUAGE_CHOICES, default="en")
    confidence_score = models.PositiveSmallIntegerField(
        default=0, validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    review_status = models.CharField(max_length=20, choices=VOCAB_REVIEW_STATUS_CHOICES, default="new")
    next_review_at = models.DateTimeField(null=True, blank=True)
    review_count = models.PositiveIntegerField(default=0)
    last_result = models.CharField(max_length=20, blank=True)
    last_practiced_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("profile", "word", "language")]

    def __str__(self):
        return self.word


class BuddyMistake(models.Model):
    profile = models.ForeignKey(BuddyProfile, on_delete=models.CASCADE, related_name="mistakes")
    session = models.ForeignKey(BuddySession, null=True, blank=True, on_delete=models.SET_NULL, related_name="mistakes")
    original_text = models.TextField(blank=True)
    corrected_text = models.TextField(blank=True)
    explanation = models.TextField(blank=True)
    mistake_type = models.CharField(max_length=120, blank=True)
    language = models.CharField(max_length=20, choices=LANGUAGE_CHOICES, default="en")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.mistake_type or f"Mistake({self.profile_id})"


class BuddyScenario(models.Model):
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=160, unique=True)
    description = models.TextField(blank=True)
    language = models.CharField(max_length=20, choices=LANGUAGE_CHOICES, default="en")
    category = models.CharField(max_length=40, choices=SCENARIO_CATEGORY_CHOICES, default="daily_life")
    level = models.CharField(max_length=30, choices=SPEAKING_LEVEL_CHOICES, default="intermediate")
    system_prompt = models.TextField(blank=True)
    opening_message = models.TextField(blank=True)
    expected_skills = models.JSONField(default=default_list, blank=True)
    vocabulary_focus = models.JSONField(default=default_list, blank=True)
    is_kids_safe = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["language", "category", "title"]

    def __str__(self):
        return f"{self.title} ({self.language})"


class BuddySessionReport(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="buddy_session_reports")
    session = models.OneToOneField(BuddySession, on_delete=models.CASCADE, related_name="report")
    overall_score = models.PositiveSmallIntegerField(
        default=0, validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    fluency_score = models.PositiveSmallIntegerField(
        default=0, validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    grammar_score = models.PositiveSmallIntegerField(
        default=0, validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    vocabulary_score = models.PositiveSmallIntegerField(
        default=0, validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    confidence_score = models.PositiveSmallIntegerField(
        default=0, validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    completeness_score = models.PositiveSmallIntegerField(
        default=0, validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    strengths = models.JSONField(default=default_list, blank=True)
    improvement_points = models.JSONField(default=default_list, blank=True)
    corrected_sentences = models.JSONField(default=default_list, blank=True)
    vocabulary_learned = models.JSONField(default=default_list, blank=True)
    next_practice_recommendation = models.TextField(blank=True)
    report_summary = models.TextField(blank=True)
    is_fallback = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Report(session={self.session_id}, score={self.overall_score})"


class BuddyNextLesson(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="buddy_next_lessons")
    profile = models.ForeignKey(BuddyProfile, on_delete=models.CASCADE, related_name="next_lessons")
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    target_language = models.CharField(max_length=20, choices=LANGUAGE_CHOICES, default="en")
    level = models.CharField(max_length=30, choices=SPEAKING_LEVEL_CHOICES, default="intermediate")
    focus_areas = models.JSONField(default=default_list, blank=True)
    recommended_scenarios = models.JSONField(default=default_list, blank=True)
    vocabulary_to_review = models.JSONField(default=default_list, blank=True)
    mistakes_to_fix = models.JSONField(default=default_list, blank=True)
    status = models.CharField(max_length=20, choices=NEXT_LESSON_STATUS_CHOICES, default="pending")
    created_from_report = models.ForeignKey(
        BuddySessionReport,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="generated_lessons",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"NextLesson({self.user_id}, {self.status})"


class BuddyWeakArea(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="buddy_weak_areas")
    profile = models.ForeignKey(BuddyProfile, on_delete=models.CASCADE, related_name="weak_area_records")
    area_type = models.CharField(max_length=30, choices=WEAK_AREA_TYPE_CHOICES, default="grammar")
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    language = models.CharField(max_length=20, choices=LANGUAGE_CHOICES, default="en")
    severity = models.CharField(max_length=20, choices=WEAK_AREA_SEVERITY_CHOICES, default="medium")
    evidence = models.JSONField(default=default_list, blank=True)
    improvement_plan = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=WEAK_AREA_STATUS_CHOICES, default="active")
    last_seen_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("profile", "area_type", "title", "language")]
        ordering = ["-severity", "-updated_at"]

    def __str__(self):
        return f"{self.area_type}:{self.title}"
