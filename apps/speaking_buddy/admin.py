from django.contrib import admin

from .models import (
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


class BuddySettingsInline(admin.StackedInline):
    model = BuddySettings
    extra = 0
    max_num = 1


class BuddyAvatarInline(admin.TabularInline):
    model = BuddyAvatar
    extra = 0


class BuddyMemoryInline(admin.TabularInline):
    model = BuddyMemory
    extra = 0


class BuddyVocabularyInline(admin.TabularInline):
    model = BuddyVocabulary
    extra = 0


class BuddyMistakeInline(admin.TabularInline):
    model = BuddyMistake
    extra = 0


@admin.register(BuddyProfile)
class BuddyProfileAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "buddy_name",
        "native_language",
        "target_language",
        "speaking_level",
        "is_memory_enabled",
        "created_at",
        "updated_at",
    )
    search_fields = ("user__username", "user__email", "buddy_name", "learning_goal")
    list_filter = (
        "native_language",
        "target_language",
        "speaking_level",
        "is_memory_enabled",
        "preferred_correction_style",
    )
    readonly_fields = ("created_at", "updated_at")
    inlines = [BuddySettingsInline, BuddyAvatarInline, BuddyMemoryInline, BuddyVocabularyInline, BuddyMistakeInline]


@admin.register(BuddySettings)
class BuddySettingsAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "profile",
        "personality",
        "selected_voice",
        "voice_style",
        "voice_gender",
        "voice_age",
        "correction_level",
        "difficulty_level",
        "created_at",
        "updated_at",
    )
    search_fields = ("profile__user__username", "profile__user__email", "default_topic")
    list_filter = (
        "personality",
        "selected_voice",
        "voice_style",
        "voice_gender",
        "voice_age",
        "correction_level",
        "difficulty_level",
    )
    readonly_fields = ("created_at", "updated_at")


@admin.register(BuddyAvatar)
class BuddyAvatarAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "profile",
        "avatar_type",
        "name",
        "consent_confirmed",
        "is_active",
        "created_at",
        "updated_at",
    )
    search_fields = ("profile__user__username", "profile__user__email", "name")
    list_filter = ("avatar_type", "consent_confirmed", "is_active", "created_at")
    readonly_fields = ("created_at", "updated_at")


@admin.register(Buddy3DAvatar)
class Buddy3DAvatarAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "slug",
        "gender_style",
        "age_style",
        "has_full_body",
        "has_hair",
        "has_hands",
        "has_feet",
        "is_active",
        "created_at",
        "updated_at",
    )
    search_fields = ("name", "slug", "personality", "voice_style", "mood", "backstory")
    list_filter = ("gender_style", "age_style", "has_full_body", "has_hair", "has_hands", "has_feet", "is_active")
    readonly_fields = ("created_at", "updated_at")


@admin.register(BuddyGeneratedAvatar)
class BuddyGeneratedAvatarAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "selected_base_avatar",
        "generation_method",
        "status",
        "consent_confirmed",
        "created_at",
        "updated_at",
    )
    search_fields = ("user__username", "user__email", "provider", "provider_job_id")
    list_filter = ("generation_method", "status", "consent_confirmed", "created_at")
    readonly_fields = ("created_at", "updated_at")


@admin.register(BuddySession)
class BuddySessionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "profile",
        "language",
        "topic",
        "selected_voice",
        "status",
        "duration_seconds",
        "started_at",
        "ended_at",
    )
    search_fields = ("profile__user__username", "profile__user__email", "topic", "ai_summary", "user_summary")
    list_filter = ("language", "selected_voice", "status", "started_at", "ended_at")
    readonly_fields = ("created_at", "updated_at")


@admin.register(BuddyMemory)
class BuddyMemoryAdmin(admin.ModelAdmin):
    list_display = ("id", "profile", "memory_type", "key", "importance", "is_active", "created_at", "updated_at")
    search_fields = ("profile__user__username", "profile__user__email", "key")
    list_filter = ("memory_type", "importance", "is_active", "created_at")
    readonly_fields = ("created_at", "updated_at")


@admin.register(BuddyPracticeTopic)
class BuddyPracticeTopicAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "language", "level", "category", "is_active", "created_at", "updated_at")
    search_fields = ("title", "description", "category")
    list_filter = ("language", "level", "category", "is_active")
    readonly_fields = ("created_at", "updated_at")


@admin.register(BuddyVocabulary)
class BuddyVocabularyAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "profile",
        "word",
        "language",
        "confidence_score",
        "last_practiced_at",
        "created_at",
        "updated_at",
    )
    search_fields = ("profile__user__username", "profile__user__email", "word", "translation")
    list_filter = ("language", "confidence_score", "last_practiced_at")
    readonly_fields = ("created_at", "updated_at")


@admin.register(BuddyMistake)
class BuddyMistakeAdmin(admin.ModelAdmin):
    list_display = ("id", "profile", "session", "mistake_type", "language", "created_at", "updated_at")
    search_fields = (
        "profile__user__username",
        "profile__user__email",
        "mistake_type",
        "original_text",
        "corrected_text",
    )
    list_filter = ("language", "mistake_type", "created_at")
    readonly_fields = ("created_at", "updated_at")


@admin.register(BuddyMessage)
class BuddyMessageAdmin(admin.ModelAdmin):
    list_display = ("id", "session", "role", "created_at", "updated_at")
    search_fields = ("session__profile__user__username", "session__profile__user__email", "text")
    list_filter = ("role", "created_at")
    readonly_fields = ("created_at", "updated_at")
