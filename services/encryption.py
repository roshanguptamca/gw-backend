"""
Encryption-at-rest service for sensitive message content.

Algorithm: AES-256-GCM (authenticated encryption — provides both
confidentiality and integrity).

Stored format: "enc:" + base64url(nonce[12] + ciphertext_with_tag)
where ciphertext_with_tag = AESGCM.encrypt output (ciphertext || 16-byte tag).

Key management:
  - Set MESSAGE_ENCRYPTION_KEY in environment (base64url-encoded 32 bytes).
  - Generate a key: python -c "import secrets,base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"
  - Never commit the key to source control.

Usage:
    from services.encryption import encrypt_message, decrypt_message, MessageEncryptionError

    ciphertext = encrypt_message("Hello future me")
    plaintext  = decrypt_message(ciphertext)
"""

import base64
import logging
import os

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

logger = logging.getLogger(__name__)

_ENC_PREFIX = "enc:"


class MessageEncryptionError(Exception):
    """Raised when encryption or decryption fails."""


def _get_key() -> bytes:
    """
    Load and validate the AES-256 encryption key from settings.

    Raises ImproperlyConfigured if the key is missing or not a valid
    base64-encoded 32-byte value.
    """
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # noqa: F401
    except ImportError as exc:
        raise ImproperlyConfigured(
            "The 'cryptography' package is required for message encryption. " "Run: pip install cryptography"
        ) from exc

    raw_key = getattr(settings, "MESSAGE_ENCRYPTION_KEY", "") or ""
    if not raw_key:
        raise ImproperlyConfigured(
            "MESSAGE_ENCRYPTION_KEY is not set. "
            'Generate one with: python -c "import secrets,base64; '
            'print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"'
        )

    try:
        key_bytes = base64.urlsafe_b64decode(raw_key + "==")
    except Exception as exc:
        raise ImproperlyConfigured("MESSAGE_ENCRYPTION_KEY is not valid base64.") from exc

    if len(key_bytes) != 32:
        raise ImproperlyConfigured(
            f"MESSAGE_ENCRYPTION_KEY must decode to exactly 32 bytes (AES-256); " f"got {len(key_bytes)} bytes."
        )

    return key_bytes


def encrypt_message(plaintext: str) -> str:
    """
    Encrypt a plaintext string using AES-256-GCM.

    Returns an opaque string in the format:
        "enc:" + base64url(nonce[12] + ciphertext_with_tag)

    Raises:
        MessageEncryptionError: if encryption fails for any reason.
        ImproperlyConfigured: if MESSAGE_ENCRYPTION_KEY is missing/invalid.
    """
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    key = _get_key()
    try:
        nonce = os.urandom(12)
        aesgcm = AESGCM(key)
        ciphertext_with_tag = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
        payload = base64.urlsafe_b64encode(nonce + ciphertext_with_tag).decode("ascii")
        return _ENC_PREFIX + payload
    except ImproperlyConfigured:
        raise
    except Exception as exc:
        logger.error("encrypt_message: encryption failed: %s", exc)
        raise MessageEncryptionError(f"Encryption failed: {exc}") from exc


def decrypt_message(value: str) -> str:
    """
    Decrypt a value produced by encrypt_message().

    If the value does not start with the "enc:" prefix (e.g., legacy
    plaintext stored before encryption was introduced), it is returned
    unchanged to allow graceful backward compatibility.

    Raises:
        MessageEncryptionError: if decryption or tag verification fails,
            indicating corrupt or tampered ciphertext.
        ImproperlyConfigured: if MESSAGE_ENCRYPTION_KEY is missing/invalid.
    """
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    if not isinstance(value, str) or not value.startswith(_ENC_PREFIX):
        # Legacy plaintext — return as-is (no-op for pre-encryption records)
        return value

    key = _get_key()
    try:
        b64_payload = value[len(_ENC_PREFIX) :]
        raw = base64.urlsafe_b64decode(b64_payload + "==")

        if len(raw) < 12 + 16:  # nonce + minimum tag, no plaintext is OK but <28 is corrupt
            raise MessageEncryptionError("Encrypted payload is too short to be valid.")

        nonce = raw[:12]
        ciphertext_with_tag = raw[12:]
        aesgcm = AESGCM(key)
        plaintext_bytes = aesgcm.decrypt(nonce, ciphertext_with_tag, None)
        return plaintext_bytes.decode("utf-8")
    except MessageEncryptionError:
        raise
    except ImproperlyConfigured:
        raise
    except InvalidTag as exc:
        logger.error("decrypt_message: authentication tag verification failed (corrupt or tampered data)")
        raise MessageEncryptionError(
            "Decryption failed: authentication tag mismatch — data may be corrupt or tampered."
        ) from exc
    except Exception as exc:
        logger.error("decrypt_message: decryption failed: %s", exc)
        raise MessageEncryptionError(f"Decryption failed: {exc}") from exc
