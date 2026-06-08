from django.conf import settings
from django.db import models


class DrivingTopic(models.Model):
    DIFFICULTY_LEVEL = [
        ("beginner", "Beginner"),
        ("intermediate", "Intermediate"),
        ("advanced", "Advanced"),
    ]

    slug = models.SlugField(unique=True)
    title = models.CharField(max_length=200)
    summary = models.TextField()
    dutch_terms = models.JSONField(default=list)
    icon = models.CharField(max_length=50, default="bi-sign-stop")
    color_theme = models.CharField(max_length=80, default="rgba(99,102,241,0.15)")
    difficulty_level = models.CharField(max_length=15, choices=DIFFICULTY_LEVEL, default="beginner")
    learning_objectives = models.JSONField(default=list)
    exam_weight = models.PositiveIntegerField(default=8)
    recommended_next = models.JSONField(default=list)  # list of slugs
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return self.title


class DrivingLesson(models.Model):
    DIFFICULTY_CHOICES = [("easy", "Easy"), ("medium", "Medium"), ("hard", "Hard")]

    topic = models.ForeignKey(DrivingTopic, on_delete=models.CASCADE, related_name="lessons")
    title = models.CharField(max_length=200)
    summary = models.TextField()
    order = models.PositiveIntegerField(default=0)
    difficulty = models.CharField(max_length=10, choices=DIFFICULTY_CHOICES, default="easy")
    estimated_minutes = models.PositiveIntegerField(default=10)
    learning_objectives = models.JSONField(default=list)
    exam_tips = models.JSONField(default=list)
    common_mistakes = models.JSONField(default=list)
    key_takeaways = models.JSONField(default=list)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return self.title


class DrivingLessonSection(models.Model):
    lesson = models.ForeignKey(DrivingLesson, on_delete=models.CASCADE, related_name="sections")
    title = models.CharField(max_length=200)
    content = models.TextField()
    examples = models.JSONField(default=list)
    dutch_keywords = models.JSONField(default=list)
    callout_boxes = models.JSONField(default=list)
    illustration_hint = models.CharField(max_length=100, blank=True, default="")
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return f"{self.lesson.title}: {self.title}"


class DrivingQuestion(models.Model):
    DIFFICULTY = [(1, "Easy"), (2, "Medium"), (3, "Hard")]
    QUESTION_TYPE = [
        ("multiple_choice", "Multiple Choice"),
        ("scenario", "Scenario Based"),
        ("sign", "Sign Recognition"),
        ("hazard", "Hazard Recognition"),
    ]

    topic = models.ForeignKey(DrivingTopic, on_delete=models.CASCADE, related_name="questions")
    lesson = models.ForeignKey(
        DrivingLesson,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="questions",
    )
    question_text = models.TextField()
    explanation = models.TextField()
    difficulty = models.IntegerField(choices=DIFFICULTY, default=1)
    question_type = models.CharField(max_length=20, choices=QUESTION_TYPE, default="multiple_choice")
    sign_hint = models.CharField(max_length=100, blank=True, default="")
    tags = models.JSONField(default=list)
    image_url = models.CharField(max_length=300, blank=True, default="")
    points = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.question_text[:60]


class DrivingQuestionOption(models.Model):
    question = models.ForeignKey(DrivingQuestion, on_delete=models.CASCADE, related_name="options")
    option_text = models.CharField(max_length=500)
    is_correct = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return self.option_text[:60]


class UserDrivingProgress(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="driving_progress")
    topic = models.ForeignKey(DrivingTopic, on_delete=models.CASCADE)
    lesson = models.ForeignKey(DrivingLesson, null=True, blank=True, on_delete=models.SET_NULL)
    lessons_completed = models.JSONField(default=list)
    questions_answered = models.PositiveIntegerField(default=0)
    questions_correct = models.PositiveIntegerField(default=0)
    last_accessed = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("user", "topic")]

    def __str__(self):
        return f"{self.user} - {self.topic}"


class MockTestAttempt(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="mock_test_attempts")
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    score = models.FloatField(null=True, blank=True)
    total_questions = models.PositiveIntegerField(default=25)
    correct_answers = models.PositiveIntegerField(default=0)
    passed = models.BooleanField(null=True, blank=True)
    attempt_number = models.PositiveIntegerField(default=1)
    topic_breakdown = models.JSONField(default=dict)
    questions = models.ManyToManyField(DrivingQuestion, blank=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"Mock test {self.id} ({self.user})"


class MockTestAnswer(models.Model):
    attempt = models.ForeignKey(MockTestAttempt, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey(DrivingQuestion, on_delete=models.CASCADE)
    selected_option = models.ForeignKey(DrivingQuestionOption, null=True, blank=True, on_delete=models.SET_NULL)
    is_correct = models.BooleanField(default=False)

    class Meta:
        unique_together = [("attempt", "question")]

    def __str__(self):
        return f"Attempt {self.attempt_id} - Question {self.question_id}"
