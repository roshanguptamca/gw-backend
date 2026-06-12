import base64
import hashlib
import logging
import secrets
from dataclasses import dataclass
from urllib.parse import urlencode

import jwt
import requests
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import OAuthTransaction, UserAuthProvider, UserProfile

logger = logging.getLogger(__name__)
User = get_user_model()


class OAuthError(Exception):
    def __init__(self, code, message=None):
        self.code = code
        super().__init__(message or code)


@dataclass
class SocialProfile:
    provider_user_id: str
    email: str = ""
    email_verified: bool = False
    first_name: str = ""
    last_name: str = ""
    display_name: str = ""
    avatar_url: str = ""
    locale: str = ""
    timezone: str = ""


OIDC_PROVIDER_METADATA = {
    "google": {
        "issuer": "https://accounts.google.com",
        "authorization_endpoint": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_endpoint": "https://oauth2.googleapis.com/token",
        "userinfo_endpoint": "https://openidconnect.googleapis.com/v1/userinfo",
        "jwks_uri": "https://www.googleapis.com/oauth2/v3/certs",
        "supports_pkce": True,
        "supports_nonce": True,
    },
    "linkedin": {
        "issuer": "https://www.linkedin.com/oauth",
        "authorization_endpoint": "https://www.linkedin.com/oauth/v2/authorization",
        "token_endpoint": "https://www.linkedin.com/oauth/v2/accessToken",
        "userinfo_endpoint": "https://api.linkedin.com/v2/userinfo",
        "jwks_uri": "https://www.linkedin.com/oauth/openid/jwks",
        "supports_pkce": False,
        "supports_nonce": False,
    },
}


def _provider_settings(provider):
    if provider not in dict(UserAuthProvider.PROVIDER_CHOICES):
        raise OAuthError("provider_unavailable")

    prefix = provider.upper()
    client_id = getattr(settings, f"{prefix}_CLIENT_ID", "")
    client_secret = getattr(settings, f"{prefix}_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        raise OAuthError("provider_unavailable")

    if provider == "facebook":
        version = settings.FACEBOOK_GRAPH_API_VERSION
        return {
            "client_id": client_id,
            "client_secret": client_secret,
            "authorization_endpoint": f"https://www.facebook.com/{version}/dialog/oauth",
            "token_endpoint": f"https://graph.facebook.com/{version}/oauth/access_token",
            "userinfo_endpoint": f"https://graph.facebook.com/{version}/me",
            "scopes": "email public_profile",
            "issuer": "",
            "jwks_uri": "",
            "supports_pkce": True,
            "supports_nonce": False,
        }

    if provider in OIDC_PROVIDER_METADATA:
        return {
            **OIDC_PROVIDER_METADATA[provider],
            "client_id": client_id,
            "client_secret": client_secret,
            "scopes": "openid profile email",
        }

    discovery_url = settings.OIDC_ISSUER_URL.rstrip("/") + "/.well-known/openid-configuration"
    try:
        response = requests.get(discovery_url, timeout=10)
        response.raise_for_status()
        metadata = response.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("OAuth discovery failed for %s: %s", provider, exc)
        raise OAuthError("provider_unavailable") from exc

    required = ("authorization_endpoint", "token_endpoint", "userinfo_endpoint", "issuer", "jwks_uri")
    if any(not metadata.get(key) for key in required):
        raise OAuthError("provider_unavailable")
    metadata.update(
        client_id=client_id,
        client_secret=client_secret,
        scopes="openid profile email",
        supports_pkce="S256" in metadata.get("code_challenge_methods_supported", []),
        supports_nonce="nonce" in metadata.get("claims_supported", []),
    )
    return metadata


def _callback_url(provider):
    return f"{settings.OAUTH_REDIRECT_BASE_URL.rstrip('/')}/api/auth/oauth/{provider}/callback"


def _code_challenge(verifier):
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def create_oauth_transaction(provider, link_user=None):
    config = _provider_settings(provider)
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    nonce = secrets.token_urlsafe(32) if config.get("supports_nonce") else ""
    redirect_uri = _callback_url(provider)
    oauth_transaction = OAuthTransaction.objects.create(
        provider=provider,
        state_digest=hashlib.sha256(state.encode()).hexdigest(),
        nonce=nonce,
        code_verifier=verifier,
        redirect_uri=redirect_uri,
        link_user=link_user,
        expires_at=timezone.now() + timezone.timedelta(minutes=settings.OAUTH_TRANSACTION_TTL_MINUTES),
    )
    params = {
        "client_id": config["client_id"],
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": config["scopes"],
        "state": state,
    }
    if config.get("supports_pkce"):
        params["code_challenge"] = _code_challenge(verifier)
        params["code_challenge_method"] = "S256"
    if nonce:
        params["nonce"] = nonce
    return oauth_transaction, f"{config['authorization_endpoint']}?{urlencode(params)}"


def consume_oauth_transaction(transaction_id, provider, state):
    try:
        oauth_transaction = OAuthTransaction.objects.select_related("link_user").get(
            id=transaction_id,
            provider=provider,
        )
    except (OAuthTransaction.DoesNotExist, ValueError) as exc:
        raise OAuthError("invalid_or_expired") from exc
    expected = hashlib.sha256((state or "").encode()).hexdigest()
    if (
        oauth_transaction.used_at
        or oauth_transaction.is_expired
        or not secrets.compare_digest(oauth_transaction.state_digest, expected)
    ):
        raise OAuthError("invalid_or_expired")
    oauth_transaction.used_at = timezone.now()
    oauth_transaction.save(update_fields=["used_at"])
    return oauth_transaction


def _exchange_code(oauth_transaction, code):
    config = _provider_settings(oauth_transaction.provider)
    try:
        token_data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": oauth_transaction.redirect_uri,
            "client_id": config["client_id"],
            "client_secret": config["client_secret"],
        }
        if config.get("supports_pkce"):
            token_data["code_verifier"] = oauth_transaction.code_verifier
        response = requests.post(
            config["token_endpoint"],
            data=token_data,
            timeout=15,
        )
        if not response.ok:
            try:
                provider_error = response.json()
            except ValueError:
                provider_error = {}
            logger.warning(
                "OAuth token exchange rejected for %s: status=%s error=%s description=%s",
                oauth_transaction.provider,
                response.status_code,
                provider_error.get("error", "unknown"),
                provider_error.get("error_description", "")[:300],
            )
            error_code = provider_error.get("error", "")
            error_description = provider_error.get("error_description", "").lower()
            if oauth_transaction.provider == "linkedin":
                if error_code in {"unauthorized_scope_error", "invalid_scope"} or "scope" in error_description:
                    raise OAuthError("provider_permissions_missing")
                if error_code == "invalid_redirect_uri" or "redirect uri" in error_description:
                    raise OAuthError("provider_redirect_mismatch")
                if error_code in {"invalid_client", "client_authentication_failed"}:
                    raise OAuthError("provider_configuration_invalid")
            raise OAuthError("provider_token_exchange_failed")
        payload = response.json()
    except OAuthError:
        raise
    except (requests.RequestException, ValueError) as exc:
        logger.warning("OAuth token exchange failed for %s: %s", oauth_transaction.provider, exc)
        raise OAuthError("provider_unavailable") from exc
    if not payload.get("access_token"):
        raise OAuthError("provider_unavailable")
    return config, payload


def _validated_oidc_claims(config, token_payload, oauth_transaction):
    id_token = token_payload.get("id_token")
    if not id_token:
        raise OAuthError("provider_account_not_verified")
    try:
        signing_key = jwt.PyJWKClient(config["jwks_uri"]).get_signing_key_from_jwt(id_token)
        claims = jwt.decode(
            id_token,
            signing_key.key,
            algorithms=["RS256", "ES256"],
            audience=config["client_id"],
            issuer=config["issuer"],
            options={"require": ["exp", "iat", "sub"]},
        )
    except jwt.PyJWTError as exc:
        logger.warning("OIDC token validation failed: %s", exc)
        raise OAuthError("provider_account_not_verified") from exc
    if oauth_transaction.nonce and not secrets.compare_digest(claims.get("nonce", ""), oauth_transaction.nonce):
        raise OAuthError("invalid_or_expired")
    return claims


def fetch_social_profile(oauth_transaction, code):
    config, token_payload = _exchange_code(oauth_transaction, code)
    provider = oauth_transaction.provider
    access_token = token_payload["access_token"]
    try:
        if provider == "facebook":
            response = requests.get(
                config["userinfo_endpoint"],
                params={"fields": "id,email,first_name,last_name,name,picture"},
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=10,
            )
            response.raise_for_status()
            claims = response.json()
            picture = claims.get("picture", {}).get("data", {}).get("url", "")
            return SocialProfile(
                provider_user_id=str(claims.get("id", "")),
                email=claims.get("email", ""),
                email_verified=bool(claims.get("email")),
                first_name=claims.get("first_name", ""),
                last_name=claims.get("last_name", ""),
                display_name=claims.get("name", ""),
                avatar_url=picture,
            )

        if provider == "linkedin":
            claims = {}
            if token_payload.get("id_token"):
                try:
                    claims = _validated_oidc_claims(config, token_payload, oauth_transaction)
                except OAuthError as exc:
                    logger.warning("LinkedIn ID token validation failed; falling back to userinfo: %s", exc.code)
            response = requests.get(
                config["userinfo_endpoint"],
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=10,
            )
            response.raise_for_status()
            claims.update(response.json())
        else:
            claims = _validated_oidc_claims(config, token_payload, oauth_transaction)
            response = requests.get(
                config["userinfo_endpoint"],
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=10,
            )
            response.raise_for_status()
            claims.update(response.json())
    except (requests.RequestException, ValueError) as exc:
        logger.warning("OAuth profile fetch failed for %s: %s", provider, exc)
        raise OAuthError("provider_unavailable") from exc

    locale = claims.get("locale", "")
    if isinstance(locale, dict):
        locale = locale.get("language", "")
    return SocialProfile(
        provider_user_id=str(claims.get("sub", "")),
        email=claims.get("email", ""),
        email_verified=claims.get("email_verified") is True,
        first_name=claims.get("given_name", ""),
        last_name=claims.get("family_name", ""),
        display_name=claims.get("name", ""),
        avatar_url=claims.get("picture", ""),
        locale=locale or "",
        timezone=claims.get("zoneinfo", ""),
    )


def _unique_username(profile):
    base = (profile.email.split("@")[0] if profile.email else profile.display_name or "user").strip()
    base = "".join(character for character in base if character.isalnum() or character in "._-")[:120] or "user"
    candidate = base
    counter = 1
    while User.objects.filter(username=candidate).exists():
        counter += 1
        candidate = f"{base[:140]}-{counter}"
    return candidate


def _update_local_profile(user, social_profile):
    changed = []
    if not user.first_name and social_profile.first_name:
        user.first_name = social_profile.first_name
        changed.append("first_name")
    if not user.last_name and social_profile.last_name:
        user.last_name = social_profile.last_name
        changed.append("last_name")
    if not user.email and social_profile.email:
        user.email = social_profile.email
        changed.append("email")
    if changed:
        user.save(update_fields=changed)

    profile, _ = UserProfile.objects.get_or_create(user=user)
    profile_changed = []
    if social_profile.email_verified and not profile.email_confirmed:
        profile.email_confirmed = True
        profile.email_confirmation_token = None
        profile.email_confirmation_token_expires_at = None
        profile_changed.extend(["email_confirmed", "email_confirmation_token", "email_confirmation_token_expires_at"])
    if not profile.avatar_url and social_profile.avatar_url:
        profile.avatar_url = social_profile.avatar_url
        profile_changed.append("avatar_url")
    if not profile.timezone and social_profile.timezone:
        profile.timezone = social_profile.timezone
        profile_changed.append("timezone")
    if profile.preferred_language == "en" and social_profile.locale.startswith("nl"):
        profile.preferred_language = "nl"
        profile_changed.append("preferred_language")
    completed = bool(user.email and user.first_name and user.last_name)
    if profile.profile_completed != completed:
        profile.profile_completed = completed
        profile_changed.append("profile_completed")
    if profile_changed:
        profile.save(update_fields=list(dict.fromkeys(profile_changed)))
    return profile


@transaction.atomic
def connect_social_account(provider, social_profile, link_user=None):
    if not social_profile.provider_user_id:
        raise OAuthError("provider_account_not_verified")
    if not social_profile.email or not social_profile.email_verified:
        raise OAuthError("provider_account_not_verified")

    existing = UserAuthProvider.objects.select_related("user").filter(
        provider=provider,
        provider_user_id=social_profile.provider_user_id,
    ).first()
    if existing:
        if link_user and existing.user_id != link_user.id:
            raise OAuthError("provider_already_linked")
        user = existing.user
        created = False
    else:
        user = link_user
        if not user:
            user = User.objects.filter(email__iexact=social_profile.email).first()
            if user:
                existing_profile = getattr(user, "profile", None)
                if existing_profile and not existing_profile.email_confirmed:
                    raise OAuthError("email_already_exists")
        created = user is None
        if created:
            user = User.objects.create(
                username=_unique_username(social_profile),
                email=social_profile.email,
                first_name=social_profile.first_name,
                last_name=social_profile.last_name,
                is_active=True,
            )
            user.set_unusable_password()
            user.save(update_fields=["password"])
        try:
            existing = UserAuthProvider.objects.create(
                user=user,
                provider=provider,
                provider_user_id=social_profile.provider_user_id,
            )
        except IntegrityError as exc:
            raise OAuthError("provider_already_linked") from exc

    existing.email = social_profile.email
    existing.email_verified = social_profile.email_verified
    existing.display_name = social_profile.display_name
    existing.avatar_url = social_profile.avatar_url
    existing.locale = social_profile.locale
    existing.timezone = social_profile.timezone
    existing.save()
    profile = _update_local_profile(user, social_profile)
    return user, created, profile.profile_completed
