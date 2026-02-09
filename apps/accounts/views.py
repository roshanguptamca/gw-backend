from django.contrib.auth import authenticate, login, logout
from django.views.decorators.csrf import ensure_csrf_cookie
from django.utils.decorators import method_decorator
from django.http import JsonResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.views import APIView
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from django.views.decorators.csrf import csrf_exempt
from .serializers import UserRegistrationSerializer
from django.middleware.csrf import get_token
from django.middleware.csrf import get_token

# ------------------------------------------------------------------
# CSRF INIT VIEW (frontend must call this ONCE before login/logout)
# PATH: DO NOT CHANGE (add URL only if missing)
# ------------------------------------------------------------------
# Simple CSRF endpoint for frontend to fetch the cookie
@csrf_exempt  # CRITICAL: Exempt this endpoint from CSRF checking
def csrf(request):
    """
    Provides CSRF token to frontend.
    This endpoint MUST be csrf_exempt because it's called to GET the token.
    """
    csrf_token = get_token(request)

    response = JsonResponse({
        "detail": "CSRF cookie set",
        "csrfToken": csrf_token
    })

    # Explicitly set cookie with correct settings for production
    response.set_cookie(
        'csrftoken',
        csrf_token,
        max_age=31449600,  # 1 year
        secure=True,  # Required for HTTPS
        httponly=False,  # Must be False - JS needs to read it
        samesite='None',  # Required for cross-origin
        path='/',
    )

    return response

# ------------------------------------------------------------------
# REGISTER
# ------------------------------------------------------------------
@method_decorator(ensure_csrf_cookie, name='dispatch')
class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = UserRegistrationSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            return Response(
                {"message": "User created", "id": user.id},
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ------------------------------------------------------------------
# LOGIN
# ------------------------------------------------------------------
@method_decorator(ensure_csrf_cookie, name='dispatch')
class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        username = request.data.get("username")
        password = request.data.get("password")

        user = authenticate(request, username=username, password=password)

        if not user:
            return Response(
                {"error": "Invalid credentials"},
                status=status.HTTP_401_UNAUTHORIZED
            )

        login(request, user)
        return Response(
            {"message": "Logged in"},
            status=status.HTTP_200_OK
        )


# ------------------------------------------------------------------
# LOGOUT
# ------------------------------------------------------------------
@method_decorator(ensure_csrf_cookie, name='dispatch')
class LogoutView(APIView):
    def post(self, request):
        logout(request)
        return Response(
            {"message": "Logged out"},
            status=status.HTTP_200_OK
        )


# ------------------------------------------------------------------
# CURRENT USER
# ------------------------------------------------------------------
class MeView(APIView):
    permission_classes = [IsAuthenticated]

    @csrf_exempt
    def get(self, request):
        user = request.user
        return Response({
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name
        })


@api_view(['GET'])
@csrf_exempt  # GET endpoint, read-only, safe to exempt
def session_view(request):
    """
    Check if user has an active session.
    Called on page load before CSRF token exists.
    """
    if request.user.is_authenticated:
        return Response({
            'authenticated': True,
            'user': {
                'id': request.user.id,
                'username': request.user.username,
                'email': request.user.email,
            }
        })
    return Response({'authenticated': False})