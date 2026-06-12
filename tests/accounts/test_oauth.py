import hashlib
import uuid
from unittest.mock import Mock, patch

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import OAuthTransaction, UserAuthProvider, UserProfile
from apps.accounts.oauth import OAuthError, SocialProfile, _exchange_code, connect_social_account

User = get_user_model()

OAUTH_SETTINGS = {
    "GOOGLE_CLIENT_ID": "google-client",
    "GOOGLE_CLIENT_SECRET": "google-secret",
    "OAUTH_REDIRECT_BASE_URL": "http://testserver",
    "FRONTEND_AUTH_SUCCESS_URL": "http://frontend/#auth-callback",
    "FRONTEND_AUTH_ERROR_URL": "http://frontend/#auth-callback",
}


@override_settings(**OAUTH_SETTINGS)
class OAuthViewsTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    @patch("apps.accounts.oauth._provider_settings")
    def test_start_generates_pkce_url_and_transaction_cookie_for_each_provider(self, provider_settings):
        provider_settings.return_value = {
            "client_id": "google-client",
            "client_secret": "google-secret",
            "authorization_endpoint": "https://provider.example/authorize",
            "scopes": "openid profile email",
        }

        for provider in ("google", "facebook", "linkedin", "oidc"):
            with self.subTest(provider=provider):
                response = self.client.get(f"/api/auth/oauth/{provider}/start")
                self.assertEqual(response.status_code, 302)
                self.assertIn("code_challenge_method=S256", response["Location"])
                self.assertIn("state=", response["Location"])
                self.assertIn("gw_oauth_transaction", response.cookies)
        self.assertEqual(OAuthTransaction.objects.count(), 4)

    def test_invalid_state_is_rejected(self):
        oauth_transaction = self._transaction("expected")
        self.client.cookies["gw_oauth_transaction"] = str(oauth_transaction.id)

        response = self.client.get(
            "/api/auth/oauth/google/callback",
            {"state": "wrong", "code": "code"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("error=invalid_or_expired", response["Location"])

    def test_expired_transaction_is_rejected(self):
        oauth_transaction = self._transaction("state", expired=True)
        self.client.cookies["gw_oauth_transaction"] = str(oauth_transaction.id)

        response = self.client.get(
            "/api/auth/oauth/google/callback",
            {"state": "state", "code": "code"},
        )

        self.assertIn("error=invalid_or_expired", response["Location"])

    @patch("apps.accounts.oauth_views.fetch_social_profile")
    def test_callback_creates_user_profile_provider_and_session(self, fetch_profile):
        fetch_profile.return_value = SocialProfile(
            provider_user_id="google-123",
            email="social@example.com",
            email_verified=True,
            first_name="Social",
            last_name="User",
            display_name="Social User",
            avatar_url="https://example.com/avatar.jpg",
            locale="nl",
        )
        oauth_transaction = self._transaction("valid-state")
        self.client.cookies["gw_oauth_transaction"] = str(oauth_transaction.id)

        response = self.client.get(
            "/api/auth/oauth/google/callback",
            {"state": "valid-state", "code": "provider-code"},
        )

        self.assertIn("status=success", response["Location"])
        user = User.objects.get(email="social@example.com")
        self.assertFalse(user.has_usable_password())
        self.assertTrue(UserAuthProvider.objects.filter(user=user, provider="google").exists())
        self.assertTrue(user.profile.email_confirmed)
        self.assertTrue(user.profile.profile_completed)
        self.assertEqual(user.profile.preferred_language, "nl")
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.id)

    @patch("apps.accounts.oauth._provider_settings")
    def test_authenticated_user_can_start_link_flow(self, provider_settings):
        user = User.objects.create_user("linked", "linked@example.com", "password")
        self.client.force_authenticate(user)
        provider_settings.return_value = {
            "client_id": "google-client",
            "client_secret": "google-secret",
            "authorization_endpoint": "https://provider.example/authorize",
            "scopes": "openid profile email",
        }

        response = self.client.post("/api/auth/oauth/link", {"provider": "google"}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertIn("authorization_url", response.data)
        self.assertEqual(OAuthTransaction.objects.get().link_user, user)
        self.assertIn("gw_oauth_transaction", response.cookies)

    def _transaction(self, state, expired=False):
        return OAuthTransaction.objects.create(
            id=uuid.uuid4(),
            provider="google",
            state_digest=hashlib.sha256(state.encode()).hexdigest(),
            nonce="nonce",
            code_verifier="verifier",
            redirect_uri="http://testserver/api/auth/oauth/google/callback",
            expires_at=timezone.now() + timezone.timedelta(minutes=-1 if expired else 10),
        )


class OAuthAccountTests(TestCase):
    def profile(self, provider_user_id="provider-1", email="person@example.com", **overrides):
        values = {
            "provider_user_id": provider_user_id,
            "email": email,
            "email_verified": True,
            "first_name": "Provider",
            "last_name": "Person",
            "display_name": "Provider Person",
            "avatar_url": "https://example.com/avatar.jpg",
        }
        values.update(overrides)
        return SocialProfile(**values)

    def test_verified_email_links_existing_user_without_overwriting_names(self):
        user = User.objects.create_user(
            "existing",
            "person@example.com",
            "password",
            first_name="Custom",
            last_name="Name",
        )
        profile = UserProfile.objects.get(user=user)
        profile.email_confirmed = True
        profile.save(update_fields=["email_confirmed"])

        linked_user, created, complete = connect_social_account("google", self.profile())

        user.refresh_from_db()
        self.assertEqual(linked_user, user)
        self.assertFalse(created)
        self.assertTrue(complete)
        self.assertEqual(user.first_name, "Custom")
        self.assertEqual(user.last_name, "Name")

    def test_unverified_existing_email_is_not_silently_linked(self):
        User.objects.create_user("existing", "person@example.com", "password")

        with self.assertRaises(OAuthError) as context:
            connect_social_account("google", self.profile())

        self.assertEqual(context.exception.code, "email_already_exists")

    def test_provider_identity_cannot_link_to_second_user(self):
        first = User.objects.create_user("first", "first@example.com", "password")
        second = User.objects.create_user("second", "second@example.com", "password")
        connect_social_account("google", self.profile(), link_user=first)

        with self.assertRaises(OAuthError) as context:
            connect_social_account("google", self.profile(), link_user=second)

        self.assertEqual(context.exception.code, "provider_already_linked")

    def test_last_login_method_cannot_be_unlinked(self):
        user = User.objects.create_user("social-only", "social@example.com")
        user.set_unusable_password()
        user.save(update_fields=["password"])
        UserAuthProvider.objects.create(user=user, provider="google", provider_user_id="google-1")
        client = APIClient()
        client.force_authenticate(user)

        response = client.delete("/api/auth/oauth/unlink/google")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"], "last_login_method")

    def test_provider_can_be_unlinked_when_password_exists(self):
        user = User.objects.create_user("password-user", "password@example.com", "password")
        UserAuthProvider.objects.create(user=user, provider="google", provider_user_id="google-2")
        client = APIClient()
        client.force_authenticate(user)

        response = client.delete("/api/auth/oauth/unlink/google")

        self.assertEqual(response.status_code, 204)
        self.assertFalse(UserAuthProvider.objects.filter(user=user).exists())

    @patch("apps.accounts.oauth._provider_settings")
    @patch("apps.accounts.oauth.requests.post")
    def test_authorization_code_is_exchanged_server_side(self, post, provider_settings):
        provider_settings.return_value = {
            "client_id": "client",
            "client_secret": "secret",
            "token_endpoint": "https://provider.example/token",
        }
        response = Mock()
        response.json.return_value = {"access_token": "server-only-token", "id_token": "id-token"}
        post.return_value = response
        oauth_transaction = OAuthTransaction(
            provider="google",
            redirect_uri="http://testserver/api/auth/oauth/google/callback",
            code_verifier="verifier",
        )

        _config, token_payload = _exchange_code(oauth_transaction, "authorization-code")

        self.assertEqual(token_payload["access_token"], "server-only-token")
        self.assertEqual(post.call_args.kwargs["data"]["code_verifier"], "verifier")

    def test_social_models_are_registered_in_admin(self):
        self.assertIn(UserAuthProvider, admin.site._registry)
        self.assertIn(OAuthTransaction, admin.site._registry)
