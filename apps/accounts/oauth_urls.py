from django.urls import path

from .oauth_views import oauth_callback, oauth_link, oauth_start, oauth_unlink
from .views import MeView

urlpatterns = [
    path("oauth/<str:provider>/start", oauth_start, name="oauth-start"),
    path("oauth/<str:provider>/callback", oauth_callback, name="oauth-callback"),
    path("oauth/link", oauth_link, name="oauth-link"),
    path("oauth/unlink/<str:provider>", oauth_unlink, name="oauth-unlink"),
    path("me", MeView.as_view(), name="auth-me"),
]
