from django.contrib import admin
from django.urls import path, include
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/accounts/", include("apps.accounts.urls")),
    path("api/auth/", include("apps.accounts.oauth_urls")),
    path("api/doc-x/", include("apps.doc_x.urls")),
    path("api/future-wise/", include("apps.future_wise.urls", namespace="future_wise")),
    path("api/insurance/", include("apps.insurance_explainer.urls")),
    path("api/contact/", include("apps.contact.urls")),
    path("api/driving/", include("apps.driving_theory.urls")),
    path("api/", include("apps.resumes.urls")),
    path("api/", include("apps.templates_app.urls")),
    path("api/", include("apps.autocomplete.urls")),
    path("api/", include("apps.jobs.urls")),
    path("api/", include("apps.files.urls")),
    path("api/buddy/", include("apps.speaking_buddy.urls")),
    # OpenAPI schema + UI
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
]
