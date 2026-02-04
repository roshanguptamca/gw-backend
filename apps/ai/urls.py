from django.urls import path
from .views import explain
urlpatterns=[path("explain/",explain)]