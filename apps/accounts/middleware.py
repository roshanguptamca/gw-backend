# Create this file: apps/accounts/middleware.py (or any app)

from django.middleware.csrf import get_token


class ForceCSRFCookieMiddleware:
    """
    Middleware that forces Django to set the CSRF cookie on every response.
    This ensures the frontend always has access to the token.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Force CSRF cookie to be set
        get_token(request)

        response = self.get_response(request)
        return response