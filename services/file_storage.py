"""
services/file_storage.py

Pluggable file storage abstraction for Doc-X.

Backends
--------
  DatabaseStorageBackend  — stores raw bytes in the DocumentFile.file_data column.
                            Zero external dependencies; works with SQLite or Postgres.
  S3StorageBackend        — stores files in AWS S3.

Selection (via settings.FILE_STORAGE_BACKEND)
  "auto"  — use S3 when AWS credentials are present, otherwise fall back to DB
  "db"    — always use DatabaseStorageBackend
  "s3"    — always use S3StorageBackend (raises at runtime if creds missing)

Usage
-----
    from services.file_storage import get_file_storage
    storage = get_file_storage()
    storage.store(uploaded_file_or_bytes, key)   # save
    data = storage.retrieve(doc_file)            # load bytes
    storage.delete(doc_file)                     # remove
"""

import os
import tempfile
import uuid
import logging

from django.conf import settings

logger = logging.getLogger(__name__)


# ── Base ──────────────────────────────────────────────────────────────────────

class FileStorageBackend:
    name: str = "base"

    def store(self, file_obj, key: str) -> dict:
        """
        Persist file_obj (Django UploadedFile or bytes) under key.

        Returns a dict with at least:
          { "storage_backend": str, "s3_key": str }
        where s3_key is a unique identifier that can be used to retrieve/delete.
        """
        raise NotImplementedError

    def retrieve(self, doc_file) -> bytes:
        """Return raw bytes for the given DocumentFile instance."""
        raise NotImplementedError

    def delete(self, doc_file) -> None:
        """Remove stored file. Silently ignores missing files."""
        raise NotImplementedError


# ── Database backend ──────────────────────────────────────────────────────────

class DatabaseStorageBackend(FileStorageBackend):
    """
    Stores file bytes directly in the DocumentFile.file_data column.
    No external services required — works entirely with the Django DB.
    """

    name = "db"

    def store(self, file_obj, key: str) -> dict:
        if isinstance(file_obj, (bytes, bytearray, memoryview)):
            data = bytes(file_obj)
        else:
            # Django UploadedFile
            file_obj.seek(0)
            data = file_obj.read()

        logger.info(f"DB storage: storing {len(data)} bytes under key '{key}'")
        # Return the raw bytes so the caller can set doc_file.file_data
        return {
            "storage_backend": "db",
            "s3_key": key,   # reuse the s3_key column as a logical identifier
            "_data": data,   # caller MUST save this onto doc_file.file_data
        }

    def retrieve(self, doc_file) -> bytes:
        if doc_file.file_data is None:
            raise ValueError(
                f"DocumentFile {doc_file.id} has storage_backend='db' but file_data is NULL. "
                "The file may not have been saved correctly."
            )
        return bytes(doc_file.file_data)

    def delete(self, doc_file) -> None:
        # Data lives in the DB row; deleting the DocumentFile row handles it.
        logger.info(f"DB storage: delete is a no-op — row deletion removes data for {doc_file.id}")


# ── S3 backend ────────────────────────────────────────────────────────────────

class S3StorageBackend(FileStorageBackend):
    """
    Stores files in AWS S3.
    Requires AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION, S3_BUCKET env vars.
    """

    name = "s3"

    def __init__(self):
        from services.s3 import S3Client
        self._s3 = S3Client()

    def store(self, file_obj, key: str) -> dict:
        if isinstance(file_obj, (bytes, bytearray, memoryview)):
            data = bytes(file_obj)
            suffix = os.path.splitext(key)[1] or ".bin"
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(data)
                tmp_path = tmp.name
        else:
            # Django UploadedFile — write to temp file
            suffix = os.path.splitext(file_obj.name)[1] or ".bin"
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                for chunk in file_obj.chunks():
                    tmp.write(chunk)
                tmp_path = tmp.name

        try:
            self._s3.upload_file(tmp_path, key)
            logger.info(f"S3 storage: uploaded to '{key}'")
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

        return {
            "storage_backend": "s3",
            "s3_key": key,
            "_data": None,
        }

    def retrieve(self, doc_file) -> bytes:
        suffix = os.path.splitext(doc_file.s3_key)[1] or ".bin"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp_path = tmp.name
        try:
            self._s3.download_file(doc_file.s3_key, tmp_path)
            with open(tmp_path, "rb") as f:
                return f.read()
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def delete(self, doc_file) -> None:
        try:
            self._s3.delete_file(doc_file.s3_key)
            logger.info(f"S3 storage: deleted '{doc_file.s3_key}'")
        except Exception as e:
            logger.warning(f"S3 storage: failed to delete '{doc_file.s3_key}': {e}")


# ── Factory ───────────────────────────────────────────────────────────────────

def _s3_credentials_present() -> bool:
    return all([
        os.getenv("AWS_ACCESS_KEY_ID"),
        os.getenv("AWS_SECRET_ACCESS_KEY"),
        os.getenv("AWS_REGION") or os.getenv("AWS_S3_REGION_NAME"),
        os.getenv("S3_BUCKET") or os.getenv("AWS_STORAGE_BUCKET_NAME"),
    ])


def get_file_storage() -> FileStorageBackend:
    """
    Return the active FileStorageBackend based on settings.FILE_STORAGE_BACKEND.

    "auto" → S3 if credentials present, else DB
    "s3"   → S3 (hard failure at runtime if credentials missing)
    "db"   → DB (always)
    """
    setting = getattr(settings, "FILE_STORAGE_BACKEND", "auto").lower()

    if setting == "db":
        logger.debug("File storage: using DatabaseStorageBackend (forced via settings)")
        return DatabaseStorageBackend()

    if setting == "s3":
        logger.debug("File storage: using S3StorageBackend (forced via settings)")
        return S3StorageBackend()

    # "auto"
    if _s3_credentials_present():
        logger.debug("File storage: using S3StorageBackend (auto — credentials found)")
        return S3StorageBackend()

    logger.debug("File storage: using DatabaseStorageBackend (auto — no S3 credentials)")
    return DatabaseStorageBackend()


def build_storage_key(user, filename: str) -> str:
    """Generate a unique storage key for a file."""
    user_id = user.id if user and hasattr(user, "id") else "anonymous"
    return f"uploads/{user_id}/{uuid.uuid4()}/{filename}"
