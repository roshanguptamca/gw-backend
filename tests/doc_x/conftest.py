# tests/doc_x/conftest.py
"""
Pytest fixtures for Doc_X tests.
"""
import pytest
from django.contrib.auth import get_user_model
from apps.doc_x.models import Document, ChatSession
from rest_framework.test import APIClient
import tempfile
import os

User = get_user_model()


@pytest.fixture
def user(db):
    """Create a test user."""
    return User.objects.create_user(username="testuser", email="test@example.com", password="testpass123")


@pytest.fixture
def api_client():
    """Create an API client."""
    return APIClient()


@pytest.fixture
def authenticated_client(api_client, user):
    """Create an authenticated API client."""
    api_client.force_authenticate(user=user)
    return api_client


@pytest.fixture
def document(db, user):
    """Create a test document."""
    return Document.objects.create(
        user=user,
        filename="test.pdf",
        file_type="pdf",
        file_size=1024,
        s3_key="test/test.pdf",
        content="This is test content for the document.",
        summary="Test document summary.",
        processing_status="completed",
    )


@pytest.fixture
def chat_session(db, document, user):
    """Create a test chat session."""
    return ChatSession.objects.create(document=document, user=user, title="Test Chat")


@pytest.fixture
def temp_pdf_file():
    """Create a temporary PDF file for testing."""
    content = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n3 0 obj\n<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> >> >> /MediaBox [0 0 612 792] /Contents 4 0 R >>\nendobj\n4 0 obj\n<< /Length 44 >>\nstream\nBT\n/F1 12 Tf\n100 700 Td\n(Test PDF) Tj\nET\nendstream\nendobj\nxref\n0 5\n0000000000 65535 f\n0000000009 00000 n\n0000000058 00000 n\n0000000115 00000 n\n0000000317 00000 n\ntrailer\n<< /Size 5 /Root 1 0 R >>\nstartxref\n410\n%%EOF"

    with tempfile.NamedTemporaryFile(mode="wb", suffix=".pdf", delete=False) as f:
        f.write(content)
        temp_path = f.name

    yield temp_path

    # Cleanup
    if os.path.exists(temp_path):
        os.remove(temp_path)


@pytest.fixture
def temp_csv_file():
    """Create a temporary CSV file for testing."""
    content = "Name,Age,City\nJohn,30,NYC\nJane,25,LA\nBob,35,SF"

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write(content)
        temp_path = f.name

    yield temp_path

    if os.path.exists(temp_path):
        os.remove(temp_path)


@pytest.fixture
def temp_txt_file():
    """Create a temporary text file for testing."""
    content = "This is a test text file.\nIt has multiple lines.\nFor testing purposes."

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write(content)
        temp_path = f.name

    yield temp_path

    if os.path.exists(temp_path):
        os.remove(temp_path)


@pytest.fixture
def mock_gemini_response(monkeypatch):
    """Mock Gemini API responses for all locations that use GeminiClient."""

    class MockGeminiClient:
        def __init__(self, *args, **kwargs):
            pass

        def explain_text(self, text, conversation=None, **kwargs):
            return f"Mock explanation: {str(text)[:50]}..."

        def generate_content(self, *args, **kwargs):
            return "Mock generated content."

    # Patch everywhere GeminiClient is used
    for target in [
        "services.gemini.GeminiClient",
        "apps.doc_x.services.processing_service.GeminiClient",
        "apps.doc_x.services.chat_service.GeminiClient",
        "apps.doc_x.views.GeminiClient",
    ]:
        monkeypatch.setattr(target, MockGeminiClient)

    return MockGeminiClient()
