from django.urls import path

from .views import download

urlpatterns = [path("files/download/<uuid:file_id>/", download)]
