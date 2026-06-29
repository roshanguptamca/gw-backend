import logging
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from django.conf import settings
from django.contrib.auth import login
from django.http import HttpResponseRedirect
from django.views.decorators.csrf import csrf_exempt

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle

from .models import UserAuthProvider
from .oauth import (
    OAuthError,
    connect_social_account,
    consume_oauth_transaction,
    create_oauth_transaction,
    fetch_social_profile,
)

logger = logging.getLogger(__name__)
TRANSACTION_COOKIE = "gw_oauth_transaction"


class OAuthStartThrottle(SimpleRateThrottle):
    scope = "oauth_start"

    def get_cache_key(self, request, view):
        return self.get_ident(request)


class OAuthCallbackThrottle(SimpleRateThrottle):
    scope = "oauth_callback"

    def get_cache_key(self, request, view):
        return self.get_ident(request)


def _frontend_redirect(success, **params):
    base_url = settings.FRONTEND_AUTH_SUCCESS_URL if success else settings.FRONTEND_AUTH_ERROR_URL
    base_url = _normalize_frontend_callback_url(base_url)
    parsed = urlparse(base_url)
    query_params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query_params.update({key: value for key, value in params.items() if value is not None})
    merged_url = urlunparse(parsed._replace(query=urlencode(query_params, doseq=True)))
    return HttpResponseRedirect(merged_url)


def _normalize_frontend_callback_url(url):
    url = (url or "").strip()
    if not url:
        return f"{settings.FRONTEND_BASE_URL.rstrip('/')}/auth/callback"
    parsed = urlparse(url)
    if parsed.scheme:
        return url
    if url.startswith("//"):
        return f"https:{url}"
    if url.startswith("/"):
        return f"{settings.FRONTEND_BASE_URL.rstrip('/')}{url}"
    return f"https://{url}"


def _start_response(provider, link_user=None, json_response=False):
    try:
        oauth_transaction, authorization_url = create_oauth_transaction(provider, link_user=link_user)
    except OAuthError as exc:
        if json_response:
            return Response({"error": exc.code}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return _frontend_redirect(False, error=exc.code)
    response = (
        Response({"authorization_url": authorization_url}) if json_response else HttpResponseRedirect(authorization_url)
    )
    response.set_cookie(
        TRANSACTION_COOKIE,
        str(oauth_transaction.id),
        max_age=settings.OAUTH_TRANSACTION_TTL_MINUTES * 60,
        httponly=True,
        secure=settings.SESSION_COOKIE_SECURE,
        samesite=settings.SESSION_COOKIE_SAMESITE,
        path="/api/auth/oauth/",
    )
    return response


@api_view(["GET"])
@permission_classes([AllowAny])
@throttle_classes([OAuthStartThrottle])
def oauth_start(request, provider):
    return _start_response(provider)


@csrf_exempt
@api_view(["GET"])
@permission_classes([AllowAny])
@throttle_classes([OAuthCallbackThrottle])
def oauth_callback(request, provider):
    if request.query_params.get("error"):
        provider_error = request.query_params.get("error", "")
        error_description = request.query_params.get("error_description", "")
        logger.warning(
            "OAuth authorization rejected for %s: error=%s description=%s",
            provider,
            provider_error,
            error_description[:300],
        )
        if provider_error in {"access_denied", "user_cancelled_login", "user_cancelled_authorize"}:
            error = "oauth_cancelled"
        elif provider_error in {"unauthorized_scope_error", "invalid_scope"} or "scope" in error_description.lower():
            error = "provider_permissions_missing"
        elif "redirect" in error_description.lower():
            error = "provider_redirect_mismatch"
        else:
            error = "provider_unavailable"
        return _frontend_redirect(False, error=error)
    try:
        oauth_transaction = consume_oauth_transaction(
            request.COOKIES.get(TRANSACTION_COOKIE),
            provider,
            request.query_params.get("state"),
        )
        code = request.query_params.get("code")
        if not code:
            raise OAuthError("invalid_or_expired")
        social_profile = fetch_social_profile(oauth_transaction, code)
        user, created, profile_complete = connect_social_account(
            provider,
            social_profile,
            link_user=oauth_transaction.link_user,
        )
        login(request, user)
    except OAuthError as exc:
        logger.info("OAuth callback rejected for %s: %s", provider, exc.code)
        response = _frontend_redirect(False, error=exc.code)
    except Exception:
        logger.exception("Unexpected OAuth callback failure for %s", provider)
        response = _frontend_redirect(False, error="provider_unavailable")
    else:
        response = _frontend_redirect(
            True,
            status="success",
            new="1" if created else "0",
            profile_complete="1" if profile_complete else "0",
        )
    response.delete_cookie(TRANSACTION_COOKIE, path="/api/auth/oauth/")
    return response


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@throttle_classes([OAuthStartThrottle])
def oauth_link(request):
    provider = request.data.get("provider", "")
    return _start_response(provider, link_user=request.user, json_response=True)


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def oauth_unlink(request, provider):
    social_account = UserAuthProvider.objects.filter(user=request.user, provider=provider).first()
    if not social_account:
        return Response({"error": "provider_not_linked"}, status=status.HTTP_404_NOT_FOUND)
    has_other_method = (
        request.user.has_usable_password()
        or UserAuthProvider.objects.filter(
            user=request.user,
        )
        .exclude(pk=social_account.pk)
        .exists()
    )
    if not has_other_method:
        return Response({"error": "last_login_method"}, status=status.HTTP_400_BAD_REQUEST)
    social_account.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)
