import logging
import secrets

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

logger = logging.getLogger(__name__)

User = get_user_model()


class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True, required=True)
    account_type = serializers.ChoiceField(
        choices=[("buyer", "Buyer"), ("seller", "Seller")],
        required=False,
        default="buyer",
        write_only=True,
    )
    business_name = serializers.CharField(
        required=False, allow_blank=True, max_length=150, write_only=True
    )

    class Meta:
        model = User
        fields = ("username", "email", "password", "password2", "account_type", "business_name")
        extra_kwargs = {
            "email": {"required": True},
            "username": {"required": True},
        }

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError(_("An account with this email address already exists."))
        return value

    def validate(self, attrs):
        if attrs["password"] != attrs["password2"]:
            raise serializers.ValidationError({"password": _("Passwords must match")})
        if attrs.get("account_type") == "seller" and not attrs.get("business_name", "").strip():
            raise serializers.ValidationError({"business_name": _("Business name is required for seller accounts.")})
        return attrs

    def create(self, validated_data):
        from .models import UserProfile
        from apps.future_wise.email_service import BrevoEmailService, BrevoDeliveryError

        account_type = validated_data.pop("account_type", "buyer")
        business_name = validated_data.pop("business_name", "").strip()
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

        # Create SellerProfile + draft Shop for seller registrations
        if account_type == "seller":
            try:
                from apps.marketplace.models import SellerProfile, Shop
                import re
                seller_profile = SellerProfile.objects.create(
                    user=user,
                    business_name=business_name or user.username,
                    created_by=user,
                )
                # Generate a unique slug from the business name
                base_slug = re.sub(r"[^\w]+", "-", business_name.lower()).strip("-") or user.username
                slug = base_slug
                counter = 1
                while Shop.objects.filter(slug=slug).exists():
                    slug = f"{base_slug}-{counter}"
                    counter += 1
                Shop.objects.create(
                    owner=user,
                    seller_profile=seller_profile,
                    name=business_name or user.username,
                    slug=slug,
                    is_active=False,    # inactive until approved
                    is_approved=False,  # requires admin approval
                )
            except Exception as exc:
                logger.error("Failed to create seller profile for %s: %s", user.username, exc)

        # Link any guest orders placed with this email to the new account
        try:
            from apps.marketplace.services import link_guest_orders_to_user
            link_guest_orders_to_user(user)
        except Exception as exc:
            logger.warning("Failed to link guest orders for %s: %s", user.email, exc)

        # Send confirmation email (best-effort)
        frontend_base = getattr(settings, "FRONTEND_BASE_URL", "https://www.guidewisey.com")
        confirmation_url = f"{frontend_base}/confirm-email/{token}"
        try:
            BrevoEmailService().send_account_confirmation_email(user.email, confirmation_url)
        except BrevoDeliveryError as exc:
            logger.error("Failed to send confirmation email to %s: %s", user.email, exc)
        except Exception as exc:
            logger.error("Unexpected error sending confirmation email to %s: %s", user.email, exc)

        return user


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    new_password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    new_password2 = serializers.CharField(write_only=True, required=True)

    def validate_current_password(self, value):
        user = self.context["request"].user
        if user.has_usable_password() and not user.check_password(value):
            raise serializers.ValidationError(_("Current password is incorrect."))
        return value

    def validate(self, attrs):
        user = self.context["request"].user
        if user.has_usable_password() and not attrs.get("current_password"):
            raise serializers.ValidationError({"current_password": _("Current password is required.")})
        if attrs["new_password"] != attrs["new_password2"]:
            raise serializers.ValidationError({"new_password": _("New passwords must match.")})
        if attrs.get("current_password") == attrs["new_password"]:
            raise serializers.ValidationError({"new_password": _("New password must differ from current password.")})
        return attrs

    def save(self, **kwargs):
        user = self.context["request"].user
        user.set_password(self.validated_data["new_password"])
        user.save(update_fields=["password"])
        return user


class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)


class ResetPasswordSerializer(serializers.Serializer):
    token = serializers.CharField(required=True)
    new_password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    new_password2 = serializers.CharField(write_only=True, required=True)

    def validate(self, attrs):
        if attrs["new_password"] != attrs["new_password2"]:
            raise serializers.ValidationError({"new_password": _("Passwords must match.")})
        return attrs
