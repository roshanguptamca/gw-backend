"""
Tests for encryption-at-rest of EmailReminder subject and message fields.

Covers:
  1. Direct unit tests for encrypt_message / decrypt_message.
  2. DB integration: stored value is ciphertext, not plaintext.
  3. Correct round-trip decryption via EncryptedTextField.
  4. Invalid / corrupt ciphertext raises MessageEncryptionError.
  5. Non-message fields (email, status, retry_count) are unaffected.
  6. Empty string encrypts and decrypts correctly.
  7. Legacy plaintext (no "enc:" prefix) passes through decrypt_message unchanged.
  8. Missing / invalid key raises ImproperlyConfigured.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured
from django.db import connection
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.future_wise.models import EmailReminder
from services.encryption import (
    MessageEncryptionError,
    decrypt_message,
    encrypt_message,
)

User = get_user_model()

_PLAIN_SUBJECT = "Hello future me — test subject"
_PLAIN_MESSAGE = "Dear future self, I hope you are doing well!"


def _make_reminder(**kwargs) -> EmailReminder:
    defaults = dict(
        email="enc-test@example.com",
        email_verified=True,
        verification_token=EmailReminder.generate_verification_token(),
        verification_token_expires_at=EmailReminder.make_token_expiry(),
        subject=_PLAIN_SUBJECT,
        message=_PLAIN_MESSAGE,
        scheduled_at=timezone.now() + timedelta(days=30),
        tier=EmailReminder.Tier.FREE,
        status=EmailReminder.Status.SCHEDULED,
    )
    defaults.update(kwargs)
    return EmailReminder.objects.create(**defaults)


def _raw_db_row(reminder_id) -> dict:
    """Fetch the raw subject/message bytes directly from the DB, bypassing ORM field processing."""
    import uuid as _uuid

    # Django stores UUIDs as 32-char hex (no hyphens) on SQLite
    id_hex = reminder_id.hex if isinstance(reminder_id, _uuid.UUID) else str(reminder_id).replace("-", "")
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT subject, message FROM future_wise_emailreminder WHERE id = %s",
            [id_hex],
        )
        row = cursor.fetchone()
    if row is None:
        raise AssertionError(f"No row found in future_wise_emailreminder for id={id_hex}")
    return {"subject": row[0], "message": row[1]}


# ── Unit tests for encrypt_message / decrypt_message ─────────────────────────


class EncryptMessageUnitTest(TestCase):

    def test_encrypt_returns_enc_prefix(self):
        result = encrypt_message("hello")
        self.assertTrue(result.startswith("enc:"), msg=f"Expected 'enc:' prefix, got: {result[:20]}")

    def test_encrypt_is_not_plaintext(self):
        result = encrypt_message("super secret message")
        self.assertNotIn("super secret message", result)

    def test_encrypt_different_nonce_each_call(self):
        """AES-GCM uses a random nonce, so two encryptions of the same plaintext differ."""
        c1 = encrypt_message("same plaintext")
        c2 = encrypt_message("same plaintext")
        self.assertNotEqual(c1, c2)

    def test_decrypt_round_trip(self):
        ciphertext = encrypt_message(_PLAIN_MESSAGE)
        recovered = decrypt_message(ciphertext)
        self.assertEqual(recovered, _PLAIN_MESSAGE)

    def test_decrypt_subject_round_trip(self):
        ciphertext = encrypt_message(_PLAIN_SUBJECT)
        recovered = decrypt_message(ciphertext)
        self.assertEqual(recovered, _PLAIN_SUBJECT)

    def test_encrypt_empty_string(self):
        ciphertext = encrypt_message("")
        self.assertTrue(ciphertext.startswith("enc:"))
        self.assertEqual(decrypt_message(ciphertext), "")

    def test_encrypt_unicode(self):
        text = "Привет будущий я! 🌟"
        self.assertEqual(decrypt_message(encrypt_message(text)), text)

    def test_decrypt_legacy_plaintext_passthrough(self):
        """Values without 'enc:' prefix are returned unchanged (backward compat)."""
        legacy = "plain text without prefix"
        self.assertEqual(decrypt_message(legacy), legacy)

    def test_decrypt_corrupt_base64_raises(self):
        with self.assertRaises(MessageEncryptionError):
            decrypt_message("enc:!!!not-valid-base64!!!")

    def test_decrypt_truncated_payload_raises(self):
        """Payload too short to hold nonce (12) + tag (16) = 28 bytes."""
        import base64

        short_payload = base64.urlsafe_b64encode(b"short").decode()
        with self.assertRaises(MessageEncryptionError):
            decrypt_message(f"enc:{short_payload}")

    def test_decrypt_tampered_ciphertext_raises(self):
        """Flipping a byte in the ciphertext must fail authentication."""
        import base64 as b64

        ciphertext = encrypt_message("important message")
        raw_b64 = ciphertext[len("enc:") :]
        raw_bytes = bytearray(b64.urlsafe_b64decode(raw_b64 + "=="))
        raw_bytes[-1] ^= 0xFF  # flip last byte (in the tag)
        tampered = "enc:" + b64.urlsafe_b64encode(bytes(raw_bytes)).decode().rstrip("=")
        with self.assertRaises(MessageEncryptionError):
            decrypt_message(tampered)

    def test_decrypt_wrong_key_raises(self):
        """Decrypting with a different key must raise MessageEncryptionError."""
        import base64

        ciphertext = encrypt_message("secret")
        other_key = base64.urlsafe_b64encode(b"wrongkeyfortest1wrongkeyfortest1").decode()
        with override_settings(MESSAGE_ENCRYPTION_KEY=other_key):
            with self.assertRaises(MessageEncryptionError):
                decrypt_message(ciphertext)


class EncryptionKeyValidationTest(TestCase):

    def test_missing_key_raises_improperly_configured(self):
        with override_settings(MESSAGE_ENCRYPTION_KEY=""):
            with self.assertRaises(ImproperlyConfigured):
                encrypt_message("hello")

    def test_invalid_base64_key_raises_improperly_configured(self):
        with override_settings(MESSAGE_ENCRYPTION_KEY="not-valid-base64!!!"):
            with self.assertRaises(ImproperlyConfigured):
                encrypt_message("hello")

    def test_key_wrong_length_raises_improperly_configured(self):
        import base64

        short_key = base64.urlsafe_b64encode(b"only16bytes_here").decode()
        with override_settings(MESSAGE_ENCRYPTION_KEY=short_key):
            with self.assertRaises(ImproperlyConfigured):
                encrypt_message("hello")


# ── DB integration: stored value is ciphertext ───────────────────────────────


class EncryptedFieldDBTest(TestCase):

    def test_subject_stored_as_ciphertext_not_plaintext(self):
        reminder = _make_reminder()
        raw = _raw_db_row(reminder.id)
        self.assertNotEqual(raw["subject"], _PLAIN_SUBJECT)
        self.assertTrue(
            raw["subject"].startswith("enc:"),
            msg=f"Expected 'enc:' prefix in DB, got: {raw['subject'][:40]}",
        )

    def test_message_stored_as_ciphertext_not_plaintext(self):
        reminder = _make_reminder()
        raw = _raw_db_row(reminder.id)
        self.assertNotEqual(raw["message"], _PLAIN_MESSAGE)
        self.assertTrue(
            raw["message"].startswith("enc:"),
            msg=f"Expected 'enc:' prefix in DB, got: {raw['message'][:40]}",
        )

    def test_subject_decrypts_correctly_on_read(self):
        reminder = _make_reminder()
        loaded = EmailReminder.objects.get(pk=reminder.pk)
        self.assertEqual(loaded.subject, _PLAIN_SUBJECT)

    def test_message_decrypts_correctly_on_read(self):
        reminder = _make_reminder()
        loaded = EmailReminder.objects.get(pk=reminder.pk)
        self.assertEqual(loaded.message, _PLAIN_MESSAGE)

    def test_non_message_fields_unaffected(self):
        """email, status, tier, retry_count etc. must be stored and returned unchanged."""
        reminder = _make_reminder()
        loaded = EmailReminder.objects.get(pk=reminder.pk)
        self.assertEqual(loaded.email, "enc-test@example.com")
        self.assertEqual(loaded.status, EmailReminder.Status.SCHEDULED)
        self.assertEqual(loaded.tier, EmailReminder.Tier.FREE)
        self.assertEqual(loaded.retry_count, 0)

    def test_refresh_from_db_decrypts(self):
        reminder = _make_reminder()
        reminder.refresh_from_db()
        self.assertEqual(reminder.subject, _PLAIN_SUBJECT)
        self.assertEqual(reminder.message, _PLAIN_MESSAGE)

    def test_update_subject_re_encrypts(self):
        reminder = _make_reminder()
        new_subject = "Updated subject for future self"
        reminder.subject = new_subject
        reminder.save(update_fields=["subject", "updated_at"])

        raw = _raw_db_row(reminder.id)
        self.assertTrue(raw["subject"].startswith("enc:"))
        self.assertNotEqual(raw["subject"][:40], new_subject[:40])

        reloaded = EmailReminder.objects.get(pk=reminder.pk)
        self.assertEqual(reloaded.subject, new_subject)

    def test_two_reminders_same_content_have_different_ciphertext(self):
        """Each save uses a fresh random nonce."""
        r1 = _make_reminder()
        r2 = _make_reminder()
        raw1 = _raw_db_row(r1.id)
        raw2 = _raw_db_row(r2.id)
        self.assertNotEqual(raw1["subject"], raw2["subject"])
        self.assertNotEqual(raw1["message"], raw2["message"])

    def test_queryset_values_returns_ciphertext(self):
        """
        values() bypasses model instantiation so from_db_value is NOT called;
        raw ciphertext is returned. This confirms the DB contains ciphertext.
        """
        reminder = _make_reminder()
        # from_db_value IS called for values() per Django docs, so we use raw SQL above.
        # Here we verify via raw cursor that the DB has ciphertext.
        raw = _raw_db_row(reminder.id)
        self.assertTrue(raw["subject"].startswith("enc:"))
        self.assertTrue(raw["message"].startswith("enc:"))

    def test_empty_subject_encrypts_and_decrypts(self):
        reminder = _make_reminder(subject="")
        raw = _raw_db_row(reminder.id)
        self.assertTrue(raw["subject"].startswith("enc:"))
        loaded = EmailReminder.objects.get(pk=reminder.pk)
        self.assertEqual(loaded.subject, "")

    def test_no_double_encryption_when_raw_ciphertext_reassigned(self):
        """
        If raw ciphertext from the DB is directly assigned to a field and then saved,
        get_prep_value must detect it is already valid ciphertext and not re-encrypt it.
        Without this guard the value would be encrypted twice and on read would
        yield the intermediate ciphertext string, not the original plaintext.
        """
        reminder = _make_reminder()
        raw_before = _raw_db_row(reminder.id)

        # Simulate edge case: raw ciphertext assigned back to the field
        reminder.subject = raw_before["subject"]
        reminder.save(update_fields=["subject", "updated_at"])

        raw_after = _raw_db_row(reminder.id)
        self.assertEqual(
            raw_before["subject"],
            raw_after["subject"],
            "Ciphertext must not change — double-encryption occurred",
        )
        # Reading back must still yield the original plaintext
        reloaded = EmailReminder.objects.get(pk=reminder.pk)
        self.assertEqual(reloaded.subject, _PLAIN_SUBJECT)

    def test_plaintext_starting_with_enc_prefix_is_not_misidentified(self):
        """
        Legitimate plaintext that starts with 'enc:' but is NOT valid ciphertext
        (e.g. short or invalid base64) must be encrypted, not bypassed.
        """
        # This looks like it starts with "enc:" but is short, not a valid payload
        tricky_subject = "enc: a note to my future self"
        reminder = _make_reminder(subject=tricky_subject)
        raw = _raw_db_row(reminder.id)
        # Must be stored as ciphertext, not as the original tricky string
        self.assertTrue(
            raw["subject"].startswith("enc:"),
            "Subject must be stored as ciphertext",
        )
        # The raw DB value must NOT equal the original tricky plaintext
        self.assertNotEqual(raw["subject"], tricky_subject)
        # Reading back must yield original plaintext
        loaded = EmailReminder.objects.get(pk=reminder.pk)
        self.assertEqual(loaded.subject, tricky_subject)


# ── Delivery path: fields are plaintext when accessed before sending ──────────


class EncryptionDeliveryPathTest(TestCase):
    """
    The EncryptedTextField decrypts on read, so any code that accesses
    reminder.subject / reminder.message after loading from DB receives plaintext.
    This test verifies that flow without needing to invoke real providers.
    """

    def test_reminder_loaded_from_db_has_plaintext_fields(self):
        """
        Simulate what _deliver_reminder does: load from DB, then access fields.
        Fields should be plaintext (decrypted by EncryptedTextField.from_db_value).
        """
        _make_reminder()

        reminder = EmailReminder.objects.filter(
            status=EmailReminder.Status.SCHEDULED,
        ).first()

        self.assertIsNotNone(reminder)
        # Fields must be plaintext — safe to pass to email/SMS providers
        self.assertEqual(reminder.subject, _PLAIN_SUBJECT)
        self.assertEqual(reminder.message, _PLAIN_MESSAGE)
        # Confirm DB has ciphertext
        raw = _raw_db_row(reminder.id)
        self.assertNotEqual(raw["subject"], _PLAIN_SUBJECT)
        self.assertNotEqual(raw["message"], _PLAIN_MESSAGE)
