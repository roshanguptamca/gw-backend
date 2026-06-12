from django.urls import path

from . import views

urlpatterns = [
    path("jobs/parse-text/", views.parse_text),
    path("jobs/parse-url/", views.parse_url),
    path("job-match/analyze/", views.analyze),
    path("job-match/<int:match_id>/optimize/", views.optimize),
]
