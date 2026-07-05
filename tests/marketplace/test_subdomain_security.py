from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, SimpleTestCase, TestCase, override_settings


class MarketplaceSubdomainSettingsTests(SimpleTestCase):
    def test_marketplace_origins_and_shared_cookie_domains_are_configured(self):
        self.assertIn("https://marketplace.guidewisey.com", settings.CORS_ALLOWED_ORIGINS)
        self.assertIn("https://marketplace.guidewisey.com", settings.CSRF_TRUSTED_ORIGINS)
        self.assertIn("https://*.shop.guidewisey.com", settings.CSRF_TRUSTED_ORIGINS)
        self.assertTrue(
            any("shop" in pattern and "guidewisey" in pattern for pattern in settings.CORS_ALLOWED_ORIGIN_REGEXES)
        )

    def test_local_marketplace_origin_is_enabled_in_development(self):
        if settings.IS_DEVELOPMENT:
            self.assertIn("http://localhost:3002", settings.CORS_ALLOWED_ORIGINS)
            self.assertIn("http://localhost:3002", settings.CSRF_TRUSTED_ORIGINS)


@override_settings(
    ALLOWED_HOSTS=["api.guidewisey.com", "testserver"],
    CSRF_TRUSTED_ORIGINS=[
        "https://marketplace.guidewisey.com",
        "https://*.shop.guidewisey.com",
    ],
)
class MarketplaceLogoutCsrfTests(TestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        user = get_user_model().objects.create_user(
            username="market-seller",
            email="market-seller@example.com",
            password="StrongPass123!",
        )
        self.client.force_login(user)

    def _csrf_token(self):
        response = self.client.get(
            "/api/accounts/csrf/",
            HTTP_HOST="api.guidewisey.com",
            secure=True,
        )
        return response.json()["csrfToken"]

    def test_logout_from_marketplace_and_shop_origins(self):
        for origin in (
            "https://marketplace.guidewisey.com",
            "https://rishikitchen.shop.guidewisey.com",
        ):
            response = self.client.post(
                "/api/accounts/logout/",
                HTTP_HOST="api.guidewisey.com",
                HTTP_ORIGIN=origin,
                HTTP_X_CSRFTOKEN=self._csrf_token(),
                secure=True,
                content_type="application/json",
            )
            self.assertEqual(response.status_code, 200)
            self.client.force_login(get_user_model().objects.get(username="market-seller"))
