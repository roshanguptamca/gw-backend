from django.urls import path

from .views import (
    LessonDetailView,
    MockTestResultView,
    MockTestStartView,
    MockTestSubmitView,
    ProgressView,
    TopicDetailView,
    TopicQuizView,
    TopicsListView,
)

app_name = "driving_theory"

urlpatterns = [
    path("topics/", TopicsListView.as_view(), name="topics-list"),
    path("topics/<slug:slug>/", TopicDetailView.as_view(), name="topic-detail"),
    path("topics/<slug:slug>/quiz/", TopicQuizView.as_view(), name="topic-quiz"),
    path("lessons/<int:pk>/", LessonDetailView.as_view(), name="lesson-detail"),
    path("progress/", ProgressView.as_view(), name="progress"),
    path("mock-tests/start/", MockTestStartView.as_view(), name="mock-test-start"),
    path("mock-tests/<int:pk>/submit/", MockTestSubmitView.as_view(), name="mock-test-submit"),
    path("mock-tests/<int:pk>/result/", MockTestResultView.as_view(), name="mock-test-result"),
]
