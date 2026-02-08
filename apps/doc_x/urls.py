from django.urls import path
from . import views

urlpatterns = [
    path("process/", views.process_document, name="process_document"),
    path("ask/", views.ask, name="ask"),
    path("process-text/", views.process_text),
    path("ask/remaining/", views.get_remaining_questions),
]
