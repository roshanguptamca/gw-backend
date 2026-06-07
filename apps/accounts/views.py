import logging
import secrets

from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from drf_spectacular.utils import (
    extend_schema,
    OpenApiExample,
    OpenApiResponse,
    inline_serializer,
)
from rest_framework import serializers as drf_serializers
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.parsers import JSONParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import UserRegistrationSerializer

logger = logging.getLogger(__name__)


class PlainTextJSONParser(JSONParser):
    """Accept text/plain bodies as JSON (sent by some fetch() calls without explicit Content-Type headers)."""

    media_type = "text/plain"


# ------------------------------------------------------------------
# CSRF INIT VIEW (frontend must call this ONCE before login/logout)
# PATH: DO NOT CHANGE (add URL only if missing)
# ------------------------------------------------------------------
@extend_schema(
    tags=["Accounts"],
    summary="Get CSRF token",
    description=(
        "Sets the `csrftoken` cookie and returns the CSRF token value. "
        "The frontend **must** call this endpoint once before making any "
        "mutating request (POST/PUT/DELETE). Include the returned token "
        "in subsequent requests via the `X-CSRFToken` header."
    ),
    responses={
        200: inline_serializer(
            "CsrfResponse",
            fields={
                "detail": drf_serializers.CharField(default="CSRF cookie set"),
                "csrfToken": drf_serializers.CharField(),
            },
        )
    },
    examples=[
        OpenApiExample(
            "Success",
            value={"detail": "CSRF cookie set", "csrfToken": "abc123xyz"},
            response_only=True,
        )
    ],
    auth=[],
)
@csrf_exempt  # CRITICAL: Exempt this endpoint from CSRF checking
def csrf(request):
    """
    Provides CSRF token to frontend.
    This endpoint MUST be csrf_exempt because it's called to GET the token.
    """
    csrf_token = get_token(request)

    response = JsonResponse({"detail": "CSRF cookie set", "csrfToken": csrf_token})

    # Explicitly set cookie with correct settings for production
    response.set_cookie(
        "csrftoken",
        csrf_token,
        max_age=31449600,  # 1 year
        secure=True,  # Required for HTTPS
        httponly=False,  # Must be False - JS needs to read it
        samesite="None",  # Required for cross-origin
        path="/",
    )

    return response


# ------------------------------------------------------------------
# REGISTER
# ------------------------------------------------------------------
@extend_schema(
    tags=["Accounts"],
    summary="Register a new user",
    description="Create a new user account. Returns the new user's `id` on success.",
    request=UserRegistrationSerializer,
    responses={
        201: inline_serializer(
            "RegisterResponse",
            fields={
                "message": drf_serializers.CharField(default="User created"),
                "id": drf_serializers.IntegerField(),
            },
        ),
        400: inline_serializer(
            "RegisterErrorResponse",
            fields={
                "username": drf_serializers.ListField(child=drf_serializers.CharField(), required=False),
                "email": drf_serializers.ListField(child=drf_serializers.CharField(), required=False),
                "password": drf_serializers.ListField(child=drf_serializers.CharField(), required=False),
            },
        ),
    },
    examples=[
        OpenApiExample(
            "Register request",
            value={
                "username": "john_doe",
                "email": "john@example.com",
                "password": "SecurePass123!",
                "password2": "SecurePass123!",
            },
            request_only=True,
        ),
        OpenApiExample(
            "Register success",
            value={"message": "User created", "id": 42},
            response_only=True,
            status_codes=["201"],
        ),
        OpenApiExample(
            "Validation error",
            value={"password": ["Passwords must match"]},
            response_only=True,
            status_codes=["400"],
        ),
    ],
    auth=[],
)
@method_decorator(ensure_csrf_cookie, name="dispatch")
class RegisterView(APIView):
    permission_classes = [AllowAny]
    parser_classes = [JSONParser, PlainTextJSONParser]

    def post(self, request):
        serializer = UserRegistrationSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            return Response({"message": "User created", "id": user.id}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ------------------------------------------------------------------
# LOGIN
# ------------------------------------------------------------------
@extend_schema(
    tags=["Accounts"],
    summary="Log in",
    description=(
        "Authenticate with `username` and `password`. "
        "On success, a session cookie (`sessionid`) is set. "
        "All subsequent requests to authenticated endpoints must carry this cookie. "
        "Returns `EMAIL_CONFIRMATION_PENDING` error code if the user has not yet confirmed their email."
    ),
    request=inline_serializer(
        "LoginRequest",
        fields={
            "username": drf_serializers.CharField(),
            "password": drf_serializers.CharField(),
        },
    ),
    responses={
        200: inline_serializer(
            "LoginResponse",
            fields={"message": drf_serializers.CharField(default="Logged in")},
        ),
        401: inline_serializer(
            "LoginErrorResponse",
            fields={
                "error": drf_serializers.CharField(default="Invalid credentials"),
                "code": drf_serializers.CharField(required=False),
            },
        ),
    },
    examples=[
        OpenApiExample(
            "Login request",
            value={"username": "john_doe", "password": "SecurePass123!"},
            request_only=True,
        ),
        OpenApiExample(
            "Login success",
            value={"message": "Logged in"},
            response_only=True,
            status_codes=["200"],
        ),
        OpenApiExample(
            "Invalid credentials",
            value={"error": "Invalid credentials"},
            response_only=True,
            status_codes=["401"],
        ),
        OpenApiExample(
            "Email confirmation pending",
            value={
                "error": "Your email confirmation is pending. Please check your inbox and confirm your email before logging in.",
                "code": "EMAIL_CONFIRMATION_PENDING",
            },
            response_only=True,
            status_codes=["401"],
        ),
    ],
    auth=[],
)
@method_decorator(ensure_csrf_cookie, name="dispatch")
class LoginView(APIView):
    permission_classes = [AllowAny]
    parser_classes = [JSONParser, PlainTextJSONParser]

    def post(self, request):
        username = request.data.get("username")
        password = request.data.get("password")

        user = authenticate(request, username=username, password=password)

        if not user:
            return Response({"error": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)

        # Block login if email is not confirmed
        profile = getattr(user, "profile", None)
        if profile is not None and not profile.email_confirmed:
            return Response(
                {
                    "error": "Your email confirmation is pending. Please check your inbox and confirm your email before logging in.",
                    "code": "EMAIL_CONFIRMATION_PENDING",
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )

        login(request, user)
        return Response({"message": "Logged in"}, status=status.HTTP_200_OK)


# ------------------------------------------------------------------
# LOGOUT
# ------------------------------------------------------------------
@extend_schema(
    tags=["Accounts"],
    summary="Log out",
    description="Invalidate the current session. The `sessionid` cookie is cleared.",
    request=None,
    responses={
        200: inline_serializer(
            "LogoutResponse",
            fields={"message": drf_serializers.CharField(default="Logged out")},
        ),
    },
    examples=[
        OpenApiExample(
            "Logout success",
            value={"message": "Logged out"},
            response_only=True,
            status_codes=["200"],
        )
    ],
)
@method_decorator(ensure_csrf_cookie, name="dispatch")
class LogoutView(APIView):
    def post(self, request):
        logout(request)
        return Response({"message": "Logged out"}, status=status.HTTP_200_OK)


# ------------------------------------------------------------------
# CURRENT USER
# ------------------------------------------------------------------
@extend_schema(
    tags=["Accounts"],
    summary="Get current user",
    description="Returns the profile of the currently authenticated user.",
    responses={
        200: inline_serializer(
            "MeResponse",
            fields={
                "id": drf_serializers.IntegerField(),
                "username": drf_serializers.CharField(),
                "email": drf_serializers.EmailField(),
                "first_name": drf_serializers.CharField(),
                "last_name": drf_serializers.CharField(),
            },
        ),
        403: OpenApiResponse(description="Not authenticated"),
    },
    examples=[
        OpenApiExample(
            "Authenticated user",
            value={
                "id": 42,
                "username": "john_doe",
                "email": "john@example.com",
                "first_name": "John",
                "last_name": "Doe",
            },
            response_only=True,
            status_codes=["200"],
        )
    ],
)
class MeView(APIView):
    permission_classes = [IsAuthenticated]

    @csrf_exempt
    def get(self, request):
        user = request.user
        return Response(
            {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
            }
        )


@extend_schema(
    tags=["Accounts"],
    summary="Check session status",
    description=(
        "Returns whether the caller has an active authenticated session. "
        "Safe to call without a CSRF token — use this on page load to restore auth state."
    ),
    responses={
        200: inline_serializer(
            "SessionResponse",
            fields={
                "authenticated": drf_serializers.BooleanField(),
                "user": inline_serializer(
                    "SessionUser",
                    fields={
                        "id": drf_serializers.IntegerField(required=False),
                        "username": drf_serializers.CharField(required=False),
                        "email": drf_serializers.EmailField(required=False),
                    },
                    required=False,
                ),
            },
        )
    },
    examples=[
        OpenApiExample(
            "Authenticated",
            value={"authenticated": True, "user": {"id": 42, "username": "john_doe", "email": "john@example.com"}},
            response_only=True,
            status_codes=["200"],
        ),
        OpenApiExample(
            "Not authenticated",
            value={"authenticated": False},
            response_only=True,
            status_codes=["200"],
        ),
    ],
    auth=[],
)
@api_view(["GET"])
@permission_classes([AllowAny])
@csrf_exempt  # GET request, read-only, safe to exempt
def session_view(request):
    """
    Check if user has an active session.
    Called on page load, must work without CSRF token.
    """
    if request.user.is_authenticated:
        return Response(
            {
                "authenticated": True,
                "user": {
                    "id": request.user.id,
                    "username": request.user.username,
                    "email": request.user.email,
                },
            }
        )
    return Response({"authenticated": False})


# ------------------------------------------------------------------
# CONFIRM EMAIL
# ------------------------------------------------------------------
@extend_schema(
    tags=["Accounts"],
    summary="Confirm email address",
    description=(
        "Validates the email-confirmation token sent during registration. "
        "On success, marks the user's email as confirmed and clears the token. "
        "The token is valid for 24 hours."
    ),
    request=None,
    responses={
        200: inline_serializer(
            "ConfirmEmailResponse",
            fields={"message": drf_serializers.CharField(default="Email confirmed successfully.")},
        ),
        400: inline_serializer(
            "ConfirmEmailErrorResponse",
            fields={"error": drf_serializers.CharField()},
        ),
    },
    examples=[
        OpenApiExample(
            "Success",
            value={"message": "Email confirmed successfully."},
            response_only=True,
            status_codes=["200"],
        ),
        OpenApiExample(
            "Invalid or expired token",
            value={"error": "This confirmation link is invalid or has expired."},
            response_only=True,
            status_codes=["400"],
        ),
    ],
    auth=[],
)
@api_view(["GET"])
@permission_classes([AllowAny])
@csrf_exempt
def confirm_email_view(request, token):
    """Confirm a user's email address using the token from the confirmation email."""
    from .models import UserProfile

    try:
        profile = UserProfile.objects.select_related("user").get(email_confirmation_token=token)
    except UserProfile.DoesNotExist:
        return Response(
            {"error": "This confirmation link is invalid or has expired."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if profile.email_confirmation_token_expires_at is None or timezone.now() > profile.email_confirmation_token_expires_at:
        return Response(
            {"error": "This confirmation link is invalid or has expired."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    profile.email_confirmed = True
    profile.email_confirmation_token = None
    profile.email_confirmation_token_expires_at = None
    profile.save(update_fields=["email_confirmed", "email_confirmation_token", "email_confirmation_token_expires_at"])

    return Response({"message": "Email confirmed successfully."}, status=status.HTTP_200_OK)


# ------------------------------------------------------------------
# RESEND CONFIRMATION EMAIL
# ------------------------------------------------------------------
@extend_schema(
    tags=["Accounts"],
    summary="Resend confirmation email",
    description=(
        "Generates a new confirmation token and sends a fresh confirmation email. "
        "Only valid for users whose email has not yet been confirmed."
    ),
    request=inline_serializer(
        "ResendConfirmationRequest",
        fields={"email": drf_serializers.EmailField()},
    ),
    responses={
        200: inline_serializer(
            "ResendConfirmationResponse",
            fields={"message": drf_serializers.CharField(default="Confirmation email resent.")},
        ),
        400: inline_serializer(
            "ResendConfirmationErrorResponse",
            fields={"error": drf_serializers.CharField()},
        ),
    },
    examples=[
        OpenApiExample(
            "Success",
            value={"message": "Confirmation email resent."},
            response_only=True,
            status_codes=["200"],
        ),
        OpenApiExample(
            "Already confirmed",
            value={"error": "This email address is already confirmed."},
            response_only=True,
            status_codes=["400"],
        ),
    ],
    auth=[],
)
@method_decorator(ensure_csrf_cookie, name="dispatch")
class ResendConfirmationView(APIView):
    permission_classes = [AllowAny]
    parser_classes = [JSONParser, PlainTextJSONParser]

    def post(self, request):
        from django.contrib.auth import get_user_model
        from .models import UserProfile
        from apps.future_wise.email_service import BrevoEmailService, BrevoDeliveryError

        email = request.data.get("email", "").strip().lower()
        if not email:
            return Response({"error": "Email is required."}, status=status.HTTP_400_BAD_REQUEST)

        UserModel = get_user_model()
        # Try by email first, fall back to username (frontend may send either)
        user = (
            UserModel.objects.filter(email__iexact=email).first()
            or UserModel.objects.filter(username__iexact=email).first()
        )
        if user is None:
            # Return generic success to avoid user enumeration
            return Response({"message": "Confirmation email resent."}, status=status.HTTP_200_OK)

        profile, _ = UserProfile.objects.get_or_create(user=user)

        if profile.email_confirmed:
            return Response(
                {"error": "This email address is already confirmed."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Generate a fresh token
        token = secrets.token_urlsafe(32)
        profile.email_confirmation_token = token
        profile.email_confirmation_token_expires_at = timezone.now() + timezone.timedelta(hours=24)
        profile.save(update_fields=["email_confirmation_token", "email_confirmation_token_expires_at"])

        frontend_base = getattr(settings, "FRONTEND_BASE_URL", "https://www.guidewisey.com")
        confirmation_url = f"{frontend_base}/confirm-email/{token}"
        try:
            BrevoEmailService().send_account_confirmation_email(user.email, confirmation_url)
        except BrevoDeliveryError as exc:
            logger.error("Failed to resend confirmation email to %s: %s", user.email, exc)
        except Exception as exc:
            logger.error("Unexpected error resending confirmation email to %s: %s", user.email, exc)

        return Response({"message": "Confirmation email resent."}, status=status.HTTP_200_OK)

