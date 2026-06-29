import logging

from django.apps import AppConfig
from django.conf import settings


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"

    def ready(self):
        logger = logging.getLogger(__name__)
        logger.info("ALLOWED_HOSTS=%s", settings.ALLOWED_HOSTS)
        logger.info("CSRF_TRUSTED_ORIGINS=%s", settings.CSRF_TRUSTED_ORIGINS)
        import apps.accounts.signals  # noqa: F401
