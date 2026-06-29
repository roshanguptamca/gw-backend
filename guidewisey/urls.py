from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView

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
    path("api/", include("apps.marketplace.urls")),
    path("api/buddy/", include("apps.speaking_buddy.urls")),
    path("api/securewise/", include("apps.securewise.urls")),
    # OpenAPI schema + UI
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
else:
    # Serve uploaded media files in production.
    # For high-traffic deployments replace this with S3 + django-storages.
    from django.views.static import serve as _media_serve

    urlpatterns += [
        path(
            settings.MEDIA_URL.lstrip("/") + "<path:path>",
            _media_serve,
            {"document_root": settings.MEDIA_ROOT, "show_indexes": False},
        )
    ]
