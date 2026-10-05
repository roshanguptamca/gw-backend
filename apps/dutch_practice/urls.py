from django.urls import path

from . import views

app_name = "dutch_practice"
urlpatterns = [
    path(
        "attempts/<uuid:attempt_id>/questions/<int:position>/position/", views.PositionView.as_view(), name="position"
    ),
    path("attempts/<uuid:attempt_id>/questions/<int:position>/media/", views.MediaView.as_view(), name="media"),
    path(
        "attempts/<uuid:attempt_id>/questions/<int:position>/playback/", views.PlaybackView.as_view(), name="playback"
    ),
    path("catalog/", views.CatalogView.as_view(), name="catalog"),
    path("attempts/", views.AttemptsView.as_view(), name="attempts"),
    path("attempts/<uuid:attempt_id>/", views.AttemptView.as_view(), name="attempt"),
    path("attempts/<uuid:attempt_id>/questions/<int:position>/", views.QuestionView.as_view(), name="question"),
    path("attempts/<uuid:attempt_id>/submit/", views.SubmitView.as_view(), name="submit"),
    path("attempts/<uuid:attempt_id>/abandon/", views.AbandonView.as_view(), name="abandon"),
    path("attempts/<uuid:attempt_id>/result/", views.ResultView.as_view(), name="result"),
]
