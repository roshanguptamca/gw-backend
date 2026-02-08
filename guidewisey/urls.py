from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/accounts/", include("apps.accounts.urls")),   # renamed path
    path('api/doc-x/', include('apps.doc_x.urls')),
]
