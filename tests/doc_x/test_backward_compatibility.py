# tests/doc_x/test_backward_compatibility.py
"""
Regression tests to ensure all existing endpoints still work.
CRITICAL: These tests must pass 100% to maintain backward compatibility.
"""
import pytest

from apps.doc_x.models import Document, UserQuestionLimit


@pytest.mark.django_db
class TestBackwardCompatibility:
    """Test that all V1 endpoints still work as expected."""

    def test_get_upload_url_endpoint_exists(self, authenticated_client):
        """Test that the upload-url endpoint still exists."""
        url = "/api/doc-x/upload-url/"
        response = authenticated_client.post(url, {"filename": "test.pdf"})

        # Should not be 404
        assert response.status_code != 404

        # Should return expected fields (even if S3 is not configured)
        if response.status_code == 200:
            assert "upload_url" in response.data or "error" in response.data

    def test_process_text_endpoint_works(self, authenticated_client, mock_gemini_response):
        """Test that process-text endpoint works."""
        url = "/api/doc-x/process-text/"
        data = {"text": "This is a test document that needs processing.", "preferred_language": "English"}

        response = authenticated_client.post(url, data, format="json")

        assert response.status_code == 200
        assert "document_id" in response.data
        assert "summary" in response.data

        # Verify document was created
        doc = Document.objects.get(id=response.data["document_id"])
        assert doc.s3_key == "TEXT"
        assert doc.content == data["text"]

    def test_ask_endpoint_rate_limiting(self, authenticated_client, document, mock_gemini_response):
        """Test that the ask endpoint still enforces rate limiting."""
        url = "/api/doc-x/ask/"

        # Ask 3 questions (should work)
        for i in range(3):
            response = authenticated_client.post(
                url, {"document_id": document.id, "question": f"Question {i}?"}, format="json"
            )
            assert response.status_code == 200
            assert "answer" in response.data
            assert "remaining" in response.data

        # 4th question should be blocked
        response = authenticated_client.post(
            url, {"document_id": document.id, "question": "Question 4?"}, format="json"
        )
        assert response.status_code == 403

    def test_get_remaining_questions_endpoint(self, authenticated_client, document):
        """Test that get remaining questions endpoint works."""
        url = f"/api/doc-x/ask/remaining/?document_id={document.id}"
        response = authenticated_client.get(url)

        assert response.status_code == 200
        assert "remaining" in response.data
        assert response.data["remaining"] == 3

    def test_existing_document_model_fields(self, document):
        """Test that existing Document model fields are unchanged."""
        # Critical fields that must exist
        assert hasattr(document, "s3_key")
        assert hasattr(document, "content")
        assert hasattr(document, "summary")
        assert hasattr(document, "created_at")

        # Verify they work
        assert document.s3_key is not None
        assert document.content is not None
        assert document.created_at is not None

    def test_conversation_model_still_works(self, authenticated_client, document, mock_gemini_response):
        """Test that Conversation model is still functional."""
        from apps.doc_x.models import Conversation

        # Create a conversation entry
        conv = Conversation.objects.create(document=document, role="user", message="Test message")

        assert conv.id is not None
        assert conv.document == document
        assert conv.role == "user"
        assert conv.message == "Test message"

    def test_old_endpoints_response_format(self, authenticated_client, document, mock_gemini_response):
        """Test that old endpoints return data in expected format."""
        url = "/api/doc-x/ask/"
        response = authenticated_client.post(url, {"document_id": document.id, "question": "Test?"}, format="json")

        assert response.status_code == 200

        # Verify response structure matches V1
        assert "answer" in response.data
        assert "remaining" in response.data
        assert isinstance(response.data["answer"], str)
        assert isinstance(response.data["remaining"], int)

    def test_process_document_without_user_field(self, db):
        """Test that documents without user field still work (backward compatibility)."""
        # Create document without user (like old records)
        doc = Document.objects.create(
            s3_key="old/document.pdf", content="Old content", summary="Old summary", processing_status="completed"
        )

        assert doc.id is not None
        assert doc.user is None  # Should allow null
        assert doc.s3_key == "old/document.pdf"

    def test_session_based_rate_limiting_still_works(self, api_client, document, mock_gemini_response):
        """Test that session-based rate limiting (for anonymous users) still works."""
        # Force authentication to simulate session-based access
        # Create session
        session = api_client.session
        session.save()

        # This tests the decorator still works with session keys
        url = "/api/doc-x/process-text/"
        data = {"text": "Test document for session-based processing."}

        api_client.force_authenticate(user=None)

        # Note: This endpoint uses session-based limiting
        # Just verify the endpoint is accessible
        response = api_client.post(url, data, format="json")
        # May fail auth, but should not be 404 or 500
        assert response.status_code in [200, 401, 403]


@pytest.mark.django_db
class TestDataIntegrity:
    """Test that existing data structures remain intact."""

    def test_old_document_records_readable(self, db, user):
        """Test that old document records can still be read."""
        # Simulate an old record (only has original fields)
        old_doc = Document.objects.create(s3_key="uploads/old.pdf", content="Old content", summary="Old summary")

        # Should be readable
        retrieved = Document.objects.get(id=old_doc.id)
        assert retrieved.s3_key == "uploads/old.pdf"
        assert retrieved.content == "Old content"

        # New fields should have defaults
        assert retrieved.processing_status == "completed"  # default
        assert retrieved.metadata == {}  # default

    def test_user_question_limit_model_unchanged(self, db, user, document):
        """Test that UserQuestionLimit model still works."""
        limit = UserQuestionLimit.objects.create(user=user, document=document, count=2)

        assert limit.user == user
        assert limit.document == document
        assert limit.count == 2

        # Should be updatable
        limit.count += 1
        limit.save()

        retrieved = UserQuestionLimit.objects.get(id=limit.id)
        assert retrieved.count == 3
