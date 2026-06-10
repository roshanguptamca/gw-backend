from django.urls import include, path

from rest_framework.routers import DefaultRouter

from .views import ResumeTemplateViewSet

router = DefaultRouter()
router.register("resume-templates", ResumeTemplateViewSet, basename="resume-template")

urlpatterns = [path("", include(router.urls))]
