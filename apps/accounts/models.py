import uuid

from django.contrib.auth import get_user_model
from django.db import models
from django.utils import timezone

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
    avatar_url = models.URLField(max_length=500, blank=True)
    timezone = models.CharField(max_length=64, blank=True)
    profile_completed = models.BooleanField(default=False)

    def __str__(self):
        return f"UserProfile({self.user.username}, confirmed={self.email_confirmed})"


class UserAuthProvider(models.Model):
    PROVIDER_CHOICES = [
        ("google", "Google"),
        ("facebook", "Facebook"),
        ("linkedin", "LinkedIn"),
        ("oidc", "OpenID Connect"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="auth_providers")
    provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES)
    provider_user_id = models.CharField(max_length=255)
    email = models.EmailField(blank=True)
    email_verified = models.BooleanField(default=False)
    display_name = models.CharField(max_length=255, blank=True)
    avatar_url = models.URLField(max_length=500, blank=True)
    locale = models.CharField(max_length=35, blank=True)
    timezone = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("provider", "provider_user_id"),
                name="unique_provider_identity",
            ),
            models.UniqueConstraint(
                fields=("user", "provider"),
                name="unique_user_provider",
            ),
        ]

    def __str__(self):
        return f"{self.provider}:{self.provider_user_id}"


class OAuthTransaction(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider = models.CharField(max_length=20, choices=UserAuthProvider.PROVIDER_CHOICES)
    state_digest = models.CharField(max_length=64)
    nonce = models.CharField(max_length=128, blank=True)
    code_verifier = models.CharField(max_length=128)
    redirect_uri = models.URLField(max_length=500)
    link_user = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="oauth_transactions",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)

    @property
    def is_expired(self):
        return self.expires_at <= timezone.now()
