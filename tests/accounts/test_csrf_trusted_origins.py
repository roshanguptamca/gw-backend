"""
Regression tests for the SecureWise CSRF 403 on POST /api/accounts/logout/.

Root cause: Django's CsrfViewMiddleware rejects a cross-origin POST unless the
request's Origin header matches an entry in CSRF_TRUSTED_ORIGINS -- this check
happens independently of (and before) validating the X-CSRFToken value itself.
SecureWise is served from https://securewise.guidewisey.com, a different
(sub)domain than the GuideWisey frontends, so it must be explicitly listed.

Previously, both the default value baked into guidewisey/settings.py and the
CSRF_TRUSTED_ORIGINS env var configured in render.yaml / .env.example omitted
https://securewise.guidewisey.com, so *any* correctly-CSRF-tokened POST from
SecureWise (logout included) was still rejected with 403 purely due to the
Origin check.
"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings

from guidewisey.settings import CSRF_TRUSTED_ORIGINS as CONFIGURED_CSRF_TRUSTED_ORIGINS

User = get_user_model()


class DefaultCsrfTrustedOriginsTests(TestCase):
    def test_securewise_origin_is_trusted_by_default(self):
        # Guards against a future edit accidentally dropping the SecureWise
        # origin from the CSRF_TRUSTED_ORIGINS default (used whenever the
        # CSRF_TRUSTED_ORIGINS env var isn't set, e.g. local/dev/other hosts).
        self.assertIn("https://securewise.guidewisey.com", CONFIGURED_CSRF_TRUSTED_ORIGINS)


@override_settings(
    ALLOWED_HOSTS=["api.guidewisey.com", "testserver"],
    CSRF_TRUSTED_ORIGINS=[
        "https://api.guidewisey.com",
        "https://guidewisey.com",
        "https://www.guidewisey.com",
        "https://securewise.guidewisey.com",
    ],
)
class SecureWiseLogoutCsrfTests(TestCase):
    """
    Exercises the real CsrfViewMiddleware (enforce_csrf_checks=True) to confirm
    a POST /api/accounts/logout/ from the SecureWise origin, carrying a valid
    CSRF token, is accepted rather than rejected as a cross-origin CSRF risk.
    """

    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        self.user = User.objects.create_user(
            username="sw-user", email="sw-user@example.com", password="Str0ngPassw0rd!"
        )
        # DRF's SessionAuthentication only enforces CSRF for authenticated
        # sessions, so log in first -- this matches the real logout scenario
        # (an anonymous request never reaches a meaningful logout anyway).
        logged_in = self.client.login(username="sw-user", password="Str0ngPassw0rd!")
        assert logged_in

    def _get_csrf_token(self):
        response = self.client.get(
            "/api/accounts/csrf/",
            HTTP_HOST="api.guidewisey.com",
            secure=True,
        )
        self.assertEqual(response.status_code, 200)
        return response.json()["csrfToken"]

    def test_logout_from_securewise_origin_is_not_rejected_for_csrf(self):
        csrf_token = self._get_csrf_token()

        response = self.client.post(
            "/api/accounts/logout/",
            HTTP_HOST="api.guidewisey.com",
            HTTP_ORIGIN="https://securewise.guidewisey.com",
            HTTP_X_CSRFTOKEN=csrf_token,
            secure=True,
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)

    def test_logout_from_untrusted_origin_is_still_rejected(self):
        # Sanity check that the CSRF origin check is actually active in this
        # test (i.e. that the fix above isn't accidentally disabling it).
        csrf_token = self._get_csrf_token()

        response = self.client.post(
            "/api/accounts/logout/",
            HTTP_HOST="api.guidewisey.com",
            HTTP_ORIGIN="https://evil-untrusted-origin.example",
            HTTP_X_CSRFTOKEN=csrf_token,
            secure=True,
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)
