"""
Root conftest.py — ensures a test encryption key is set before and after Django initialises.

MESSAGE_ENCRYPTION_KEY must be available when EncryptedTextField.get_prep_value/
from_db_value are called. pytest-django may call django.setup() before conftest
module-level code runs, so we patch both os.environ (pre-setup) and the already-
loaded django.conf.settings (post-setup) in the pytest_configure hook.

The test key is NOT a secret — it is only used in automated test databases.
"""

import os

# Pre-setup: set before Django.setup() if possible
_TEST_ENCRYPTION_KEY = "dGVzdGtleWZvcnVuaXR0ZXN0czEyMzQ1Njc4OTAxMjM="
os.environ.setdefault("MESSAGE_ENCRYPTION_KEY", _TEST_ENCRYPTION_KEY)


def pytest_configure(config):
    """Belt-and-suspenders: also patch django.conf.settings if already loaded."""
    os.environ.setdefault("MESSAGE_ENCRYPTION_KEY", _TEST_ENCRYPTION_KEY)
    try:
        from django.conf import settings as django_settings

        if not getattr(django_settings, "MESSAGE_ENCRYPTION_KEY", ""):
            django_settings.MESSAGE_ENCRYPTION_KEY = _TEST_ENCRYPTION_KEY
    except Exception:
        pass
