from django.urls import path

from . import views

urlpatterns = [
    path("autocomplete/skills/", views.skills),
    path("autocomplete/job-titles/", views.job_titles),
    path("autocomplete/companies/", views.companies),
    path("autocomplete/schools/", views.schools),
    path("autocomplete/degrees/", views.degrees),
    path("autocomplete/locations/", views.locations),
]
