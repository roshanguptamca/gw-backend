import logging
import secrets

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.utils import timezone
from rest_framework import serializers

logger = logging.getLogger(__name__)

User = get_user_model()


class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True, required=True)  # confirm password

    class Meta:
        model = User
        fields = ("username", "email", "password", "password2")
        extra_kwargs = {
            "email": {"required": True},
            "username": {"required": True},
        }

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("An account with this email address already exists.")
        return value

    def validate(self, attrs):
        if attrs["password"] != attrs["password2"]:
            raise serializers.ValidationError({"password": "Passwords must match"})
        return attrs

    def create(self, validated_data):
        from .models import UserProfile
        from apps.future_wise.email_service import BrevoEmailService, BrevoDeliveryError

        validated_data.pop("password2")
        user = User.objects.create_user(
            username=validated_data["username"],
            email=validated_data["email"],
            password=validated_data["password"],
        )
        user.is_active = True
        user.save()

        # Generate a secure confirmation token (valid for 24 hours)
        token = secrets.token_urlsafe(32)
        expires_at = timezone.now() + timezone.timedelta(hours=24)

        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.email_confirmed = False
        profile.email_confirmation_token = token
        profile.email_confirmation_token_expires_at = expires_at
        profile.save()

        # Send confirmation email (best-effort — don't fail registration if email fails)
        frontend_base = getattr(settings, "FRONTEND_BASE_URL", "https://www.guidewisey.com")
        confirmation_url = f"{frontend_base}/confirm-email/{token}"
        try:
            BrevoEmailService().send_account_confirmation_email(user.email, confirmation_url)
        except BrevoDeliveryError as exc:
            logger.error("Failed to send confirmation email to %s: %s", user.email, exc)
        except Exception as exc:
            logger.error("Unexpected error sending confirmation email to %s: %s", user.email, exc)

        return user

