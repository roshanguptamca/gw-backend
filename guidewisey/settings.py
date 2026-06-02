import os
from pathlib import Path

# Load .env file for local development (no-op in production if .env absent)
try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)
except ImportError:
    pass

# -------------------------------
# Base Directory
# -------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent

# -------------------------------
# Environment Detection
# -------------------------------
ENV = os.getenv("ENV", "DEV").upper()
IS_PRODUCTION = ENV == "PROD"
IS_DEVELOPMENT = ENV == "DEV"

# -------------------------------
# Security
# -------------------------------
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")
DEBUG = IS_DEVELOPMENT  # Only True in development

ALLOWED_HOSTS = [
    "gw-backend-eq2n.onrender.com",
    "gw-frontend-nine.vercel.app",
    "www.guidewisey.com",
    "guidewisey.com",
    "127.0.0.1",
    "localhost",
]

# -------------------------------
# Installed Apps
# -------------------------------
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "drf_spectacular",
    "drf_spectacular_sidecar",
    "apps.accounts",
    "apps.doc_x",
    "apps.future_wise",
    "apps.insurance_explainer",
    "apps.contact",
    "django_apscheduler",
]

# -------------------------------
# Middleware
# -------------------------------
MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# -------------------------------
# URL Configuration
# -------------------------------
ROOT_URLCONF = "guidewisey.urls"

# -------------------------------
# Templates
# -------------------------------
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    }
]

# -------------------------------
# WSGI
# -------------------------------
WSGI_APPLICATION = "guidewisey.wsgi.application"

# -------------------------------
# Database
# -------------------------------
if IS_DEVELOPMENT:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
            # Raise busy-timeout to 20 s so concurrent threads wait instead of
            # immediately raising "database is locked".
            "OPTIONS": {"timeout": 20},
            # Do NOT pool connections in dev — each thread gets its own
            # connection, which avoids cross-thread lock contention.
            "CONN_MAX_AGE": 0,
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("DB_NAME"),
            "USER": os.getenv("DB_USER"),
            "PASSWORD": os.getenv("DB_PASSWORD"),
            "HOST": os.getenv("DB_HOST"),
            "PORT": os.getenv("DB_PORT", "5432"),
        }
    }

# -------------------------------
# CORS Configuration
# -------------------------------
CORS_ALLOWED_ORIGINS = [
    "https://www.guidewisey.com",
    "https://guidewisey.com",
    "https://gw-frontend-nine.vercel.app",
    "https://gw-frontend-git-main-roshans-projects-8dfa7f93.vercel.app",
    "https://gw-frontend-7kjrbapg8-roshans-projects-8dfa7f93.vercel.app",
]

# Add localhost origins only in development
if IS_DEVELOPMENT:
    CORS_ALLOWED_ORIGINS += [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ]

CORS_ALLOW_CREDENTIALS = True

from corsheaders.defaults import default_headers, default_methods

CORS_ALLOW_METHODS = list(default_methods)
CORS_ALLOW_HEADERS = list(default_headers) + [
    "X-Secret",
    "X-CSRFToken",
]

# -------------------------------
# CSRF Configuration
# -------------------------------
CSRF_TRUSTED_ORIGINS = [
    "https://www.guidewisey.com",
    "https://guidewisey.com",
    "https://gw-frontend-nine.vercel.app",
    "https://gw-frontend-git-main-roshans-projects-8dfa7f93.vercel.app",
    "https://gw-frontend-7kjrbapg8-roshans-projects-8dfa7f93.vercel.app",
]

# Add localhost only in development
if IS_DEVELOPMENT:
    CSRF_TRUSTED_ORIGINS += [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ]

# -------------------------------
# Cookie Settings (Environment-Specific)
# -------------------------------
if IS_DEVELOPMENT:
    # Development: HTTP (no Secure flag needed)
    CSRF_COOKIE_SECURE = False
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SAMESITE = "Lax"
else:
    # Production: HTTPS (Secure flag required)
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SAMESITE = "None"  # Required for cross-origin
    SESSION_COOKIE_SAMESITE = "None"

# Common cookie settings (both environments)
CSRF_COOKIE_DOMAIN = None
SESSION_COOKIE_DOMAIN = None
CSRF_COOKIE_HTTPONLY = False  # JavaScript needs to read CSRF token
SESSION_COOKIE_HTTPONLY = True  # Security: prevent JS access to session
CSRF_COOKIE_PATH = "/"
SESSION_COOKIE_PATH = "/"
CSRF_USE_SESSIONS = False
SESSION_COOKIE_AGE = 1209600  # 2 weeks

# -------------------------------
# Security Settings (Production Only)
# -------------------------------
if IS_PRODUCTION:
    SECURE_SSL_REDIRECT = False  # Render handles SSL
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_BROWSER_XSS_FILTER = True
    X_FRAME_OPTIONS = "DENY"
    CORS_ALLOWED_ORIGIN_REGEXES = [
        r"^https://gw-frontend-.*\.vercel\.app$",
    ]

# -------------------------------
# Password Validators
# -------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# -------------------------------
# Internationalization
# -------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_L10N = True
USE_TZ = True

# -------------------------------
# Static & Media Files
# -------------------------------
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# -------------------------------
# Django REST Framework
# -------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.AllowAny" if IS_DEVELOPMENT else "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

# -------------------------------
# Logging (Production)
# -------------------------------
if IS_PRODUCTION:
    LOGGING = {
        "version": 1,
        "disable_existing_loggers": False,
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
            },
        },
        "root": {
            "handlers": ["console"],
            "level": "INFO",
        },
        "loggers": {
            "django": {
                "handlers": ["console"],
                "level": "INFO",
                "propagate": False,
            },
            "apps.future_wise": {
                "handlers": ["console"],
                "level": "INFO",
                "propagate": False,
            },
        },
    }
else:
    # Dev — ensure FutureWise scheduler/email logs are always visible
    LOGGING = {
        "version": 1,
        "disable_existing_loggers": False,
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "simple",
            },
        },
        "formatters": {
            "simple": {
                "format": "[{levelname}] {name}: {message}",
                "style": "{",
            },
        },
        "loggers": {
            "apps.future_wise": {
                "handlers": ["console"],
                "level": "DEBUG",
                "propagate": False,
            },
            "apscheduler": {
                "handlers": ["console"],
                "level": "INFO",
                "propagate": False,
            },
        },
    }

# -------------------------------
# Default Primary Key Field Type
# -------------------------------
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ============================================================
# File Storage Backend
# ============================================================
# Controls where uploaded files are stored.
#   "db"   (default) — store file bytes in the database; no external deps required
#   "auto"           — use S3 if AWS credentials are present, otherwise fall back to DB
#   "s3"             — always use AWS S3 (requires AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, S3_BUCKET)
# S3 is fully optional. The app runs without any AWS credentials when this is "db".
FILE_STORAGE_BACKEND = os.getenv("FILE_STORAGE_BACKEND", "db")

# ============================================================
# FutureWise / DearTomorrow — Email Reminder Feature
# ============================================================

# ── Django SMTP Email Backend ────────────────────────────────
EMAIL_BACKEND = "guidewisey.email_backend.CertifiSMTPEmailBackend"
EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp-relay.brevo.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", 587))
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "true").lower() == "true"
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "ac98f2001@smtp-brevo.com")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_TIMEOUT = int(os.getenv("EMAIL_TIMEOUT", 30))  # seconds; prevents SMTP hangs
DEFAULT_FROM_EMAIL = os.getenv(
    "DEFAULT_FROM_EMAIL",
    f'{os.getenv("EMAIL_SENDER_NAME", "FutureWise by GuideWisey")} <{os.getenv("EMAIL_SENDER_EMAIL", "noreply@guidewisey.com")}>',
)
EMAIL_SENDER_NAME = os.getenv("EMAIL_SENDER_NAME", "FutureWise by GuideWisey")
EMAIL_SENDER_EMAIL = os.getenv("EMAIL_SENDER_EMAIL", "noreply@guidewisey.com")
CONTACT_ADMIN_EMAIL = os.getenv("CONTACT_ADMIN_EMAIL", "info@guidewisey.com")

# Fall back to console backend in DEV if no SMTP password is set
if ENV == "DEV" and not EMAIL_HOST_PASSWORD:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
# Legacy Brevo REST API key (kept for reference; no longer used for delivery)
BREVO_API_KEY = os.getenv("BREVO_API_KEY", "")

# ── FutureWise Delivery Tuning ───────────────────────────────
FUTUREWAVE_MAX_RETRIES = int(os.getenv("FUTUREWAVE_MAX_RETRIES", 3))
FUTUREWAVE_RETRY_BASE_DELAY_SECONDS = int(os.getenv("FUTUREWAVE_RETRY_BASE_DELAY_SECONDS", 300))
FUTUREWAVE_MAX_SCHEDULE_YEARS = int(os.getenv("FUTUREWAVE_MAX_SCHEDULE_YEARS", 10))
FUTUREWAVE_MIN_SCHEDULE_MINUTES = int(os.getenv("FUTUREWAVE_MIN_SCHEDULE_MINUTES", 30))
FUTUREWAVE_MAX_ATTACHMENT_BYTES = int(os.getenv("FUTUREWAVE_MAX_ATTACHMENT_BYTES", 10 * 1024 * 1024))
FUTUREWAVE_MAX_ATTACHMENTS = int(os.getenv("FUTUREWAVE_MAX_ATTACHMENTS", 5))
FUTUREWAVE_ATTACHMENT_PURGE_AFTER_SEND = os.getenv("FUTUREWAVE_ATTACHMENT_PURGE_AFTER_SEND", "true").lower() == "true"
FUTUREWAVE_FRONTEND_BASE_URL = os.getenv("FUTUREWAVE_FRONTEND_BASE_URL", "https://www.guidewisey.com")

# ── Business rules ───────────────────────────────────────────
# Max email reminders per day for free (non-superuser) users, counted per email address
EMAIL_REMINDER_FREE_DAILY_LIMIT = int(os.getenv("EMAIL_REMINDER_FREE_DAILY_LIMIT", 3))
# How long an email-verification link stays valid (also used by cleanup job)
EMAIL_VERIFICATION_EXPIRY_HOURS = int(os.getenv("EMAIL_VERIFICATION_EXPIRY_HOURS", 24))

# ── Rate Limits (DRF scope rates) ───────────────────────────
FUTUREWAVE_ANON_CREATE_RATE = os.getenv("FUTUREWAVE_ANON_CREATE_RATE", "5/hour")
FUTUREWAVE_USER_CREATE_RATE = os.getenv("FUTUREWAVE_USER_CREATE_RATE", "20/hour")
FUTUREWAVE_VERIFY_RATE = os.getenv("FUTUREWAVE_VERIFY_RATE", "10/hour")

# ── APScheduler (DB-backed, no Redis required) ───────────────
APSCHEDULER_DATETIME_FORMAT = "N j, Y, f:s a"
APSCHEDULER_RUN_NOW_TIMEOUT = 25  # seconds

# ── Multi-Channel Reminder Providers ────────────────────────
# Twilio (SMS + Voice + WhatsApp Sandbox)
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER", "")        # E.164 e.g. +15005550006
TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER", "")  # Sandbox: +14155238886

# Telegram Bot API
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# ── DRF Throttle Cache ───────────────────────────────────────
if IS_PRODUCTION and os.getenv("REDIS_URL"):
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": os.getenv("REDIS_URL"),
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        }
    }

REST_FRAMEWORK["DEFAULT_THROTTLE_CLASSES"] = [
    "rest_framework.throttling.AnonRateThrottle",
    "rest_framework.throttling.UserRateThrottle",
]
REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] = {
    "anon": "100/day",
    "user": "1000/day",
    "futurewave_anon_create": FUTUREWAVE_ANON_CREATE_RATE,
    "futurewave_user_create": FUTUREWAVE_USER_CREATE_RATE,
    "futurewave_verify": FUTUREWAVE_VERIFY_RATE,
}

# ── Sentry Observability ─────────────────────────────────────
SENTRY_DSN = os.getenv("SENTRY_DSN", "")
if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.django import DjangoIntegration

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration(), CeleryIntegration()],
        traces_sample_rate=0.1,
        send_default_pii=False,
        environment=ENV.lower(),
    )

# -------------------------------
# OpenAPI / Swagger (drf-spectacular)
# -------------------------------
SPECTACULAR_SETTINGS = {
    "TITLE": "GuideWisey API",
    "DESCRIPTION": (
        "Production API for GuideWisey — a platform that simplifies government, "
        "school, and official documents using AI.\n\n"
        "## Authentication\n"
        "All protected endpoints require a valid session cookie. "
        "Before calling any mutating endpoint, fetch the CSRF token from "
        "`GET /api/accounts/csrf/` and include it in the `X-CSRFToken` header.\n\n"
        "## Apps\n"
        "- **Accounts** — registration, login, session management\n"
        "- **Doc-X** — AI-powered document parsing and Q&A\n"
        "- **FutureWise / DearTomorrow** — schedule a future-self email reminder\n"
    ),
    "VERSION": "2.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    # Give explicit names to status enums that would otherwise collide
    "ENUM_NAME_OVERRIDES": {
        "DocumentProcessingStatusEnum": ["pending", "processing", "completed", "failed"],
        "JobStatusEnum": ["pending", "running", "completed", "failed"],
        "InsuranceSessionStatusEnum": ["ins_pending", "ins_processing", "ins_completed", "ins_failed"],
    },
    # Security schemes
    "SECURITY": [{"cookieAuth": []}],
    "COMPONENTS": {
        "securitySchemes": {
            "cookieAuth": {
                "type": "apiKey",
                "in": "cookie",
                "name": "sessionid",
                "description": "Django session cookie set after a successful login.",
            },
            "csrfToken": {
                "type": "apiKey",
                "in": "header",
                "name": "X-CSRFToken",
                "description": "CSRF token obtained from GET /api/accounts/csrf/",
            },
        }
    },
    # Self-hosted Swagger UI assets (no CDN in production)
    "SWAGGER_UI_DIST": "SIDECAR",
    "SWAGGER_UI_FAVICON_HREF": "SIDECAR",
    "REDOC_DIST": "SIDECAR",
    # Swagger UI configuration
    "SWAGGER_UI_SETTINGS": {
        "deepLinking": True,
        "persistAuthorization": True,
        "displayOperationId": False,
        "filter": True,
        "docExpansion": "list",
        "defaultModelsExpandDepth": 2,
        "defaultModelExpandDepth": 2,
        "displayRequestDuration": True,
        "tryItOutEnabled": True,
    },
    # Schema generation options
    "SORT_OPERATIONS": False,
    "ENUM_GENERATE_CHOICE_DESCRIPTION": True,
    "POSTPROCESSING_HOOKS": [
        "drf_spectacular.hooks.postprocess_schema_enums",
    ],
    "SCHEMA_PATH_PREFIX": r"/api/",
    "SCHEMA_PATH_PREFIX_TRIM": True,
    "CONTACT": {
        "name": "GuideWisey Support",
        "email": "support@guidewisey.com",
        "url": "https://www.guidewisey.com",
    },
    "LICENSE": {"name": "Proprietary"},
    "SERVERS": [
        {"url": "https://gw-backend-eq2n.onrender.com", "description": "Production"},
        {"url": "http://localhost:8000", "description": "Local Development"},
    ],
    "TAGS": [
        {"name": "Accounts", "description": "User registration, authentication, and session management"},
        {"name": "Doc-X V2", "description": "Document upload, AI processing, and chat (recommended API)"},
        {
            "name": "Doc-X V1 (Legacy)",
            "description": "Legacy document processing endpoints — kept for backward compatibility",
        },
        {"name": "FutureWise", "description": "Schedule future self-email reminders with optional attachments"},
        {
            "name": "Insurance Explainer",
            "description": "AI-powered insurance policy analysis: coverage, gaps, risks, and action items with country/language context",
        },
    ],
}
