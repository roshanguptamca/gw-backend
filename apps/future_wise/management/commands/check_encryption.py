"""
Management command: python manage.py check_encryption

Queries raw DB column values (bypassing ORM field processing) to report
whether EmailReminder subject and message fields are stored as ciphertext.

Output buckets per field:
  • encrypted   — starts with "enc:", valid base64, payload ≥ 28 bytes
  • legacy/plain — does not match the ciphertext format (pre-encryption rows)
  • corrupt      — starts with "enc:" but base64 is invalid or payload too short

Usage:
    python manage.py check_encryption
    python manage.py check_encryption --limit 50
    python manage.py check_encryption --decrypt   # attempt live decryption to verify round-trip
"""

import base64

from django.core.management.base import BaseCommand
from django.db import connection

_ENC_PREFIX = "enc:"
_MIN_BYTES = 28  # 12-byte nonce + 16-byte GCM auth tag


def _classify(value: str) -> str:
    if not isinstance(value, str):
        return "null/non-string"
    if not value.startswith(_ENC_PREFIX):
        return "legacy/plain"
    b64_part = value[len(_ENC_PREFIX) :]
    try:
        decoded = base64.urlsafe_b64decode(b64_part + "==")
        if len(decoded) >= _MIN_BYTES:
            return "encrypted"
        return "corrupt (payload too short)"
    except Exception:
        return "corrupt (invalid base64)"


class Command(BaseCommand):
    help = "Check raw DB column values to confirm subject/message are encrypted at rest"

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=20,
            help="Number of rows to sample (default: 20, 0 = all rows)",
        )
        parser.add_argument(
            "--decrypt",
            action="store_true",
            help="Attempt to decrypt each encrypted value and report success/failure",
        )

    def handle(self, *args, **options):
        limit = options["limit"]
        do_decrypt = options["decrypt"]

        sql = "SELECT id, subject, message FROM future_wise_emailreminder"
        if limit:
            sql += f" LIMIT {limit}"

        with connection.cursor() as cursor:
            cursor.execute(sql)
            rows = cursor.fetchall()

        if not rows:
            self.stdout.write(self.style.WARNING("No reminders found in the database."))
            return

        counts = {"subject": {}, "message": {}}
        issues = []

        for row_id, subject, message in rows:
            for field_name, raw_value in (("subject", subject), ("message", message)):
                bucket = _classify(raw_value)
                counts[field_name][bucket] = counts[field_name].get(bucket, 0) + 1

                if bucket == "encrypted" and do_decrypt:
                    try:
                        from services.encryption import decrypt_message

                        decrypted = decrypt_message(raw_value)
                        if not isinstance(decrypted, str):
                            issues.append(f"  id={row_id} {field_name}: decrypted but result is not str")
                    except Exception as exc:
                        issues.append(f"  id={row_id} {field_name}: decryption FAILED — {exc}")

                if bucket.startswith("corrupt") or bucket == "legacy/plain":
                    preview = (raw_value or "")[:60]
                    issues.append(f"  id={row_id} {field_name} [{bucket}]: {preview!r}")

        self.stdout.write(f"\nSampled {len(rows)} row(s):\n")

        for field_name in ("subject", "message"):
            self.stdout.write(f"  {field_name}:")
            for bucket, count in sorted(counts[field_name].items()):
                style = self.style.SUCCESS if bucket == "encrypted" else self.style.WARNING
                self.stdout.write(style(f"    {bucket}: {count}"))

        if issues:
            self.stdout.write(self.style.WARNING("\nIssues found:"))
            for line in issues:
                self.stdout.write(self.style.WARNING(line))
        else:
            self.stdout.write(self.style.SUCCESS("\nAll sampled values are properly encrypted. ✅"))
