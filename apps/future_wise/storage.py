"""
Attachment storage for FutureWise reminders.

Uses the same FILE_STORAGE_BACKEND setting as doc_x:
  "db"   — bytes stored in ReminderAttachment.file_data  (no S3 needed)
  "s3"   — bytes stored in S3 under a UUID key
  "auto" — use S3 if credentials present, else DB

This lets the app run with zero external dependencies locally.
"""

import logging
import uuid
from typing import Optional

from django.conf import settings

logger = logging.getLogger(__name__)

_S3_PREFIX = "future_wise/attachments/"


def _backend() -> str:
    """Return "db" or "s3" depending on settings."""
    backend = getattr(settings, "FILE_STORAGE_BACKEND", "auto").lower()
    if backend == "s3":
        return "s3"
    if backend == "db":
        return "db"
    # auto: use S3 if all four credentials are present
    if all([
        getattr(settings, "AWS_ACCESS_KEY_ID", ""),
        getattr(settings, "AWS_SECRET_ACCESS_KEY", ""),
        getattr(settings, "S3_BUCKET", ""),
    ]):
        return "s3"
    return "db"


class AttachmentStorage:
    """
    Upload / download / delete reminder attachments.

    For DB backend, the bytes are stored on the `ReminderAttachment` model's
    `file_data` field.  For S3, we store in S3 and keep the key in
    `ReminderAttachment.storage_key`.
    """

    def __init__(self):
        self.mode = _backend()
        if self.mode == "s3":
            import boto3
            self._s3 = boto3.client(
                "s3",
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                region_name=getattr(settings, "AWS_REGION", "eu-west-1"),
            )
            self._bucket = settings.S3_BUCKET

    # ── Upload ────────────────────────────────────────────────────────────────

    def upload(
        self,
        content_bytes: bytes,
        original_filename: str,
        content_type: str,
        attachment_instance=None,
    ) -> str:
        """
        Store bytes.  Returns a storage_key string.
        For DB backend: saves bytes directly on attachment_instance.file_data
        and returns a synthetic key.  attachment_instance must be provided.
        For S3: uploads to S3 and returns the S3 key.
        """
        key = f"{_S3_PREFIX}{uuid.uuid4().hex}{_extension(original_filename)}"

        if self.mode == "db":
            if attachment_instance is None:
                raise StorageError("DB storage requires attachment_instance to save file_data")
            attachment_instance.file_data = content_bytes
            # key is a logical identifier; actual bytes are on the model
            logger.debug("Stored attachment in DB for %s", original_filename)
            return key

        # S3 path
        try:
            self._s3.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=content_bytes,
                ContentType=content_type,
                ServerSideEncryption="AES256",
            )
            logger.debug("Uploaded attachment %s → s3://%s/%s", original_filename, self._bucket, key)
            return key
        except Exception as exc:
            raise StorageError(f"S3 upload failed: {exc}") from exc

    # ── Download ──────────────────────────────────────────────────────────────

    def download_bytes(self, storage_key: str, attachment_instance=None) -> bytes:
        """
        Retrieve bytes. For DB backend, reads from attachment_instance.file_data.
        For S3, downloads from the bucket.
        """
        if self.mode == "db":
            if attachment_instance is None or not attachment_instance.file_data:
                raise StorageError("No file_data on attachment — cannot download from DB")
            return bytes(attachment_instance.file_data)

        try:
            obj = self._s3.get_object(Bucket=self._bucket, Key=storage_key)
            return obj["Body"].read()
        except Exception as exc:
            raise StorageError(f"S3 download failed for key {storage_key}: {exc}") from exc

    # ── Delete ────────────────────────────────────────────────────────────────

    def delete(self, storage_key: str, attachment_instance=None) -> None:
        if self.mode == "db":
            if attachment_instance:
                attachment_instance.file_data = None
                attachment_instance.save(update_fields=["file_data"])
            return
        try:
            self._s3.delete_object(Bucket=self._bucket, Key=storage_key)
        except Exception as exc:
            logger.warning("S3 delete failed for key %s: %s", storage_key, exc)

    def delete_many(self, storage_keys: list[str]) -> None:
        if self.mode == "db":
            return  # DB cleanup handled by cascade delete on the model
        if not storage_keys:
            return
        try:
            self._s3.delete_objects(
                Bucket=self._bucket,
                Delete={"Objects": [{"Key": k} for k in storage_keys[:1000]], "Quiet": True},
            )
        except Exception as exc:
            logger.warning("S3 batch delete failed: %s", exc)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extension(filename: str) -> str:
    parts = filename.rsplit(".", 1)
    if len(parts) == 2:
        ext = "." + parts[1].lower()
        allowed = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".pdf", ".txt", ".doc", ".docx"}
        return ext if ext in allowed else ""
    return ""


class StorageError(Exception):
    """Raised when an attachment storage operation fails."""
