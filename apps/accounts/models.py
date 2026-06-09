from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()

LANGUAGE_CHOICES = [
    ("en", "English"),
    ("nl", "Dutch"),
]


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    email_confirmed = models.BooleanField(default=False)
    email_confirmation_token = models.CharField(max_length=128, null=True, blank=True)
    email_confirmation_token_expires_at = models.DateTimeField(null=True, blank=True)
    password_reset_token = models.CharField(max_length=128, null=True, blank=True)
    password_reset_token_expires_at = models.DateTimeField(null=True, blank=True)
    preferred_language = models.CharField(
        max_length=10,
        choices=LANGUAGE_CHOICES,
        default="en",
        help_text="User's preferred UI language.",
    )

    def __str__(self):
        return f"UserProfile({self.user.username}, confirmed={self.email_confirmed})"
