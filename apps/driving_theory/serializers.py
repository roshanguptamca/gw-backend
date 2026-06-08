import random

from rest_framework import serializers

from .models import (
    DrivingLesson,
    DrivingLessonSection,
    DrivingQuestion,
    DrivingQuestionOption,
    DrivingTopic,
    MockTestAttempt,
    UserDrivingProgress,
)


class DrivingLessonSectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = DrivingLessonSection
        fields = [
            "id", "title", "content", "examples", "dutch_keywords",
            "callout_boxes", "illustration_hint", "order",
        ]
        read_only_fields = fields


class DrivingQuestionOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = DrivingQuestionOption
        fields = ["id", "option_text", "is_correct"]
        read_only_fields = fields

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.context.get("hide_correct_answers"):
            self.fields.pop("is_correct", None)


class DrivingQuestionSerializer(serializers.ModelSerializer):
    options = serializers.SerializerMethodField()

    class Meta:
        model = DrivingQuestion
        fields = ["id", "question_text", "explanation", "difficulty", "question_type", "sign_hint", "points", "options"]
        read_only_fields = fields

    def get_options(self, obj):
        options = list(obj.options.all())
        rng = random.Random()
        rng.shuffle(options)
        return DrivingQuestionOptionSerializer(options, many=True, context=self.context).data


class DrivingLessonSerializer(serializers.ModelSerializer):
    sections = DrivingLessonSectionSerializer(many=True, read_only=True)

    class Meta:
        model = DrivingLesson
        fields = [
            "id", "title", "summary", "difficulty", "estimated_minutes",
            "learning_objectives", "exam_tips", "common_mistakes", "key_takeaways",
            "sections",
        ]
        read_only_fields = fields


class DrivingLessonDetailSerializer(DrivingLessonSerializer):
    questions = serializers.SerializerMethodField()
    topic_slug = serializers.SlugField(source="topic.slug", read_only=True)
    topic_title = serializers.CharField(source="topic.title", read_only=True)

    class Meta(DrivingLessonSerializer.Meta):
        fields = DrivingLessonSerializer.Meta.fields + ["topic_slug", "topic_title", "questions"]
        read_only_fields = fields

    def get_questions(self, obj):
        questions = obj.questions.filter(is_active=True).prefetch_related("options")
        return DrivingQuestionSerializer(questions, many=True, context=self.context).data


class DrivingTopicListSerializer(serializers.ModelSerializer):
    question_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = DrivingTopic
        fields = [
            "id", "slug", "title", "summary", "icon", "color_theme",
            "difficulty_level", "learning_objectives", "exam_weight",
            "order", "question_count",
        ]
        read_only_fields = fields


class DrivingTopicDetailSerializer(serializers.ModelSerializer):
    lessons = DrivingLessonSerializer(many=True, read_only=True)

    class Meta:
        model = DrivingTopic
        fields = [
            "id", "slug", "title", "summary", "dutch_terms", "icon",
            "color_theme", "difficulty_level", "learning_objectives",
            "exam_weight", "order", "is_active", "created_at", "lessons",
        ]
        read_only_fields = fields


class MockTestAttemptSerializer(serializers.ModelSerializer):
    class Meta:
        model = MockTestAttempt
        fields = ["id", "attempt_number", "started_at", "score", "passed", "total_questions", "correct_answers"]
        read_only_fields = fields


class ProgressUpdateSerializer(serializers.Serializer):
    topic_slug = serializers.SlugField()
    lesson_id = serializers.IntegerField(required=False, allow_null=True)
    lesson_completed = serializers.BooleanField(required=False, default=False)
    question_id = serializers.IntegerField(required=False, allow_null=True)
    answer_correct = serializers.BooleanField(required=False, default=False)


class UserDrivingProgressSerializer(serializers.ModelSerializer):
    topic_slug = serializers.SlugField(source="topic.slug", read_only=True)
    topic_title = serializers.CharField(source="topic.title", read_only=True)
    topic_icon = serializers.CharField(source="topic.icon", read_only=True)
    total_lessons = serializers.SerializerMethodField()
    completion_percentage = serializers.SerializerMethodField()
    accuracy_percentage = serializers.SerializerMethodField()

    class Meta:
        model = UserDrivingProgress
        fields = [
            "id",
            "topic_slug",
            "topic_title",
            "topic_icon",
            "lesson",
            "lessons_completed",
            "questions_answered",
            "questions_correct",
            "total_lessons",
            "completion_percentage",
            "accuracy_percentage",
            "last_accessed",
        ]
        read_only_fields = fields

    def get_total_lessons(self, obj):
        return obj.topic.lessons.filter(is_active=True).count()

    def get_completion_percentage(self, obj):
        total_lessons = self.get_total_lessons(obj)
        if total_lessons == 0:
            return 0
        return round((len(obj.lessons_completed or []) / total_lessons) * 100, 2)

    def get_accuracy_percentage(self, obj):
        if obj.questions_answered == 0:
            return 0
        return round((obj.questions_correct / obj.questions_answered) * 100, 2)


class MockTestAnswerInputSerializer(serializers.Serializer):
    question_id = serializers.IntegerField()
    option_id = serializers.IntegerField(required=False, allow_null=True)


class MockTestSubmitSerializer(serializers.Serializer):
    answers = MockTestAnswerInputSerializer(many=True)
