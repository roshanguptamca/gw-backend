# apps/doc_x/views_v2.py
"""
New API endpoints for Doc_X v2 with backward compatibility.
These are the enhanced REST APIs that use the service layer.
"""
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from drf_spectacular.utils import (
    extend_schema,
    OpenApiParameter,
    OpenApiExample,
    inline_serializer,
)
from rest_framework import serializers as drf_serializers

from apps.doc_x.models import ChatSession
from apps.doc_x.services import DocumentService, ProcessingService, ChatService
from apps.doc_x.serializers import DocumentSerializer
import logging

logger = logging.getLogger(__name__)

# Service instances
document_service = DocumentService()
processing_service = ProcessingService()
chat_service = ChatService()


# ====================================================================================
# DOCUMENT MANAGEMENT APIs
# ====================================================================================


@extend_schema(
    tags=["Doc-X V2"],
    summary="Upload a document",
    description=(
        "Upload a document file using `multipart/form-data`. "
        "Supported types: `pdf`, `docx`, `doc`, `txt`, `csv`, `xlsx`, `xls`, `png`, `jpg`, `jpeg`. "
        "Maximum file size: **10 MB**. "
        "After upload, call `POST /documents/{id}/process` to trigger AI processing."
    ),
    request=inline_serializer(
        "UploadDocumentRequest",
        fields={
            "file": drf_serializers.FileField(help_text="Document file to upload"),
            "use_s3": drf_serializers.BooleanField(
                default=True,
                required=False,
                help_text="Store file in S3 (default: true)",
            ),
        },
    ),
    responses={
        201: inline_serializer(
            "UploadDocumentResponse",
            fields={
                "document_id": drf_serializers.IntegerField(),
                "filename": drf_serializers.CharField(),
                "file_type": drf_serializers.CharField(),
                "file_size": drf_serializers.IntegerField(help_text="File size in bytes"),
                "status": drf_serializers.CharField(help_text="pending | processing | completed | failed"),
                "message": drf_serializers.CharField(),
            },
        ),
        400: inline_serializer("UploadDocError", fields={"error": drf_serializers.CharField()}),
        500: inline_serializer("UploadDocServerError", fields={"error": drf_serializers.CharField()}),
    },
    examples=[
        OpenApiExample(
            "Success",
            value={
                "document_id": 15,
                "filename": "lease_agreement.pdf",
                "file_type": "pdf",
                "file_size": 204800,
                "status": "pending",
                "message": "File uploaded successfully. Use /documents/{id}/process to process it.",
            },
            response_only=True,
            status_codes=["201"],
        ),
        OpenApiExample(
            "File too large",
            value={"error": "File too large. Maximum size is 10MB, got 12.50MB"},
            response_only=True,
            status_codes=["400"],
        ),
    ],
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def upload_document(request):
    """
    POST /api/doc-x/documents/upload

    Upload a document file directly (multipart/form-data).

    Request:
        - file: File upload
        - use_s3: Optional boolean (default: True)

    Response:
        - document_id: ID of created document
        - filename: Original filename
        - file_type: Detected file type
        - file_size: File size in bytes
        - status: processing_status
    """
    if "file" not in request.FILES:
        return Response({"error": "No file provided"}, status=status.HTTP_400_BAD_REQUEST)

    uploaded_file = request.FILES["file"]
    use_s3 = request.data.get("use_s3", "true").lower() == "true"

    # Validate file type
    allowed_types = ["pdf", "docx", "doc", "txt", "csv", "xlsx", "xls", "png", "jpg", "jpeg"]
    file_ext = uploaded_file.name.rsplit(".", 1)[-1].lower()

    if file_ext not in allowed_types:
        return Response(
            {"error": f"Unsupported file type: .{file_ext}. Allowed: {', '.join(allowed_types)}"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Validate file size (10MB limit)
    max_size = 10 * 1024 * 1024  # 10MB
    if uploaded_file.size > max_size:
        return Response(
            {"error": f"File too large. Maximum size is 10MB, got {uploaded_file.size / 1024 / 1024:.2f}MB"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        doc, doc_file = document_service.upload_file(uploaded_file, user=request.user, use_s3=use_s3)

        return Response(
            {
                "document_id": doc.id,
                "filename": doc.filename,
                "file_type": doc.file_type,
                "file_size": doc.file_size,
                "status": doc.processing_status,
                "message": "File uploaded successfully. Use /documents/{id}/process to process it.",
            },
            status=status.HTTP_201_CREATED,
        )

    except Exception as e:
        logger.error(f"Upload failed: {e}")
        return Response({"error": f"Upload failed: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@extend_schema(
    tags=["Doc-X V2"],
    operation_id="doc_x_documents_list",
    summary="List documents",
    description="List all documents belonging to the authenticated user, ordered by most recent first.",
    parameters=[
        OpenApiParameter(
            name="limit",
            location=OpenApiParameter.QUERY,
            required=False,
            type=int,
            default=100,
            description="Maximum number of documents to return (default: 100)",
        )
    ],
    responses={
        200: inline_serializer(
            "ListDocumentsResponse",
            fields={
                "documents": DocumentSerializer(many=True),
                "count": drf_serializers.IntegerField(),
            },
        )
    },
    examples=[
        OpenApiExample(
            "Success",
            value={
                "documents": [
                    {
                        "id": 15,
                        "s3_key": "uploads/uuid.pdf",
                        "content": "This agreement...",
                        "summary": "A rental agreement...",
                        "created_at": "2024-01-15T10:30:00Z",
                        "user": 42,
                        "filename": "lease_agreement.pdf",
                        "file_type": "pdf",
                        "file_size": 204800,
                        "processing_status": "completed",
                        "metadata": {},
                    }
                ],
                "count": 1,
            },
            response_only=True,
            status_codes=["200"],
        )
    ],
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_documents(request):
    """
    GET /api/doc-x/documents

    List documents for the authenticated user.

    Query params:
        - limit: Number of documents to return (default: 100)

    Response:
        - documents: List of document objects
        - count: Number of documents returned
    """
    limit = int(request.query_params.get("limit", 100))
    documents = document_service.list_documents(user=request.user, limit=limit)

    return Response(
        {"documents": DocumentSerializer(documents, many=True).data, "count": len(documents)}, status=status.HTTP_200_OK
    )


@extend_schema(
    tags=["Doc-X V2"],
    operation_id="doc_x_document_retrieve",
    summary="Get a document",
    description="Retrieve a specific document by its ID. Only the document owner can access it.",
    parameters=[
        OpenApiParameter(
            name="document_id",
            location=OpenApiParameter.PATH,
            required=True,
            type=int,
            description="Document ID",
        )
    ],
    responses={
        200: DocumentSerializer,
        404: inline_serializer("GetDocNotFound", fields={"error": drf_serializers.CharField()}),
    },
    examples=[
        OpenApiExample(
            "Success",
            value={
                "id": 15,
                "s3_key": "uploads/uuid.pdf",
                "content": "This agreement is made between...",
                "summary": "A rental agreement between John and Jane for the property at 123 Main St.",
                "created_at": "2024-01-15T10:30:00Z",
                "user": 42,
                "filename": "lease_agreement.pdf",
                "file_type": "pdf",
                "file_size": 204800,
                "processing_status": "completed",
                "metadata": {"pages": 5, "language": "en"},
            },
            response_only=True,
            status_codes=["200"],
        )
    ],
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_document(request, document_id):
    """
    GET /api/doc-x/documents/{document_id}

    Get a specific document by ID.

    Response:
        - Complete document details including content and summary
    """
    doc = document_service.get_document(document_id, user=request.user)

    if not doc:
        return Response({"error": "Document not found"}, status=status.HTTP_404_NOT_FOUND)

    return Response(DocumentSerializer(doc).data, status=status.HTTP_200_OK)


@extend_schema(
    tags=["Doc-X V2"],
    summary="Delete a document",
    description="Permanently delete a document and all its associated files. This action is irreversible.",
    parameters=[
        OpenApiParameter(
            name="document_id",
            location=OpenApiParameter.PATH,
            required=True,
            type=int,
            description="Document ID",
        )
    ],
    responses={
        200: inline_serializer(
            "DeleteDocResponse",
            fields={"message": drf_serializers.CharField(default="Document deleted successfully")},
        ),
        404: inline_serializer("DeleteDocNotFound", fields={"error": drf_serializers.CharField()}),
    },
    examples=[
        OpenApiExample(
            "Success",
            value={"message": "Document deleted successfully"},
            response_only=True,
            status_codes=["200"],
        )
    ],
)
@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_document(request, document_id):
    """
    DELETE /api/doc-x/documents/{document_id}

    Delete a document and its associated files.

    Response:
        - message: Success message
    """
    success = document_service.delete_document(document_id, user=request.user)

    if not success:
        return Response({"error": "Document not found or permission denied"}, status=status.HTTP_404_NOT_FOUND)

    return Response({"message": "Document deleted successfully"}, status=status.HTTP_200_OK)


# ====================================================================================
# PROCESSING APIs
# ====================================================================================


@extend_schema(
    tags=["Doc-X V2"],
    summary="Process a document",
    description=(
        "Trigger AI processing for an uploaded document. "
        "This runs text extraction, summarization, and chunking. "
        "If the document is already processed, returns the current status immediately."
    ),
    parameters=[
        OpenApiParameter(
            name="document_id",
            location=OpenApiParameter.PATH,
            required=True,
            type=int,
            description="Document ID",
        )
    ],
    request=None,
    responses={
        200: inline_serializer(
            "ProcessDocumentResponse",
            fields={
                "status": drf_serializers.CharField(help_text="completed | failed | processing"),
                "text_length": drf_serializers.IntegerField(required=False),
                "summary_length": drf_serializers.IntegerField(required=False),
                "chunk_count": drf_serializers.IntegerField(required=False),
                "message": drf_serializers.CharField(required=False),
            },
        ),
        404: inline_serializer("ProcessDocNotFound", fields={"error": drf_serializers.CharField()}),
        500: inline_serializer(
            "ProcessDocFailed", fields={"status": drf_serializers.CharField(), "error": drf_serializers.CharField()}
        ),
    },
    examples=[
        OpenApiExample(
            "Success",
            value={
                "status": "completed",
                "text_length": 4250,
                "summary_length": 312,
                "chunk_count": 3,
            },
            response_only=True,
            status_codes=["200"],
        ),
        OpenApiExample(
            "Already processed",
            value={"message": "Document already processed", "status": "completed"},
            response_only=True,
            status_codes=["200"],
        ),
    ],
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def process_document_endpoint(request, document_id):
    """
    POST /api/doc-x/documents/{document_id}/process

    Trigger document processing (extraction, summarization, chunking).

    Response:
        - status: Processing status
        - text_length: Length of extracted text
        - summary_length: Length of generated summary
        - chunk_count: Number of chunks created
    """
    doc = document_service.get_document(document_id, user=request.user)

    if not doc:
        return Response({"error": "Document not found"}, status=status.HTTP_404_NOT_FOUND)

    if doc.processing_status == "completed":
        return Response(
            {"message": "Document already processed", "status": doc.processing_status}, status=status.HTTP_200_OK
        )

    # Process the document
    result = processing_service.process_document(doc)

    if result["status"] == "failed":
        return Response(result, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return Response(result, status=status.HTTP_200_OK)


@extend_schema(
    tags=["Doc-X V2"],
    summary="Get processing status",
    description="Poll the processing status of a document. Useful for showing progress indicators on the frontend.",
    parameters=[
        OpenApiParameter(
            name="document_id",
            location=OpenApiParameter.PATH,
            required=True,
            type=int,
            description="Document ID",
        )
    ],
    responses={
        200: inline_serializer(
            "ProcessingStatusResponse",
            fields={
                "document_id": drf_serializers.IntegerField(),
                "status": drf_serializers.CharField(help_text="pending | processing | completed | failed"),
                "has_content": drf_serializers.BooleanField(),
                "has_summary": drf_serializers.BooleanField(),
                "chunk_count": drf_serializers.IntegerField(),
            },
        ),
        404: inline_serializer("StatusNotFound", fields={"error": drf_serializers.CharField()}),
    },
    examples=[
        OpenApiExample(
            "Completed",
            value={
                "document_id": 15,
                "status": "completed",
                "has_content": True,
                "has_summary": True,
                "chunk_count": 3,
            },
            response_only=True,
            status_codes=["200"],
        ),
        OpenApiExample(
            "Still processing",
            value={
                "document_id": 15,
                "status": "processing",
                "has_content": False,
                "has_summary": False,
                "chunk_count": 0,
            },
            response_only=True,
            status_codes=["200"],
        ),
    ],
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_processing_status(request, document_id):
    """
    GET /api/doc-x/documents/{document_id}/status

    Get processing status for a document.

    Response:
        - document_id: Document ID
        - status: Current processing status
        - has_content: Boolean
        - has_summary: Boolean
        - chunk_count: Number of chunks
    """
    doc = document_service.get_document(document_id, user=request.user)

    if not doc:
        return Response({"error": "Document not found"}, status=status.HTTP_404_NOT_FOUND)

    status_info = processing_service.get_processing_status(doc)

    return Response(status_info, status=status.HTTP_200_OK)


# ====================================================================================
# CHAT APIs
# ====================================================================================


@extend_schema(
    tags=["Doc-X V2"],
    summary="Chat with a document",
    description=(
        "Send a message (question) about a processed document and receive an AI-generated response. "
        "The conversation history is maintained within the chat session. "
        "Each user is limited to a fixed number of questions per document. "
        "The document must have `processing_status = completed` before chatting."
    ),
    parameters=[
        OpenApiParameter(
            name="document_id",
            location=OpenApiParameter.PATH,
            required=True,
            type=int,
            description="Document ID",
        )
    ],
    request=inline_serializer(
        "ChatRequest",
        fields={"message": drf_serializers.CharField(help_text="Your question about the document")},
    ),
    responses={
        200: inline_serializer(
            "ChatResponse",
            fields={
                "user_message": inline_serializer(
                    "UserMessage",
                    fields={
                        "id": drf_serializers.UUIDField(),
                        "content": drf_serializers.CharField(),
                        "created_at": drf_serializers.DateTimeField(),
                    },
                ),
                "assistant_message": inline_serializer(
                    "AssistantMessage",
                    fields={
                        "id": drf_serializers.UUIDField(),
                        "content": drf_serializers.CharField(),
                        "created_at": drf_serializers.DateTimeField(),
                    },
                ),
                "remaining_questions": drf_serializers.IntegerField(),
            },
        ),
        400: inline_serializer("ChatBadRequest", fields={"error": drf_serializers.CharField()}),
        403: inline_serializer("ChatLimitReached", fields={"error": drf_serializers.CharField()}),
        404: inline_serializer("ChatDocNotFound", fields={"error": drf_serializers.CharField()}),
    },
    examples=[
        OpenApiExample(
            "Request",
            value={"message": "What are the key terms of this contract?"},
            request_only=True,
        ),
        OpenApiExample(
            "Success",
            value={
                "user_message": {
                    "id": "550e8400-e29b-41d4-a716-446655440001",
                    "content": "What are the key terms of this contract?",
                    "created_at": "2024-01-15T10:35:00Z",
                },
                "assistant_message": {
                    "id": "550e8400-e29b-41d4-a716-446655440002",
                    "content": "The key terms include: 1) Monthly rent of $1,500 due on the 1st...",
                    "created_at": "2024-01-15T10:35:02Z",
                },
                "remaining_questions": 2,
            },
            response_only=True,
            status_codes=["200"],
        ),
        OpenApiExample(
            "Limit reached",
            value={"error": "Question limit reached for this document"},
            response_only=True,
            status_codes=["403"],
        ),
    ],
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def chat_with_document(request, document_id):
    """
    POST /api/doc-x/documents/{document_id}/chat

    Send a chat message about a document.

    Request:
        - message: User's question/message

    Response:
        - user_message: User's message
        - assistant_message: AI response
        - remaining_questions: Number of questions remaining
    """
    doc = document_service.get_document(document_id, user=request.user)

    if not doc:
        return Response({"error": "Document not found"}, status=status.HTTP_404_NOT_FOUND)

    if doc.processing_status != "completed":
        return Response(
            {"error": "Document not yet processed. Please wait for processing to complete."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    message = request.data.get("message")
    if not message or not message.strip():
        return Response({"error": "Message is required"}, status=status.HTTP_400_BAD_REQUEST)

    # Check question limit
    can_ask, remaining = chat_service.check_question_limit(doc, user=request.user)
    if not can_ask:
        return Response({"error": "Question limit reached for this document"}, status=status.HTTP_403_FORBIDDEN)

    # Get or create chat session
    session = chat_service.get_or_create_session(doc, user=request.user)

    # Send message and get response
    user_msg, assistant_msg = chat_service.send_message(session, message, user=request.user)

    # Increment question count
    chat_service.increment_question_count(doc, user=request.user)

    # Update remaining count
    _, remaining = chat_service.check_question_limit(doc, user=request.user)

    return Response(
        {
            "user_message": {"id": str(user_msg.id), "content": user_msg.content, "created_at": user_msg.created_at},
            "assistant_message": {
                "id": str(assistant_msg.id),
                "content": assistant_msg.content,
                "created_at": assistant_msg.created_at,
            },
            "remaining_questions": remaining,
        },
        status=status.HTTP_200_OK,
    )


@extend_schema(
    tags=["Doc-X V2"],
    summary="Get chat message history",
    description="Retrieve the full chat history for a document. Returns messages ordered by creation time.",
    parameters=[
        OpenApiParameter(
            name="document_id",
            location=OpenApiParameter.PATH,
            required=True,
            type=int,
            description="Document ID",
        ),
        OpenApiParameter(
            name="limit",
            location=OpenApiParameter.QUERY,
            required=False,
            type=int,
            default=100,
            description="Maximum number of messages to return (default: 100)",
        ),
    ],
    responses={
        200: inline_serializer(
            "ChatMessagesResponse",
            fields={
                "messages": inline_serializer(
                    "ChatMessageItem",
                    fields={
                        "id": drf_serializers.UUIDField(),
                        "role": drf_serializers.ChoiceField(choices=["user", "assistant", "system"]),
                        "content": drf_serializers.CharField(),
                        "created_at": drf_serializers.DateTimeField(),
                    },
                    many=True,
                ),
                "count": drf_serializers.IntegerField(),
            },
        ),
        404: inline_serializer("MessagesNotFound", fields={"error": drf_serializers.CharField()}),
    },
    examples=[
        OpenApiExample(
            "Success",
            value={
                "messages": [
                    {
                        "id": "550e8400-e29b-41d4-a716-446655440001",
                        "role": "assistant",
                        "content": "This is a rental agreement between...",
                        "created_at": "2024-01-15T10:30:01Z",
                    },
                    {
                        "id": "550e8400-e29b-41d4-a716-446655440002",
                        "role": "user",
                        "content": "What is the monthly rent?",
                        "created_at": "2024-01-15T10:35:00Z",
                    },
                    {
                        "id": "550e8400-e29b-41d4-a716-446655440003",
                        "role": "assistant",
                        "content": "The monthly rent is $1,500.",
                        "created_at": "2024-01-15T10:35:02Z",
                    },
                ],
                "count": 3,
            },
            response_only=True,
            status_codes=["200"],
        ),
        OpenApiExample(
            "No chat yet",
            value={"messages": [], "count": 0},
            response_only=True,
            status_codes=["200"],
        ),
    ],
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_chat_messages(request, document_id):
    """
    GET /api/doc-x/documents/{document_id}/messages

    Get chat message history for a document.

    Query params:
        - limit: Number of messages to return (default: 100)

    Response:
        - messages: List of messages
        - count: Number of messages
    """
    doc = document_service.get_document(document_id, user=request.user)

    if not doc:
        return Response({"error": "Document not found"}, status=status.HTTP_404_NOT_FOUND)

    # Get active session
    session = ChatSession.objects.filter(document=doc, user=request.user, is_active=True).first()

    if not session:
        return Response({"messages": [], "count": 0}, status=status.HTTP_200_OK)

    limit = int(request.query_params.get("limit", 100))
    messages = chat_service.get_messages(session, limit=limit)

    messages_data = [
        {"id": str(msg.id), "role": msg.role, "content": msg.content, "created_at": msg.created_at} for msg in messages
    ]

    return Response({"messages": messages_data, "count": len(messages_data)}, status=status.HTTP_200_OK)
