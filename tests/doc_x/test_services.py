# tests/doc_x/test_services.py
"""
Unit tests for Doc_X service classes.
"""
import pytest

from apps.doc_x.models import Document
from apps.doc_x.services import ChatService, DocumentService, ProcessingService


@pytest.mark.django_db
class TestDocumentService:
    """Test DocumentService."""

    def test_create_document(self, user):
        """Test document creation."""
        service = DocumentService()

        doc = service.create_document(
            user=user,
            filename="test.pdf",
            file_type="pdf",
            file_size=1024,
            s3_key="test/key.pdf",
            content="Test content",
        )

        assert doc.id is not None
        assert doc.user == user
        assert doc.filename == "test.pdf"
        assert doc.file_type == "pdf"
        assert doc.processing_status == "pending"

    def test_get_document(self, user, document):
        """Test document retrieval."""
        service = DocumentService()

        retrieved = service.get_document(document.id, user=user)

        assert retrieved is not None
        assert retrieved.id == document.id

    def test_get_document_wrong_user(self, user, document, db):
        """Test that users can't access other users' documents."""
        from django.contrib.auth import get_user_model

        other_user = get_user_model().objects.create_user(username="other", password="pass")
        service = DocumentService()

        retrieved = service.get_document(document.id, user=other_user)

        assert retrieved is None

    def test_list_documents(self, user, document):
        """Test document listing."""
        service = DocumentService()

        # Create another document
        Document.objects.create(
            user=user,
            filename="test2.pdf",
            file_type="pdf",
            s3_key="test2.pdf",
            content="Content 2",
            processing_status="completed",
        )

        docs = service.list_documents(user=user)

        assert len(docs) == 2

    def test_list_documents_limit(self, user, document):
        """Test document listing with limit."""
        service = DocumentService()

        # Create multiple documents
        for i in range(5):
            Document.objects.create(
                user=user, filename=f"test{i}.pdf", file_type="pdf", s3_key=f"test{i}.pdf", content=f"Content {i}"
            )

        docs = service.list_documents(user=user, limit=3)

        assert len(docs) == 3


@pytest.mark.django_db
class TestProcessingService:
    """Test ProcessingService."""

    def test_get_processing_status(self, document):
        """Test getting processing status."""
        service = ProcessingService()

        status = service.get_processing_status(document)

        assert status["document_id"] == document.id
        assert status["status"] == document.processing_status
        assert status["has_content"] is True
        assert status["has_summary"] is True

    def test_create_processing_job(self, document):
        """Test creating a processing job."""
        service = ProcessingService()

        job = service.create_processing_job(document, job_type="extraction")

        assert job.id is not None
        assert job.document == document
        assert job.job_type == "extraction"
        assert job.status == "pending"


@pytest.mark.django_db
class TestChatService:
    """Test ChatService."""

    def test_get_or_create_session(self, user, document):
        """Test session creation."""
        service = ChatService()

        session = service.get_or_create_session(document, user=user)

        assert session.id is not None
        assert session.document == document
        assert session.user == user
        assert session.is_active is True

    def test_get_existing_session(self, user, document, chat_session):
        """Test retrieving existing session."""
        service = ChatService()

        session = service.get_or_create_session(document, user=user)

        # Should return the same session
        assert session.id == chat_session.id

    def test_send_message(self, user, document, chat_session, mock_gemini_response):
        """Test sending a chat message."""
        service = ChatService()

        user_msg, assistant_msg = service.send_message(chat_session, "What is this about?", user=user)

        assert user_msg.role == "user"
        assert user_msg.content == "What is this about?"
        assert assistant_msg.role == "assistant"
        assert len(assistant_msg.content) > 0

    def test_get_messages(self, user, document, chat_session, mock_gemini_response):
        """Test retrieving chat messages."""
        service = ChatService()

        # Send some messages
        service.send_message(chat_session, "Question 1", user=user)
        service.send_message(chat_session, "Question 2", user=user)

        messages = service.get_messages(chat_session)

        assert len(messages) == 4  # 2 user + 2 assistant

    def test_check_question_limit(self, user, document):
        """Test question limit checking."""
        service = ChatService()

        can_ask, remaining = service.check_question_limit(document, user=user, max_questions=3)

        assert can_ask is True
        assert remaining == 3

    def test_increment_question_count(self, user, document):
        """Test incrementing question count."""
        service = ChatService()

        # Increment 3 times
        for _ in range(3):
            service.increment_question_count(document, user=user)

        can_ask, remaining = service.check_question_limit(document, user=user, max_questions=3)

        assert can_ask is False
        assert remaining == 0

    def test_question_limit_per_document(self, user):
        """Test that question limits are per-document."""
        from apps.doc_x.models import Document

        doc1 = Document.objects.create(
            user=user, filename="doc1.pdf", file_type="pdf", s3_key="doc1.pdf", content="Content 1"
        )
        doc2 = Document.objects.create(
            user=user, filename="doc2.pdf", file_type="pdf", s3_key="doc2.pdf", content="Content 2"
        )

        service = ChatService()

        # Use up limit on doc1
        for _ in range(3):
            service.increment_question_count(doc1, user=user)

        # Should still be able to ask about doc2
        can_ask, remaining = service.check_question_limit(doc2, user=user)

        assert can_ask is True
        assert remaining == 3
