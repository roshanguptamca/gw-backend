import hashlib
import uuid
from unittest.mock import Mock, patch

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from rest_framework.test import APIClient

from apps.accounts.models import OAuthTransaction, UserAuthProvider, UserProfile
from apps.accounts.oauth import (
    OAuthError,
    SocialProfile,
    _callback_url,
    _exchange_code,
    _provider_settings,
    connect_social_account,
    fetch_social_profile,
)
from apps.accounts.oauth_views import _frontend_redirect

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
        provider_settings.side_effect = lambda provider: {
            "client_id": "test-client",
            "client_secret": "test-secret",
            "authorization_endpoint": "https://provider.example/authorize",
            "scopes": "openid profile email",
            "supports_pkce": provider != "linkedin",
            "supports_nonce": provider not in {"facebook", "linkedin"},
        }

        for provider in ("google", "facebook", "linkedin", "oidc"):
            with self.subTest(provider=provider):
                response = self.client.get(f"/api/auth/oauth/{provider}/start")
                self.assertEqual(response.status_code, 302)
                if provider == "linkedin":
                    self.assertNotIn("code_challenge=", response["Location"])
                    self.assertNotIn("nonce=", response["Location"])
                else:
                    self.assertIn("code_challenge_method=S256", response["Location"])
                self.assertIn("state=", response["Location"])
                self.assertIn("gw_oauth_transaction", response.cookies)
        self.assertEqual(OAuthTransaction.objects.count(), 4)

    def test_google_provider_uses_basic_openid_scopes_only(self):
        config = _provider_settings("google")

        self.assertEqual(config["scopes"], "openid profile email")

    @override_settings(OAUTH_REDIRECT_BASE_URL="https://api.guidewisey.com")
    def test_google_callback_uri_is_derived_from_configured_backend_base_url(self):
        self.assertEqual(
            _callback_url("google"),
            "https://api.guidewisey.com/api/auth/oauth/google/callback",
        )

    @override_settings(OAUTH_REDIRECT_BASE_URL="https://api.guidewisey.com")
    def test_linkedin_callback_uri_is_derived_from_configured_backend_base_url(self):
        self.assertEqual(
            _callback_url("linkedin"),
            "https://api.guidewisey.com/api/auth/oauth/linkedin/callback",
        )

    def test_invalid_state_is_rejected(self):
        oauth_transaction = self._transaction("expected")
        self.client.cookies["gw_oauth_transaction"] = str(oauth_transaction.id)

        response = self.client.get(
            "/api/auth/oauth/google/callback",
            {"state": "wrong", "code": "code"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("error=invalid_or_expired", response["Location"])

    @override_settings(
        FRONTEND_AUTH_SUCCESS_URL="www.guidewisey.com/auth-callback?status=success",
        FRONTEND_AUTH_ERROR_URL="www.guidewisey.com/auth-callback?error=",
        FRONTEND_BASE_URL="https://www.guidewisey.com",
    )
    def test_frontend_redirect_normalizes_scheme_less_callback_urls(self):
        response = _frontend_redirect(True, status="success", new="0")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"],
            "https://www.guidewisey.com/auth-callback?status=success&new=0",
        )

    def test_expired_transaction_is_rejected(self):
        oauth_transaction = self._transaction("state", expired=True)
        self.client.cookies["gw_oauth_transaction"] = str(oauth_transaction.id)

        response = self.client.get(
            "/api/auth/oauth/google/callback",
            {"state": "state", "code": "code"},
        )

        self.assertIn("error=invalid_or_expired", response["Location"])

    def test_linkedin_missing_oidc_permissions_returns_actionable_error(self):
        response = self.client.get(
            "/api/auth/oauth/linkedin/callback",
            {
                "error": "unauthorized_scope_error",
                "error_description": "Scope openid is not authorized for your application",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("error=provider_permissions_missing", response["Location"])

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

    def test_linkedin_without_email_verified_flag_still_succeeds(self):
        # LinkedIn frequently omits email_verified entirely; only the email address
        # should be required for LinkedIn, unlike other providers.
        profile = self.profile(provider_user_id="linkedin-1", email="linkedin-user@example.com", email_verified=False)

        user, created, _complete = connect_social_account("linkedin", profile)

        self.assertTrue(created)
        self.assertEqual(user.email, "linkedin-user@example.com")
        self.assertTrue(UserAuthProvider.objects.filter(user=user, provider="linkedin").exists())
        self.assertTrue(UserProfile.objects.get(user=user).email_confirmed)

    def test_missing_email_is_rejected_for_any_provider(self):
        for provider in ("google", "linkedin"):
            with self.subTest(provider=provider):
                profile = self.profile(
                    provider_user_id=f"{provider}-no-email",
                    email="",
                    email_verified=True,
                )
                with self.assertRaises(OAuthError) as context:
                    connect_social_account(provider, profile)
                self.assertEqual(context.exception.code, "provider_account_not_verified")

    def test_google_unverified_email_is_rejected(self):
        profile = self.profile(
            provider_user_id="google-unverified", email="unverified@example.com", email_verified=False
        )

        with self.assertRaises(OAuthError) as context:
            connect_social_account("google", profile)

        self.assertEqual(context.exception.code, "provider_account_not_verified")

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
            "supports_pkce": True,
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

    @override_settings(LINKEDIN_CLIENT_ID="linkedin-client", LINKEDIN_CLIENT_SECRET="linkedin-secret")
    @patch("apps.accounts.oauth.requests.get")
    def test_linkedin_provider_config_does_not_require_discovery_request(self, get):
        config = _provider_settings("linkedin")

        self.assertEqual(config["token_endpoint"], "https://www.linkedin.com/oauth/v2/accessToken")
        self.assertEqual(config["issuer"], "https://www.linkedin.com/oauth")
        self.assertFalse(config["supports_pkce"])
        self.assertFalse(config["supports_nonce"])
        get.assert_not_called()

    @override_settings(LINKEDIN_CLIENT_ID="linkedin-client", LINKEDIN_CLIENT_SECRET="linkedin-secret")
    @patch("apps.accounts.oauth.requests.post")
    def test_linkedin_token_exchange_omits_unsupported_pkce_verifier(self, post):
        response = Mock()
        response.ok = True
        response.json.return_value = {"access_token": "access-token", "id_token": "id-token"}
        post.return_value = response
        oauth_transaction = OAuthTransaction(
            provider="linkedin",
            redirect_uri="http://testserver/api/auth/oauth/linkedin/callback",
            code_verifier="verifier",
        )

        _exchange_code(oauth_transaction, "authorization-code")

        self.assertNotIn("code_verifier", post.call_args.kwargs["data"])

    @override_settings(FACEBOOK_CLIENT_ID="facebook-client", FACEBOOK_CLIENT_SECRET="facebook-secret")
    @patch("apps.accounts.oauth._exchange_code")
    @patch("apps.accounts.oauth.requests.get")
    def test_facebook_profile_mapping_uses_graph_fields(self, get, exchange_code):
        profile_response = Mock()
        profile_response.raise_for_status.return_value = None
        profile_response.json.return_value = {
            "id": "fb-123",
            "name": "Facebook User",
            "first_name": "Facebook",
            "last_name": "User",
            "email": "fb@example.com",
            "picture": {"data": {"url": "https://example.com/fb.jpg"}},
        }
        get.return_value = profile_response
        exchange_code.return_value = (
            {
                "client_id": "facebook-client",
                "client_secret": "facebook-secret",
                "authorization_endpoint": "https://www.facebook.com/v23.0/dialog/oauth",
                "token_endpoint": "https://graph.facebook.com/v23.0/oauth/access_token",
                "userinfo_endpoint": "https://graph.facebook.com/v23.0/me",
                "scopes": "email public_profile",
                "issuer": "",
                "jwks_uri": "",
                "supports_pkce": True,
                "supports_nonce": False,
            },
            {"access_token": "facebook-token"},
        )

        oauth_transaction = OAuthTransaction(
            provider="facebook",
            redirect_uri="http://testserver/api/auth/oauth/facebook/callback",
            code_verifier="verifier",
            state_digest="state",
            expires_at=timezone.now() + timezone.timedelta(minutes=10),
        )
        oauth_transaction.save()

        profile = fetch_social_profile(oauth_transaction, "code")

        self.assertEqual(profile.provider_user_id, "fb-123")
        self.assertEqual(profile.email, "fb@example.com")
        self.assertEqual(profile.first_name, "Facebook")
        self.assertEqual(profile.avatar_url, "https://example.com/fb.jpg")

    @override_settings(FACEBOOK_CLIENT_ID="facebook-client", FACEBOOK_CLIENT_SECRET="facebook-secret")
    @patch("apps.accounts.oauth.requests.post")
    def test_facebook_token_exchange_uses_post(self, post):
        response = Mock()
        response.ok = True
        response.json.return_value = {"access_token": "facebook-token"}
        post.return_value = response

        oauth_transaction = OAuthTransaction(
            provider="facebook",
            redirect_uri="http://testserver/api/auth/oauth/facebook/callback",
            code_verifier="verifier",
            state_digest="state",
            expires_at=timezone.now() + timezone.timedelta(minutes=10),
        )
        oauth_transaction.save()

        with patch("apps.accounts.oauth._provider_settings") as provider_settings:
            provider_settings.return_value = {
                "client_id": "facebook-client",
                "client_secret": "facebook-secret",
                "authorization_endpoint": "https://www.facebook.com/v23.0/dialog/oauth",
                "token_endpoint": "https://graph.facebook.com/v23.0/oauth/access_token",
                "userinfo_endpoint": "https://graph.facebook.com/v23.0/me",
                "scopes": "email public_profile",
                "issuer": "",
                "jwks_uri": "",
                "supports_pkce": True,
                "supports_nonce": False,
            }
            _exchange_code(oauth_transaction, "code")

        self.assertEqual(post.call_args.kwargs["data"]["grant_type"], "authorization_code")
        self.assertEqual(post.call_args.kwargs["data"]["client_id"], "facebook-client")

    @patch("apps.accounts.oauth._exchange_code")
    @patch("apps.accounts.oauth._validated_oidc_claims")
    @patch("apps.accounts.oauth.requests.get")
    def test_linkedin_uses_userinfo_as_authoritative_profile(
        self,
        get,
        validated_claims,
        exchange_code,
    ):
        response = Mock()
        response.json.return_value = {
            "sub": "linkedin-123",
            "email": "linkedin@example.com",
            "email_verified": True,
            "given_name": "Linked",
            "family_name": "User",
        }
        get.return_value = response
        exchange_code.return_value = (
            {"userinfo_endpoint": "https://api.linkedin.com/v2/userinfo"},
            {"access_token": "access-token", "id_token": "id-token"},
        )
        validated_claims.return_value = {
            "sub": "linkedin-123",
            "name": "Linked User",
        }
        oauth_transaction = OAuthTransaction(provider="linkedin")

        profile = fetch_social_profile(oauth_transaction, "code")

        self.assertEqual(profile.provider_user_id, "linkedin-123")
        self.assertEqual(profile.email, "linkedin@example.com")

    @patch("apps.accounts.oauth._exchange_code")
    @patch("apps.accounts.oauth._validated_oidc_claims")
    @patch("apps.accounts.oauth.requests.get")
    def test_linkedin_userinfo_still_works_when_id_token_validation_fails(
        self,
        get,
        validated_claims,
        exchange_code,
    ):
        validated_claims.side_effect = OAuthError("provider_account_not_verified")
        response = Mock()
        response.json.return_value = {
            "sub": "linkedin-456",
            "email": "fallback@example.com",
            "email_verified": True,
            "given_name": "Fallback",
            "family_name": "User",
        }
        get.return_value = response
        exchange_code.return_value = (
            {"userinfo_endpoint": "https://api.linkedin.com/v2/userinfo"},
            {"access_token": "access-token", "id_token": "id-token"},
        )

        profile = fetch_social_profile(OAuthTransaction(provider="linkedin"), "code")

        self.assertEqual(profile.provider_user_id, "linkedin-456")
        self.assertEqual(profile.email, "fallback@example.com")

    @patch("apps.accounts.oauth._exchange_code")
    @patch("apps.accounts.oauth._validated_oidc_claims")
    @patch("apps.accounts.oauth.requests.get")
    def test_google_email_verified_true_boolean_succeeds(self, get, validated_claims, exchange_code):
        response = Mock()
        response.json.return_value = {
            "sub": "google-1",
            "email": "verified@example.com",
            "given_name": "Verified",
            "family_name": "User",
        }
        get.return_value = response
        exchange_code.return_value = (
            {"userinfo_endpoint": "https://openidconnect.googleapis.com/v1/userinfo"},
            {"access_token": "access-token", "id_token": "id-token"},
        )
        validated_claims.return_value = {
            "sub": "google-1",
            "email": "verified@example.com",
            "email_verified": True,
        }

        profile = fetch_social_profile(OAuthTransaction(provider="google"), "code")

        self.assertTrue(profile.email_verified)
        self.assertEqual(profile.email, "verified@example.com")

    @patch("apps.accounts.oauth._exchange_code")
    @patch("apps.accounts.oauth._validated_oidc_claims")
    @patch("apps.accounts.oauth.requests.get")
    def test_google_email_verified_string_true_succeeds(self, get, validated_claims, exchange_code):
        # Some Google responses (e.g. userinfo fallback) return email_verified as the
        # string "true"/"True" rather than a JSON boolean; this must still be accepted.
        response = Mock()
        response.json.return_value = {
            "sub": "google-2",
            "email": "verified-string@example.com",
            "email_verified": "True",
        }
        get.return_value = response
        exchange_code.return_value = (
            {"userinfo_endpoint": "https://openidconnect.googleapis.com/v1/userinfo"},
            {"access_token": "access-token", "id_token": "id-token"},
        )
        validated_claims.return_value = {
            "sub": "google-2",
            "email": "verified-string@example.com",
        }

        profile = fetch_social_profile(OAuthTransaction(provider="google"), "code")

        self.assertTrue(profile.email_verified)

    @patch("apps.accounts.oauth._exchange_code")
    @patch("apps.accounts.oauth._validated_oidc_claims")
    @patch("apps.accounts.oauth.requests.get")
    def test_google_email_verified_false_from_id_token_is_not_overridden_by_userinfo(
        self, get, validated_claims, exchange_code
    ):
        # The validated ID token says email_verified=False; a userinfo response that
        # omits/claims otherwise must not override that authoritative signal.
        response = Mock()
        response.json.return_value = {
            "sub": "google-3",
            "email": "unverified@example.com",
            "given_name": "Unverified",
        }
        get.return_value = response
        exchange_code.return_value = (
            {"userinfo_endpoint": "https://openidconnect.googleapis.com/v1/userinfo"},
            {"access_token": "access-token", "id_token": "id-token"},
        )
        validated_claims.return_value = {
            "sub": "google-3",
            "email": "unverified@example.com",
            "email_verified": False,
        }

        profile = fetch_social_profile(OAuthTransaction(provider="google"), "code")

        self.assertFalse(profile.email_verified)

    @patch("apps.accounts.oauth._exchange_code")
    @patch("apps.accounts.oauth._validated_oidc_claims")
    @patch("apps.accounts.oauth.requests.get")
    def test_google_profile_fetch_does_not_log_tokens(self, get, validated_claims, exchange_code):
        response = Mock()
        response.json.return_value = {"sub": "google-4", "email": "safe@example.com", "email_verified": True}
        get.return_value = response
        exchange_code.return_value = (
            {"userinfo_endpoint": "https://openidconnect.googleapis.com/v1/userinfo"},
            {"access_token": "super-secret-access-token", "id_token": "super-secret-id-token"},
        )
        validated_claims.return_value = {"sub": "google-4", "email": "safe@example.com", "email_verified": True}

        with self.assertLogs("apps.accounts.oauth", level="INFO") as captured:
            fetch_social_profile(OAuthTransaction(provider="google"), "code")

        log_output = "\n".join(captured.output)
        self.assertIn("provider=google", log_output)
        self.assertIn("email=safe@example.com", log_output)
        self.assertIn("email_verified=True", log_output)
        self.assertNotIn("super-secret-access-token", log_output)
        self.assertNotIn("super-secret-id-token", log_output)
