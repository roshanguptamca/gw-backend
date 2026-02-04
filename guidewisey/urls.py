from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/accounts/", include("apps.accounts.urls")),   # renamed path
    path("api/documents/", include("apps.documents.urls")),
    path("api/ai/", include("apps.ai.urls")),
]
