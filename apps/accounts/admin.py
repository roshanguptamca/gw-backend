from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import OAuthTransaction, UserAuthProvider, UserProfile

User = get_user_model()


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = "Email Confirmation"
    fields = (
        "email_confirmed",
        "email_confirmation_token",
        "email_confirmation_token_expires_at",
    )
    readonly_fields = ("email_confirmation_token", "email_confirmation_token_expires_at")


# Re-register User with the inline attached
admin.site.unregister(User)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    inlines = (UserProfileInline,)
    list_display = (
        "username",
        "email",
        "first_name",
        "last_name",
        "is_staff",
        "is_active",
        "email_confirmed",
        "date_joined",
    )
    list_filter = BaseUserAdmin.list_filter + ("profile__email_confirmed",)

    @admin.display(boolean=True, description="Email confirmed")
    def email_confirmed(self, obj):
        profile = getattr(obj, "profile", None)
        return profile.email_confirmed if profile else False


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "email",
        "email_confirmed",
        "token_expires_at",
    )
    list_filter = ("email_confirmed",)
    search_fields = ("user__username", "user__email")
    readonly_fields = (
        "user",
        "email_confirmation_token",
        "email_confirmation_token_expires_at",
    )
    fields = (
        "user",
        "email_confirmed",
        "email_confirmation_token",
        "email_confirmation_token_expires_at",
    )
    actions = ["mark_confirmed", "clear_confirmation_token"]

    @admin.display(description="Email")
    def email(self, obj):
        return obj.user.email

    @admin.display(description="Token expires")
    def token_expires_at(self, obj):
        return obj.email_confirmation_token_expires_at or "—"

    @admin.action(description="Mark selected users as email-confirmed")
    def mark_confirmed(self, request, queryset):
        updated = queryset.update(
            email_confirmed=True,
            email_confirmation_token=None,
            email_confirmation_token_expires_at=None,
        )
        self.message_user(request, f"{updated} user(s) marked as email-confirmed.")

    @admin.action(description="Clear confirmation token (force re-send)")
    def clear_confirmation_token(self, request, queryset):
        updated = queryset.update(
            email_confirmation_token=None,
            email_confirmation_token_expires_at=None,
        )
        self.message_user(request, f"Confirmation token cleared for {updated} user(s).")


@admin.register(UserAuthProvider)
class UserAuthProviderAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "provider",
        "provider_user_id",
        "email",
        "email_verified",
        "created_at",
        "updated_at",
    )
    search_fields = ("user__email", "user__username", "email", "provider_user_id", "display_name")
    list_filter = ("provider", "email_verified", "created_at")
    readonly_fields = ("created_at", "updated_at")


@admin.register(OAuthTransaction)
class OAuthTransactionAdmin(admin.ModelAdmin):
    list_display = ("id", "provider", "link_user", "created_at", "expires_at", "used_at")
    list_filter = ("provider", "created_at", "used_at")
    readonly_fields = (
        "id",
        "provider",
        "state_digest",
        "nonce",
        "code_verifier",
        "redirect_uri",
        "link_user",
        "created_at",
        "expires_at",
        "used_at",
    )
