import os
from pathlib import Path

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

    "apps.accounts",
    "apps.doc_x",
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
        },
    }

# -------------------------------
# Default Primary Key Field Type
# -------------------------------
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"