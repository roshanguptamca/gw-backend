# tests/accounts/test_views.py

from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status

User = get_user_model()


class AccountsAPITestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        # Pre-created user for login tests
        self.user_data = {
            "username": "testuser",
            "email": "testuser@example.com",
            "password": "testpass123",
            "password2": "testpass123",
        }
        self.user = User.objects.create_user(
            username=self.user_data["username"],
            email=self.user_data["email"],
            password=self.user_data["password"]
        )

    # ---------------------------
    # Registration tests
    # ---------------------------
    def test_register_user_success(self):
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
        """User can login with correct credentials"""
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

    # ---------------------------
    # Logout test
    # ---------------------------
    def test_logout_user(self):
        """Authenticated user can logout"""
        self.client.login(username=self.user_data["username"], password=self.user_data["password"])
        response = self.client.post("/api/accounts/logout/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("message", response.data)
