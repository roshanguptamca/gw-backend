"""
Custom Django model fields for encryption at rest.

EncryptedTextField — a TextField subclass that transparently encrypts
values on write (get_prep_value) and decrypts on read (from_db_value).

Usage in models:
    from apps.future_wise.fields import EncryptedTextField

    class MyModel(models.Model):
        secret = EncryptedTextField()

The plaintext length limit (e.g. max_length=250 for subject) should be
enforced at the serializer layer, NOT on the model field, because the
stored ciphertext is always longer than the plaintext.
"""

import base64
import logging

from django.core.exceptions import ImproperlyConfigured
from django.db import models

from services.encryption import MessageEncryptionError, decrypt_message, encrypt_message

logger = logging.getLogger(__name__)

# Minimum AES-256-GCM payload: 12-byte nonce + 16-byte auth tag
_MIN_CIPHERTEXT_BYTES = 28
_ENC_PREFIX = "enc:"


def _is_already_encrypted(value: str) -> bool:
    """
    Return True only if *value* is a structurally valid AES-256-GCM ciphertext
    produced by encrypt_message().

    Checks:
      1. Starts with "enc:"
      2. Remainder is valid base64-url
      3. Decoded payload is at least 28 bytes (12-byte nonce + 16-byte GCM tag)

    This is intentionally stricter than a plain prefix check so that legitimate
    plaintext that happens to start with "enc:" (e.g. "enc: remember to call mum")
    is NOT mistaken for ciphertext and is always encrypted normally.
    """
    if not isinstance(value, str) or not value.startswith(_ENC_PREFIX):
        return False
    b64_part = value[len(_ENC_PREFIX) :]
    try:
        decoded = base64.urlsafe_b64decode(b64_part + "==")
        return len(decoded) >= _MIN_CIPHERTEXT_BYTES
    except Exception:
        return False


class EncryptedTextField(models.TextField):
    """
    A TextField that stores values as AES-256-GCM ciphertext.

    - Writing (get_prep_value): plaintext → ciphertext stored in DB.
    - Reading (from_db_value):  ciphertext → plaintext returned to Python.

    All existing code that accesses the field sees plaintext transparently.
    Legacy plaintext values (before encryption was introduced) are returned
    unchanged by decrypt_message (backward compat via "enc:" prefix check).

    If MESSAGE_ENCRYPTION_KEY is not configured, values are stored as
    plaintext with a warning (graceful degradation for dev environments).
    """

    def from_db_value(self, value, expression, connection):
        if value is None:
            return value
        try:
            return decrypt_message(value)
        except ImproperlyConfigured:
            # Key not configured — value is likely plaintext already
            logger.warning(
                "EncryptedTextField.from_db_value: MESSAGE_ENCRYPTION_KEY not configured, " "returning raw value as-is."
            )
            return value
        except MessageEncryptionError as exc:
            raise ImproperlyConfigured(
                f"Failed to decrypt field value from database. "
                f"Check MESSAGE_ENCRYPTION_KEY is correct. Detail: {exc}"
            ) from exc

    def get_prep_value(self, value):
        if value is None:
            return value
        # Guard against double-encryption: if the value is already valid
        # ciphertext (structurally confirmed, not just prefix-checked), store
        # it unchanged. This handles edge cases where raw ciphertext is
        # re-assigned to a field before saving.
        if _is_already_encrypted(value):
            return value
        try:
            return encrypt_message(value)
        except ImproperlyConfigured:
            logger.warning(
                "EncryptedTextField.get_prep_value: MESSAGE_ENCRYPTION_KEY not configured, "
                "storing value as plaintext."
            )
            return value

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        # Use this module's dotted path so migrations reference the correct class
        path = "apps.future_wise.fields.EncryptedTextField"
        return name, path, args, kwargs
