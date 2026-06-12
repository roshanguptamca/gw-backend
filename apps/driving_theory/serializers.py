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


class LangMixin:
    def get_lang(self):
        request = self.context.get("request")
        return "nl" if request and request.GET.get("lang") == "nl" else "en"


class DrivingLessonSectionSerializer(LangMixin, serializers.ModelSerializer):
    title = serializers.SerializerMethodField()
    content = serializers.SerializerMethodField()
    examples = serializers.SerializerMethodField()
    callout_boxes = serializers.SerializerMethodField()

    class Meta:
        model = DrivingLessonSection
        fields = [
            "id",
            "title",
            "content",
            "examples",
            "dutch_keywords",
            "callout_boxes",
            "illustration_hint",
            "order",
        ]
        read_only_fields = ["id", "examples", "dutch_keywords", "callout_boxes", "illustration_hint", "order"]

    def get_title(self, obj):
        return obj.title_nl if self.get_lang() == "nl" and obj.title_nl else obj.title

    def get_content(self, obj):
        return obj.content_nl if self.get_lang() == "nl" and obj.content_nl else obj.content

    def get_examples(self, obj):
        return obj.examples_nl if self.get_lang() == "nl" and obj.examples_nl else obj.examples

    def get_callout_boxes(self, obj):
        return obj.callout_boxes_nl if self.get_lang() == "nl" and obj.callout_boxes_nl else obj.callout_boxes


class DrivingQuestionOptionSerializer(LangMixin, serializers.ModelSerializer):
    option_text = serializers.SerializerMethodField()

    class Meta:
        model = DrivingQuestionOption
        fields = ["id", "option_text", "is_correct"]
        read_only_fields = ["id", "is_correct"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.context.get("hide_correct_answers"):
            self.fields.pop("is_correct", None)

    def get_option_text(self, obj):
        return obj.option_text_nl if self.get_lang() == "nl" and obj.option_text_nl else obj.option_text


class DrivingQuestionSerializer(LangMixin, serializers.ModelSerializer):
    question_text = serializers.SerializerMethodField()
    explanation = serializers.SerializerMethodField()
    options = serializers.SerializerMethodField()

    class Meta:
        model = DrivingQuestion
        fields = [
            "id",
            "question_text",
            "explanation",
            "difficulty",
            "question_type",
            "sign_hint",
            "image_url",
            "tags",
            "points",
            "options",
        ]
        read_only_fields = ["id", "difficulty", "question_type", "sign_hint", "image_url", "tags", "points", "options"]

    def get_question_text(self, obj):
        return obj.question_text_nl if self.get_lang() == "nl" and obj.question_text_nl else obj.question_text

    def get_explanation(self, obj):
        return obj.explanation_nl if self.get_lang() == "nl" and obj.explanation_nl else obj.explanation

    def get_options(self, obj):
        options = list(obj.options.all())
        rng = random.Random()
        rng.shuffle(options)
        return DrivingQuestionOptionSerializer(options, many=True, context=self.context).data


class DrivingLessonSerializer(LangMixin, serializers.ModelSerializer):
    title = serializers.SerializerMethodField()
    summary = serializers.SerializerMethodField()
    learning_objectives = serializers.SerializerMethodField()
    exam_tips = serializers.SerializerMethodField()
    common_mistakes = serializers.SerializerMethodField()
    key_takeaways = serializers.SerializerMethodField()
    sections = DrivingLessonSectionSerializer(many=True, read_only=True)

    class Meta:
        model = DrivingLesson
        fields = [
            "id",
            "title",
            "summary",
            "difficulty",
            "estimated_minutes",
            "learning_objectives",
            "exam_tips",
            "common_mistakes",
            "key_takeaways",
            "sections",
        ]
        read_only_fields = [
            "id",
            "difficulty",
            "estimated_minutes",
            "learning_objectives",
            "exam_tips",
            "common_mistakes",
            "key_takeaways",
            "sections",
        ]

    def get_title(self, obj):
        return obj.title_nl if self.get_lang() == "nl" and obj.title_nl else obj.title

    def get_summary(self, obj):
        return obj.summary_nl if self.get_lang() == "nl" and obj.summary_nl else obj.summary

    def get_learning_objectives(self, obj):
        return (
            obj.learning_objectives_nl
            if self.get_lang() == "nl" and obj.learning_objectives_nl
            else obj.learning_objectives
        )

    def get_exam_tips(self, obj):
        return obj.exam_tips_nl if self.get_lang() == "nl" and obj.exam_tips_nl else obj.exam_tips

    def get_common_mistakes(self, obj):
        return obj.common_mistakes_nl if self.get_lang() == "nl" and obj.common_mistakes_nl else obj.common_mistakes

    def get_key_takeaways(self, obj):
        return obj.key_takeaways_nl if self.get_lang() == "nl" and obj.key_takeaways_nl else obj.key_takeaways


class DrivingLessonDetailSerializer(DrivingLessonSerializer):
    questions = serializers.SerializerMethodField()
    topic_slug = serializers.SlugField(source="topic.slug", read_only=True)
    topic_title = serializers.CharField(source="topic.title", read_only=True)

    class Meta(DrivingLessonSerializer.Meta):
        fields = DrivingLessonSerializer.Meta.fields + ["topic_slug", "topic_title", "questions"]
        read_only_fields = DrivingLessonSerializer.Meta.read_only_fields + ["topic_slug", "topic_title", "questions"]

    def get_questions(self, obj):
        questions = obj.questions.filter(is_active=True).prefetch_related("options")
        return DrivingQuestionSerializer(questions, many=True, context=self.context).data


class DrivingTopicListSerializer(LangMixin, serializers.ModelSerializer):
    title = serializers.SerializerMethodField()
    summary = serializers.SerializerMethodField()
    question_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = DrivingTopic
        fields = [
            "id",
            "slug",
            "title",
            "summary",
            "icon",
            "color_theme",
            "difficulty_level",
            "learning_objectives",
            "exam_weight",
            "recommended_next",
            "order",
            "question_count",
        ]
        read_only_fields = [
            "id",
            "slug",
            "icon",
            "color_theme",
            "difficulty_level",
            "learning_objectives",
            "exam_weight",
            "recommended_next",
            "order",
            "question_count",
        ]

    def get_title(self, obj):
        return obj.title_nl if self.get_lang() == "nl" and obj.title_nl else obj.title

    def get_summary(self, obj):
        return obj.summary_nl if self.get_lang() == "nl" and obj.summary_nl else obj.summary


class DrivingTopicDetailSerializer(LangMixin, serializers.ModelSerializer):
    title = serializers.SerializerMethodField()
    summary = serializers.SerializerMethodField()
    lessons = DrivingLessonSerializer(many=True, read_only=True)

    class Meta:
        model = DrivingTopic
        fields = [
            "id",
            "slug",
            "title",
            "summary",
            "dutch_terms",
            "icon",
            "color_theme",
            "difficulty_level",
            "learning_objectives",
            "exam_weight",
            "recommended_next",
            "order",
            "is_active",
            "created_at",
            "lessons",
        ]
        read_only_fields = [
            "id",
            "slug",
            "dutch_terms",
            "icon",
            "color_theme",
            "difficulty_level",
            "learning_objectives",
            "exam_weight",
            "recommended_next",
            "order",
            "is_active",
            "created_at",
            "lessons",
        ]

    def get_title(self, obj):
        return obj.title_nl if self.get_lang() == "nl" and obj.title_nl else obj.title

    def get_summary(self, obj):
        return obj.summary_nl if self.get_lang() == "nl" and obj.summary_nl else obj.summary


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
