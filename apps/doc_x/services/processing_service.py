"""
apps/doc_x/services/processing_service.py

Document processing pipeline — text extraction, AI summarisation, chunking.
File retrieval goes through services.file_storage so it works with both
S3 and DB storage backends.
"""

import os
import tempfile
import logging

from apps.doc_x.models import Document, DocumentChunk, ProcessingJob
from apps.doc_x.extract import extract_text
from services.file_storage import get_file_storage
from services.gemini import GeminiClient

logger = logging.getLogger(__name__)


class ProcessingService:
    """Service for document processing operations."""

    def __init__(self):
        self.ai_client = GeminiClient()

    def process_document(self, document: Document) -> dict:
        """
        Complete document processing pipeline:
          1. Retrieve raw bytes from storage (S3 or DB)
          2. Write to temp file
          3. Extract text
          4. Generate AI summary
          5. Chunk document
          6. Update document status
        """
        file_path = None
        try:
            document.processing_status = "processing"
            document.save()

            # Step 1-2: Retrieve file bytes → temp file
            file_path = self._retrieve_to_tempfile(document)

            # Step 3: Extract text
            text = self._extract_text(file_path, document.file_type)
            document.content = text
            document.save()

            # Step 4: Generate AI summary
            summary = self._generate_summary(text, document.filename or "document")
            document.summary = summary

            # Step 5: Chunk document
            chunk_count = self._chunk_document(document, text)

            # Step 6: Mark completed
            document.processing_status = "completed"
            document.save()

            logger.info(f"Successfully processed document {document.id}")
            return {
                "status": "completed",
                "text_length": len(text),
                "summary_length": len(summary),
                "chunk_count": chunk_count,
            }

        except Exception as e:
            logger.error(f"Failed to process document {document.id}: {e}", exc_info=True)
            document.processing_status = "failed"
            document.metadata["error"] = str(e)
            document.save()
            return {"status": "failed", "error": str(e)}

        finally:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)

    def _retrieve_to_tempfile(self, document: Document) -> str:
        """
        Retrieve file bytes from the active storage backend and write to a
        named temp file.  Returns the temp file path.
        """
        # Find the primary DocumentFile record
        doc_file = document.files.order_by("uploaded_at").first()
        if doc_file is None:
            raise ValueError(
                f"Document {document.id} has no associated DocumentFile record. "
                "Upload may have failed or been created by V1 flow."
            )

        storage = get_file_storage()
        data = storage.retrieve(doc_file)

        ext = os.path.splitext(document.s3_key)[1] or f".{document.file_type or 'bin'}"
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            tmp.write(data)
            return tmp.name

    def _extract_text(self, file_path: str, file_type: str) -> str:
        try:
            text = extract_text(file_path, file_type)
            if not text or len(text.strip()) < 10:
                raise ValueError("Extracted text is too short or empty")
            return text
        except Exception as e:
            logger.error(f"Text extraction failed for {file_path}: {e}")
            raise

    def _generate_summary(self, text: str, filename: str = "document") -> str:
        try:
            # Gemini 2.5 Flash supports ~1M tokens (~750K chars). Cap at 500K for safety.
            MAX_CHARS = 500_000
            note = ""
            if len(text) > MAX_CHARS:
                text = text[:MAX_CHARS]
                note = "\n\n[Note: document was very large — analysis covers the first portion only.]"

            summary = self.ai_client.explain_text(
                text=text + note,
                system_prompt=(
                    "You are an assistant that explains documents clearly and concisely. "
                    "Summarise the key points and what the reader needs to know or do."
                ),
                preferred_language="English",
            )
            return summary
        except Exception as e:
            logger.error(f"Summary generation failed: {e}")
            return "Summary generation failed. Please try again later."

    def _chunk_document(self, document: Document, text: str, chunk_size: int = 2000) -> int:
        if len(text) < chunk_size * 2:
            return 0

        chunks = []
        start = 0
        chunk_index = 0

        while start < len(text):
            end = start + chunk_size
            if end < len(text):
                search_start = max(start, end - 200)
                search_text = text[search_start : end + 200]
                for delimiter in [". ", ".\n", "! ", "? "]:
                    idx = search_text.rfind(delimiter)
                    if idx != -1:
                        end = search_start + idx + len(delimiter)
                        break

            chunk_text = text[start:end].strip()
            if chunk_text:
                chunks.append(
                    DocumentChunk(
                        document=document,
                        chunk_index=chunk_index,
                        content=chunk_text,
                        token_count=len(chunk_text) // 4,
                    )
                )
                chunk_index += 1
            start = end

        if chunks:
            DocumentChunk.objects.bulk_create(chunks)
            logger.info(f"Created {len(chunks)} chunks for document {document.id}")

        return len(chunks)

    def create_processing_job(self, document: Document, job_type: str) -> ProcessingJob:
        return ProcessingJob.objects.create(document=document, job_type=job_type, status="pending")

    def get_processing_status(self, document: Document) -> dict:
        return {
            "document_id": document.id,
            "status": document.processing_status,
            "has_content": bool(document.content),
            "has_summary": bool(document.summary),
            "chunk_count": document.chunks.count(),
            "metadata": document.metadata,
        }
