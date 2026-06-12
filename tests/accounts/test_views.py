# tests/accounts/test_views.py

from unittest.mock import patch

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework import status

from apps.accounts.models import UserProfile

User = get_user_model()


class AccountsAPITestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        # Pre-created user for login tests — email already confirmed
        self.user_data = {
            "username": "testuser",
            "email": "testuser@example.com",
            "password": "testpass123",
            "password2": "testpass123",
        }
        self.user = User.objects.create_user(
            username=self.user_data["username"], email=self.user_data["email"], password=self.user_data["password"]
        )
        # Mark email as confirmed so existing login tests continue to pass
        profile, _ = UserProfile.objects.get_or_create(user=self.user)
        profile.email_confirmed = True
        profile.save()

    # ---------------------------
    # Registration tests
    # ---------------------------
    @patch("apps.future_wise.email_service.BrevoEmailService.send_account_confirmation_email")
    def test_register_user_success(self, mock_send):
        """User can register with username, email, password and password2"""
        data = {
            "username": "newuser",
            "email": "newuser@example.com",
            "password": "newpass123",
            "password2": "newpass123",
        }
        response = self.client.post("/api/accounts/register/", data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("message", response.data)
        self.assertTrue(User.objects.filter(username="newuser").exists())
        mock_send.assert_called_once()

    @patch("apps.future_wise.email_service.BrevoEmailService.send_account_confirmation_email")
    def test_register_creates_unconfirmed_profile(self, mock_send):
        """Registration creates a UserProfile with email_confirmed=False and a token."""
        data = {
            "username": "tokenuser",
            "email": "tokenuser@example.com",
            "password": "tokenpass123",
            "password2": "tokenpass123",
        }
        response = self.client.post("/api/accounts/register/", data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        user = User.objects.get(username="tokenuser")
        profile = UserProfile.objects.get(user=user)
        self.assertFalse(profile.email_confirmed)
        self.assertIsNotNone(profile.email_confirmation_token)
        self.assertIsNotNone(profile.email_confirmation_token_expires_at)
        mock_send.assert_called_once()

    def test_register_existing_username(self):
        """Registration should fail if username already exists"""
        data = {
            "username": "testuser",
            "email": "another@example.com",
            "password": "anypass123",
            "password2": "anypass123",
        }
        response = self.client.post("/api/accounts/register/", data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("username", response.data)

    def test_register_existing_email(self):
        """Registration should fail if email is already in use"""
        data = {
            "username": "brandnewuser",
            "email": self.user_data["email"],  # duplicate email
            "password": "anypass123",
            "password2": "anypass123",
        }
        response = self.client.post("/api/accounts/register/", data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.data)

    def test_register_missing_email(self):
        """Registration should fail if email is missing"""
        data = {
            "username": "nouseremail",
            "password": "newpass123",
            "password2": "newpass123",
        }
        response = self.client.post("/api/accounts/register/", data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.data)

    def test_register_password_mismatch(self):
        """Registration should fail if passwords do not match"""
        data = {
            "username": "mismatchuser",
            "email": "mismatch@example.com",
            "password": "password1",
            "password2": "password2",
        }
        response = self.client.post("/api/accounts/register/", data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password", response.data)

    # ---------------------------
    # Login tests
    # ---------------------------
    def test_login_user_success(self):
        """User can login with correct credentials when email is confirmed"""
        data = {"username": self.user_data["username"], "password": self.user_data["password"]}
        response = self.client.post("/api/accounts/login/", data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("message", response.data)

    def test_login_invalid_credentials(self):
        """Login fails with wrong username/password"""
        data = {"username": "wrong", "password": "wrongpass"}
        response = self.client.post("/api/accounts/login/", data, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn("error", response.data)

    def test_login_blocked_before_confirmation(self):
        """Login is blocked with EMAIL_CONFIRMATION_PENDING if email not confirmed"""
        user = User.objects.create_user(username="unconfirmed", email="unconfirmed@example.com", password="pass12345")
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.email_confirmed = False
        profile.save()

        response = self.client.post(
            "/api/accounts/login/",
            {"username": "unconfirmed", "password": "pass12345"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data.get("code"), "EMAIL_CONFIRMATION_PENDING")

    def test_login_success_after_confirmation(self):
        """Login succeeds once email is confirmed"""
        user = User.objects.create_user(username="willconfirm", email="willconfirm@example.com", password="pass12345")
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.email_confirmed = False
        profile.save()

        # Should be blocked first
        res = self.client.post(
            "/api/accounts/login/",
            {"username": "willconfirm", "password": "pass12345"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

        # Confirm the email
        profile.email_confirmed = True
        profile.save()

        # Should succeed now
        res = self.client.post(
            "/api/accounts/login/",
            {"username": "willconfirm", "password": "pass12345"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    # ---------------------------
    # Email confirmation tests
    # ---------------------------
    def test_confirm_email_valid_token(self):
        """Confirmation succeeds with a valid, non-expired token"""
        user = User.objects.create_user(username="confirmme", email="confirmme@example.com", password="pass12345")
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.email_confirmed = False
        profile.email_confirmation_token = "validtoken123"
        profile.email_confirmation_token_expires_at = timezone.now() + timezone.timedelta(hours=1)
        profile.save()

        response = self.client.get("/api/accounts/confirm-email/validtoken123/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        profile.refresh_from_db()
        self.assertTrue(profile.email_confirmed)
        self.assertIsNone(profile.email_confirmation_token)
        self.assertIsNone(profile.email_confirmation_token_expires_at)

    def test_confirm_email_invalid_token(self):
        """Confirmation fails with an invalid token"""
        response = self.client.get("/api/accounts/confirm-email/doesnotexist/")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.data)

    def test_confirm_email_expired_token(self):
        """Confirmation fails with an expired token"""
        user = User.objects.create_user(username="expireduser", email="expired@example.com", password="pass12345")
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.email_confirmed = False
        profile.email_confirmation_token = "expiredtoken123"
        profile.email_confirmation_token_expires_at = timezone.now() - timezone.timedelta(hours=1)
        profile.save()

        response = self.client.get("/api/accounts/confirm-email/expiredtoken123/")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.data)

    # ---------------------------
    # Resend confirmation tests
    # ---------------------------
    @patch("apps.future_wise.email_service.BrevoEmailService.send_account_confirmation_email")
    def test_resend_confirmation_success(self, mock_send):
        """Resend confirmation sends a new token for unconfirmed user"""
        user = User.objects.create_user(username="resendme", email="resendme@example.com", password="pass12345")
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.email_confirmed = False
        profile.email_confirmation_token = "oldtoken"
        profile.save()

        response = self.client.post(
            "/api/accounts/resend-confirmation/",
            {"email": "resendme@example.com"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_send.assert_called_once()

        profile.refresh_from_db()
        self.assertNotEqual(profile.email_confirmation_token, "oldtoken")

    def test_resend_confirmation_already_confirmed(self):
        """Resend returns error if email already confirmed"""
        response = self.client.post(
            "/api/accounts/resend-confirmation/",
            {"email": self.user_data["email"]},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.data)

    # ---------------------------
    # Logout test
    # ---------------------------
    def test_logout_user(self):
        """Authenticated user can logout"""
        self.client.login(username=self.user_data["username"], password=self.user_data["password"])
        response = self.client.post("/api/accounts/logout/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("message", response.data)

    # ---------------------------
    # Change password tests
    # ---------------------------
    def test_change_password_success(self):
        """Authenticated user can change their password"""
        self.client.login(username=self.user_data["username"], password=self.user_data["password"])
        response = self.client.post(
            "/api/accounts/change-password/",
            {"current_password": "testpass123", "new_password": "NewPass456!", "new_password2": "NewPass456!"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("message", response.data)

        # Verify new password works for login
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("NewPass456!"))

    def test_change_password_wrong_current(self):
        """Change password fails if current password is wrong"""
        self.client.login(username=self.user_data["username"], password=self.user_data["password"])
        response = self.client.post(
            "/api/accounts/change-password/",
            {"current_password": "wrongpassword", "new_password": "NewPass456!", "new_password2": "NewPass456!"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("current_password", response.data)

    def test_change_password_mismatch(self):
        """Change password fails if new passwords do not match"""
        self.client.login(username=self.user_data["username"], password=self.user_data["password"])
        response = self.client.post(
            "/api/accounts/change-password/",
            {"current_password": "testpass123", "new_password": "NewPass456!", "new_password2": "DifferentPass!"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_change_password_same_as_current(self):
        """Change password fails if new password is same as current"""
        self.client.login(username=self.user_data["username"], password=self.user_data["password"])
        response = self.client.post(
            "/api/accounts/change-password/",
            {"current_password": "testpass123", "new_password": "testpass123", "new_password2": "testpass123"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_change_password_unauthenticated(self):
        """Change password requires authentication"""
        response = self.client.post(
            "/api/accounts/change-password/",
            {"current_password": "testpass123", "new_password": "NewPass456!", "new_password2": "NewPass456!"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    # ---------------------------
    # Forgot password tests
    # ---------------------------
    @patch("apps.future_wise.email_service.BrevoEmailService.send_password_reset_email")
    def test_forgot_password_sends_email_for_confirmed_account(self, mock_send):
        """Forgot password sends a reset email for a confirmed account."""
        response = self.client.post(
            "/api/accounts/forgot-password/",
            {"email": self.user_data["email"]},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("message", response.data)
        mock_send.assert_called_once()

        profile = UserProfile.objects.get(user=self.user)
        self.assertIsNotNone(profile.password_reset_token)
        self.assertIsNotNone(profile.password_reset_token_expires_at)

    @patch("apps.future_wise.email_service.BrevoEmailService.send_password_reset_email")
    def test_forgot_password_returns_400_for_unknown_email(self, mock_send):
        """Forgot password returns 400 for unknown email (clear UX error)."""
        response = self.client.post(
            "/api/accounts/forgot-password/",
            {"email": "nobody@nowhere.com"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.data)
        mock_send.assert_not_called()

    @patch("apps.future_wise.email_service.BrevoEmailService.send_password_reset_email")
    def test_forgot_password_sends_for_unconfirmed_account(self, mock_send):
        """Forgot password sends reset email even if account email is not yet confirmed."""
        unconfirmed = User.objects.create_user(
            username="notconfirmed2", email="notconfirmed2@example.com", password="pass12345"
        )
        profile, _ = UserProfile.objects.get_or_create(user=unconfirmed)
        profile.email_confirmed = False
        profile.save()

        response = self.client.post(
            "/api/accounts/forgot-password/",
            {"email": "notconfirmed2@example.com"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        mock_send.assert_called_once()

        profile.refresh_from_db()
        self.assertIsNotNone(profile.password_reset_token)

    # ---------------------------
    # Reset password tests
    # ---------------------------
    def _set_reset_token(self, token, hours_from_now=1):
        from django.utils import timezone

        profile = UserProfile.objects.get(user=self.user)
        profile.password_reset_token = token
        profile.password_reset_token_expires_at = timezone.now() + timezone.timedelta(hours=hours_from_now)
        profile.save()

    def test_reset_password_success(self):
        """Valid token allows password reset."""
        self._set_reset_token("validresettoken123")
        response = self.client.post(
            "/api/accounts/reset-password/",
            {"token": "validresettoken123", "new_password": "NewSecure@99", "new_password2": "NewSecure@99"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("message", response.data)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("NewSecure@99"))

    def test_reset_password_clears_token_after_use(self):
        """Token and expiry are cleared after a successful reset."""
        self._set_reset_token("clearmetoken")
        self.client.post(
            "/api/accounts/reset-password/",
            {"token": "clearmetoken", "new_password": "NewSecure@99", "new_password2": "NewSecure@99"},
            format="json",
        )
        profile = UserProfile.objects.get(user=self.user)
        self.assertIsNone(profile.password_reset_token)
        self.assertIsNone(profile.password_reset_token_expires_at)

    def test_reset_password_invalid_token(self):
        """Invalid token returns 400."""
        response = self.client.post(
            "/api/accounts/reset-password/",
            {"token": "doesnotexist", "new_password": "NewSecure@99", "new_password2": "NewSecure@99"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.data)

    def test_reset_password_expired_token(self):
        """Expired token returns 400."""
        self._set_reset_token("expiredresettoken", hours_from_now=-1)
        response = self.client.post(
            "/api/accounts/reset-password/",
            {"token": "expiredresettoken", "new_password": "NewSecure@99", "new_password2": "NewSecure@99"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.data)

    def test_reset_password_mismatch(self):
        """Mismatched passwords return 400 validation error."""
        self._set_reset_token("mismatchtoken")
        response = self.client.post(
            "/api/accounts/reset-password/",
            {"token": "mismatchtoken", "new_password": "NewSecure@99", "new_password2": "DifferentPass@99"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_reset_password_token_cannot_be_reused(self):
        """After a successful reset the token cannot be used again."""
        self._set_reset_token("oneusetoken")
        self.client.post(
            "/api/accounts/reset-password/",
            {"token": "oneusetoken", "new_password": "NewSecure@99", "new_password2": "NewSecure@99"},
            format="json",
        )
        response = self.client.post(
            "/api/accounts/reset-password/",
            {"token": "oneusetoken", "new_password": "AnotherPass@99", "new_password2": "AnotherPass@99"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_login_works_after_password_reset(self):
        """User can log in with the new password after a successful reset."""
        self._set_reset_token("loginafterreset")
        self.client.post(
            "/api/accounts/reset-password/",
            {"token": "loginafterreset", "new_password": "FreshPass@2026", "new_password2": "FreshPass@2026"},
            format="json",
        )
        response = self.client.post(
            "/api/accounts/login/",
            {"username": self.user_data["username"], "password": "FreshPass@2026"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
