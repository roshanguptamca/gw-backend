from django.contrib.auth import authenticate, login, logout
from django.views.decorators.csrf import ensure_csrf_cookie
from django.utils.decorators import method_decorator
from django.http import JsonResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.views import APIView
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.parsers import JSONParser


class PlainTextJSONParser(JSONParser):
    """Accept text/plain bodies as JSON (sent by some fetch() calls without explicit Content-Type headers)."""
    media_type = "text/plain"
from django.views.decorators.csrf import csrf_exempt
from .serializers import UserRegistrationSerializer
from django.middleware.csrf import get_token
from django.middleware.csrf import get_token
from drf_spectacular.utils import (
    extend_schema,
    OpenApiExample,
    OpenApiResponse,
    inline_serializer,
)
from rest_framework import serializers as drf_serializers


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
        "All subsequent requests to authenticated endpoints must carry this cookie."
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
            fields={"error": drf_serializers.CharField(default="Invalid credentials")},
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
