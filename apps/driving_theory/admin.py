from django.contrib import admin

from .models import (
    DrivingLesson,
    DrivingLessonSection,
    DrivingQuestion,
    DrivingQuestionOption,
    DrivingTopic,
    MockTestAnswer,
    MockTestAttempt,
    UserDrivingProgress,
)


@admin.register(DrivingTopic)
class DrivingTopicAdmin(admin.ModelAdmin):
    list_display = ("title", "slug", "difficulty_level", "exam_weight", "icon", "order", "is_active", "created_at")
    list_filter = ("is_active", "difficulty_level")
    search_fields = ("title", "slug")
    ordering = ("order",)
    readonly_fields = ("created_at",)


@admin.register(DrivingLesson)
class DrivingLessonAdmin(admin.ModelAdmin):
    list_display = ("title", "topic", "difficulty", "estimated_minutes", "order", "is_active")
    list_filter = ("difficulty", "is_active", "topic")
    search_fields = ("title", "summary", "topic__title")
    ordering = ("topic__order", "order")


@admin.register(DrivingLessonSection)
class DrivingLessonSectionAdmin(admin.ModelAdmin):
    list_display = ("title", "lesson", "illustration_hint", "order")
    search_fields = ("title", "lesson__title")
    ordering = ("lesson__topic__order", "lesson__order", "order")


class DrivingQuestionOptionInline(admin.TabularInline):
    model = DrivingQuestionOption
    extra = 0


@admin.register(DrivingQuestion)
class DrivingQuestionAdmin(admin.ModelAdmin):
    list_display = ("question_text", "topic", "lesson", "difficulty", "question_type", "points", "is_active")
    list_filter = ("difficulty", "is_active", "topic", "question_type")
    search_fields = ("question_text", "explanation", "topic__title")
    inlines = [DrivingQuestionOptionInline]


@admin.register(DrivingQuestionOption)
class DrivingQuestionOptionAdmin(admin.ModelAdmin):
    list_display = ("option_text", "question", "is_correct", "order")
    list_filter = ("is_correct",)
    search_fields = ("option_text", "question__question_text")


@admin.register(UserDrivingProgress)
class UserDrivingProgressAdmin(admin.ModelAdmin):
    list_display = ("user", "topic", "lesson", "questions_answered", "questions_correct", "last_accessed")
    list_filter = ("topic",)
    search_fields = ("user__username", "topic__title")


class MockTestAnswerInline(admin.TabularInline):
    model = MockTestAnswer
    extra = 0
    readonly_fields = ("question", "selected_option", "is_correct")


@admin.register(MockTestAttempt)
class MockTestAttemptAdmin(admin.ModelAdmin):
    list_display = ("user", "attempt_number", "score", "passed", "correct_answers", "total_questions", "started_at")
    list_filter = ("passed",)
    search_fields = ("user__username",)
    inlines = [MockTestAnswerInline]


@admin.register(MockTestAnswer)
class MockTestAnswerAdmin(admin.ModelAdmin):
    list_display = ("attempt", "question", "selected_option", "is_correct")
    list_filter = ("is_correct",)
    search_fields = ("attempt__user__username", "question__question_text")
