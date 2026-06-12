from django.test import TestCase, override_settings
from rest_framework.test import APIClient


@override_settings(
    ALLOWED_HOSTS=[
        "api.guidewisey.com",
        "guidewisey.com",
        "gw-backend-eq2n.onrender.com",
        "localhost",
        "127.0.0.1",
    ],
    CSRF_TRUSTED_ORIGINS=[
        "https://api.guidewisey.com",
        "https://guidewisey.com",
    ],
    FRONTEND_AUTH_ERROR_URL="https://guidewisey.com/#auth-callback",
)
class RenderCustomDomainTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_api_custom_domain_is_accepted(self):
        response = self.client.get("/api/accounts/session/", HTTP_HOST="api.guidewisey.com", secure=True)

        self.assertEqual(response.status_code, 200)

    def test_frontend_custom_domain_is_accepted(self):
        response = self.client.get("/api/accounts/session/", HTTP_HOST="guidewisey.com", secure=True)

        self.assertEqual(response.status_code, 200)

    def test_oauth_callback_on_custom_domain_returns_redirect_instead_of_bad_request(self):
        response = self.client.get(
            "/api/auth/oauth/google/callback",
            {"error": "access_denied"},
            HTTP_HOST="api.guidewisey.com",
            secure=True,
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("oauth_cancelled", response["Location"])
