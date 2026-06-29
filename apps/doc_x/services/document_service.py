"""
apps/doc_x/services/document_service.py

Document CRUD + upload service.
All file I/O goes through services.file_storage.get_file_storage()
so storage is switchable between S3 and DB via FILE_STORAGE_BACKEND setting.
"""

import logging
import os
from typing import List, Optional

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import UploadedFile

from apps.doc_x.models import Document, DocumentFile
from services.file_storage import build_storage_key, get_file_storage

logger = logging.getLogger(__name__)
User = get_user_model()


class DocumentService:
    """Service for document management operations."""

    def create_document(
        self,
        user: Optional[User] = None,
        filename: str = None,
        file_type: str = None,
        file_size: int = None,
        s3_key: str = None,
        content: str = "",
        summary: str = "",
        metadata: dict = None,
    ) -> Document:
        doc = Document.objects.create(
            user=user,
            filename=filename,
            file_type=file_type,
            file_size=file_size,
            s3_key=s3_key or "",
            content=content,
            summary=summary,
            processing_status="pending",
            metadata=metadata or {},
        )
        logger.info(f"Created document {doc.id} for user {user}")
        return doc

    def upload_file(
        self,
        uploaded_file: UploadedFile,
        user: Optional[User] = None,
        use_s3: bool = None,  # deprecated — kept for backward compat; ignored
    ) -> tuple[Document, DocumentFile]:
        """
        Upload a file and create Document + DocumentFile records.
        Storage backend (S3 or DB) is determined by get_file_storage().
        """
        filename = uploaded_file.name
        file_size = uploaded_file.size
        file_type = self._get_file_type(filename)

        # Pick storage backend
        storage = get_file_storage()
        key = build_storage_key(user, filename)

        # Store the file
        result = storage.store(uploaded_file, key)

        # Create document record
        doc = self.create_document(
            user=user,
            filename=filename,
            file_type=file_type,
            file_size=file_size,
            s3_key=result["s3_key"],
        )

        # Create file record
        doc_file = DocumentFile(
            document=doc,
            filename=filename,
            file_type=file_type,
            file_size=file_size,
            s3_key=result["s3_key"],
            storage_backend=result["storage_backend"],
            uploaded_by=user,
        )
        if result.get("_data") is not None:
            doc_file.file_data = result["_data"]
        doc_file.save()

        logger.info(f"Uploaded '{filename}' ({file_size} bytes) via {storage.name} backend " f"for document {doc.id}")
        return doc, doc_file

    def get_document(self, document_id: int, user: Optional[User] = None) -> Optional[Document]:
        try:
            query = Document.objects.filter(id=document_id)
            if user:
                query = query.filter(user=user)
            return query.first()
        except Document.DoesNotExist:
            return None

    def list_documents(self, user: Optional[User] = None, limit: int = 100) -> List[Document]:
        query = Document.objects.all()
        if user:
            query = query.filter(user=user)
        return list(query.order_by("-created_at")[:limit])

    def delete_document(self, document_id: int, user: Optional[User] = None) -> bool:
        doc = self.get_document(document_id, user)
        if not doc:
            return False

        storage = get_file_storage()
        for doc_file in doc.files.all():
            try:
                storage.delete(doc_file)
            except Exception as e:
                logger.warning(f"Could not delete stored file for {doc_file.id}: {e}")

        doc.delete()
        logger.info(f"Deleted document {document_id}")
        return True

    def _get_file_type(self, filename: str) -> str:
        _, ext = os.path.splitext(filename)
        return ext.lower().replace(".", "")
