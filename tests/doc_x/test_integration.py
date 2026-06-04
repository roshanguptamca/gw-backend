# tests/doc_x/test_integration.py
"""
Integration tests for Doc_X - test complete workflows.
"""
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from apps.doc_x.models import Document


@pytest.mark.django_db
class TestDocumentUploadWorkflow:
    """Test complete document upload and processing workflow."""

    def test_upload_process_chat_workflow(self, authenticated_client, temp_txt_file, mock_gemini_response):
        """Test full workflow: upload → process → chat."""

        # Step 1: Upload document
        with open(temp_txt_file, "rb") as f:
            upload_response = authenticated_client.post(
                "/api/doc-x/documents/upload",
                {"file": f, "use_s3": "false"},  # Use local storage for testing
                format="multipart",
            )

        assert upload_response.status_code == 201
        assert "document_id" in upload_response.data
        document_id = upload_response.data["document_id"]

        # Step 2: Process document
        process_response = authenticated_client.post(f"/api/doc-x/documents/{document_id}/process")

        assert process_response.status_code == 200
        assert process_response.data["status"] == "completed"

        # Step 3: Chat with document
        chat_response = authenticated_client.post(
            f"/api/doc-x/documents/{document_id}/chat", {"message": "What is this about?"}, format="json"
        )

        assert chat_response.status_code == 200
        assert "assistant_message" in chat_response.data
        assert "remaining_questions" in chat_response.data

        # Step 4: Get message history
        messages_response = authenticated_client.get(f"/api/doc-x/documents/{document_id}/messages")

        assert messages_response.status_code == 200
        assert messages_response.data["count"] == 2  # user + assistant

    def test_list_and_delete_workflow(self, authenticated_client, document):
        """Test listing documents and deleting."""

        # List documents
        list_response = authenticated_client.get("/api/doc-x/documents")

        assert list_response.status_code == 200
        assert list_response.data["count"] >= 1

        # Delete document — correct endpoint is /documents/{id}/delete
        delete_response = authenticated_client.delete(f"/api/doc-x/documents/{document.id}/delete")

        assert delete_response.status_code == 200

        # Verify it's gone
        get_response = authenticated_client.get(f"/api/doc-x/documents/{document.id}")
        assert get_response.status_code == 404


@pytest.mark.django_db
class TestV1WorkflowCompatibility:
    """Test that V1 workflow still works."""

    def test_process_text_workflow(self, authenticated_client, mock_gemini_response):
        """Test V1 process-text workflow."""

        # Process text
        response = authenticated_client.post(
            "/api/doc-x/process-text/",
            {"text": "This is a test document.", "preferred_language": "English"},
            format="json",
        )

        assert response.status_code == 200
        assert "document_id" in response.data
        assert "summary" in response.data

    def test_ask_workflow(self, authenticated_client, document, mock_gemini_response):
        """Test V1 ask workflow."""

        # Ask question
        response = authenticated_client.post(
            "/api/doc-x/ask/", {"document_id": document.id, "question": "What is this?"}, format="json"
        )

        assert response.status_code == 200
        assert "answer" in response.data
        assert "remaining" in response.data


@pytest.mark.django_db
class TestFileTypeSupport:
    """Test all supported file types."""

    def test_csv_upload_and_process(self, authenticated_client, temp_csv_file, mock_gemini_response):
        """Test CSV file upload and processing."""

        with open(temp_csv_file, "rb") as f:
            response = authenticated_client.post(
                "/api/doc-x/documents/upload", {"file": f, "use_s3": "false"}, format="multipart"
            )

        assert response.status_code == 201
        document_id = response.data["document_id"]

        # Process
        process_response = authenticated_client.post(f"/api/doc-x/documents/{document_id}/process")

        assert process_response.status_code == 200
        assert process_response.data["status"] == "completed"

        # Verify content was extracted
        doc = Document.objects.get(id=document_id)
        assert "Name" in doc.content
        assert "Age" in doc.content

    def test_txt_upload_and_process(self, authenticated_client, temp_txt_file, mock_gemini_response):
        """Test TXT file upload and processing."""

        with open(temp_txt_file, "rb") as f:
            response = authenticated_client.post(
                "/api/doc-x/documents/upload", {"file": f, "use_s3": "false"}, format="multipart"
            )

        assert response.status_code == 201
        document_id = response.data["document_id"]

        # Process
        process_response = authenticated_client.post(f"/api/doc-x/documents/{document_id}/process")

        assert process_response.status_code == 200


@pytest.mark.django_db
class TestErrorHandling:
    """Test error handling scenarios."""

    def test_upload_without_file(self, authenticated_client):
        """Test upload without providing file."""
        response = authenticated_client.post("/api/doc-x/documents/upload", {}, format="multipart")

        assert response.status_code == 400
        assert "error" in response.data

    def test_upload_unsupported_file_type(self, authenticated_client):
        """Test upload with unsupported file type."""
        file = SimpleUploadedFile("test.xyz", b"content", content_type="application/octet-stream")

        response = authenticated_client.post("/api/doc-x/documents/upload", {"file": file}, format="multipart")

        assert response.status_code == 400
        assert "Unsupported file type" in response.data["error"]

    def test_upload_file_too_large(self, authenticated_client):
        """Test upload with file exceeding size limit."""
        # Create 11MB file (exceeds 10MB limit)
        large_content = b"x" * (11 * 1024 * 1024)
        file = SimpleUploadedFile("large.txt", large_content, content_type="text/plain")

        response = authenticated_client.post("/api/doc-x/documents/upload", {"file": file}, format="multipart")

        assert response.status_code == 400
        assert "too large" in response.data["error"].lower()

    def test_process_nonexistent_document(self, authenticated_client):
        """Test processing non-existent document."""
        response = authenticated_client.post("/api/doc-x/documents/99999/process")

        assert response.status_code == 404

    def test_chat_with_unprocessed_document(self, authenticated_client, user):
        """Test chatting with unprocessed document."""
        # Create document in pending state
        doc = Document.objects.create(
            user=user, filename="test.pdf", file_type="pdf", s3_key="test.pdf", processing_status="pending"
        )

        response = authenticated_client.post(
            f"/api/doc-x/documents/{doc.id}/chat", {"message": "What is this?"}, format="json"
        )

        assert response.status_code == 400
        assert "not yet processed" in response.data["error"].lower()

    def test_chat_without_message(self, authenticated_client, document):
        """Test chat without providing message."""
        response = authenticated_client.post(f"/api/doc-x/documents/{document.id}/chat", {}, format="json")

        assert response.status_code == 400
        assert "message" in response.data["error"].lower()

    def test_rate_limit_enforcement(self, authenticated_client, document, mock_gemini_response):
        """Test that rate limiting is enforced."""
        # Ask 3 questions (limit)
        for i in range(3):
            response = authenticated_client.post(
                f"/api/doc-x/documents/{document.id}/chat", {"message": f"Question {i}?"}, format="json"
            )
            assert response.status_code == 200

        # 4th should be blocked
        response = authenticated_client.post(
            f"/api/doc-x/documents/{document.id}/chat", {"message": "Question 4?"}, format="json"
        )

        assert response.status_code == 403
        assert "limit" in response.data["error"].lower()


@pytest.mark.django_db
class TestAuthentication:
    """Test authentication requirements."""

    def test_endpoints_require_authentication(self, api_client):
        """Test that endpoints require authentication."""
        endpoints = [
            ("/api/doc-x/documents/upload", "post"),
            ("/api/doc-x/documents", "get"),
            ("/api/doc-x/documents/1", "get"),
            ("/api/doc-x/documents/1/process", "post"),
            ("/api/doc-x/documents/1/chat", "post"),
        ]

        for url, method in endpoints:
            if method == "get":
                response = api_client.get(url)
            else:
                response = api_client.post(url, {})

            # Should require authentication
            assert response.status_code in [401, 403]
