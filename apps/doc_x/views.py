# apps/doc_x/views.py
import logging
import os
import tempfile
import uuid

from drf_spectacular.utils import OpenApiExample, OpenApiParameter, extend_schema, inline_serializer
from rest_framework import serializers as drf_serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from guidewisey.decorators import question_limit
from services.ai import AIClient
from services.gemini import GeminiClient

try:
    from services.s3 import S3Client

    _S3_AVAILABLE = True
except ImportError:
    S3Client = None
    _S3_AVAILABLE = False

from .extract import extract_docx, extract_image, extract_pdf
from .models import Conversation, Document, UserQuestionLimit
from .serializers import DocumentSerializer

logger = logging.getLogger(__name__)

MAX_QUESTIONS_PER_USER = 3
ALLOWED_EXTENSIONS = ["pdf", "png", "jpg", "jpeg", "doc", "docx"]


@extend_schema(
    tags=["Doc-X V1 (Legacy)"],
    summary="Get presigned S3 upload URL",
    description=(
        "Returns a pre-signed S3 URL and the generated `s3_key`. "
        "The client uploads the file directly to S3 using this URL, "
        "then calls `POST /api/doc-x/process/` with the `s3_key`."
    ),
    request=inline_serializer(
        "UploadUrlRequest",
        fields={"filename": drf_serializers.CharField(help_text="Original filename including extension")},
    ),
    responses={
        200: inline_serializer(
            "UploadUrlResponse",
            fields={
                "upload_url": drf_serializers.URLField(help_text="Pre-signed S3 PUT URL (valid for ~15 minutes)"),
                "s3_key": drf_serializers.CharField(help_text="S3 object key to pass to /process/"),
            },
        ),
        400: inline_serializer(
            "UploadUrlErrorResponse",
            fields={"error": drf_serializers.CharField()},
        ),
    },
    examples=[
        OpenApiExample(
            "Request",
            value={"filename": "contract.pdf"},
            request_only=True,
        ),
        OpenApiExample(
            "Success",
            value={
                "upload_url": "https://s3.amazonaws.com/bucket/uploads/uuid.pdf?X-Amz-Signature=...",
                "s3_key": "uploads/550e8400-e29b-41d4-a716-446655440000.pdf",
            },
            response_only=True,
            status_codes=["200"],
        ),
    ],
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def get_upload_url(request):
    """
    Returns a presigned S3 URL for direct frontend upload.
    Frontend uploads to S3, then calls process_document with s3_key.
    """
    filename = request.data.get("filename")
    if not filename:
        return Response({"error": "filename is required"}, status=400)

    ext = filename.rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return Response({"error": f"Unsupported file type: .{ext}"}, status=400)

    # Generate unique S3 key
    s3_key = f"uploads/{uuid.uuid4()}.{ext}"

    try:
        if not _S3_AVAILABLE:
            return Response({"error": "S3 is not configured. This endpoint requires S3 storage."}, status=503)
        s3_client = S3Client()
        presigned_url = s3_client.generate_presigned_url(s3_key)
    except Exception as e:
        return Response({"error": f"Failed to generate upload URL: {str(e)}"}, status=500)

    return Response(
        {
            "upload_url": presigned_url,
            "s3_key": s3_key,
        }
    )


# -------------------------------
# Process uploaded document
# -------------------------------
@extend_schema(
    tags=["Doc-X V1 (Legacy)"],
    summary="Process a document from S3",
    description=(
        "Download the file from S3 using `s3_key`, extract text, generate an AI summary, "
        "and persist the document + initial conversation. "
        "Subject to per-user question limits."
    ),
    request=inline_serializer(
        "ProcessDocumentRequest",
        fields={"s3_key": drf_serializers.CharField(help_text="S3 object key returned by /upload-url/")},
    ),
    responses={
        200: DocumentSerializer,
        400: inline_serializer("ProcessDocError", fields={"error": drf_serializers.CharField()}),
        500: inline_serializer("ProcessDocServerError", fields={"error": drf_serializers.CharField()}),
    },
    examples=[
        OpenApiExample(
            "Request",
            value={"s3_key": "uploads/550e8400-e29b-41d4-a716-446655440000.pdf"},
            request_only=True,
        ),
        OpenApiExample(
            "Success",
            value={
                "id": 1,
                "s3_key": "uploads/550e8400-e29b-41d4-a716-446655440000.pdf",
                "content": "This agreement is made between...",
                "summary": "This is a rental agreement between John and Jane...",
                "created_at": "2024-01-15T10:30:00Z",
                "user": 42,
                "filename": None,
                "file_type": None,
                "file_size": None,
                "processing_status": "completed",
                "metadata": {},
            },
            response_only=True,
            status_codes=["200"],
        ),
    ],
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@question_limit(use_session=True)
def process_document(request, document=None, user_question_limit=None):
    """
    Upload document from S3, extract text, generate AI explanation,
    and store Document + initial Conversation.
    """
    s3_client = S3Client() if _S3_AVAILABLE else None
    ai_client = AIClient()
    s3_key = request.data.get("s3_key")
    if not s3_key:
        return Response({"error": "s3_key is required"}, status=400)

    if not _S3_AVAILABLE:
        return Response({"error": "S3 is not configured. This endpoint requires S3 storage."}, status=503)

    _, ext = os.path.splitext(s3_key)
    ext = ext.lower().replace(".", "")

    # Download file from S3 to temp path
    with tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}") as tmp_file:
        local_path = tmp_file.name
    try:
        s3_client.download_file(s3_key, local_path)
    except Exception as e:
        os.remove(local_path)
        return Response({"error": f"S3 download failed: {str(e)}"}, status=500)

    # Extract text from file
    try:
        if ext == "pdf":
            text = extract_pdf(local_path)
        elif ext in ["docx", "doc"]:
            text = extract_docx(local_path)
        elif ext in ["png", "jpg", "jpeg"]:
            text = extract_image(local_path)
        else:
            return Response({"error": "Unsupported file type"}, status=400)
    finally:
        os.remove(local_path)

    # Generate AI explanation
    try:
        explanation = ai_client.explain_text(text)
    except Exception as e:
        return Response({"error": f"AI explanation failed: {str(e)}"}, status=500)

    # Store in DB
    doc = Document.objects.create(s3_key=s3_key, content=text, summary=explanation)
    Conversation.objects.create(document=doc, role="assistant", message=explanation)

    return Response(DocumentSerializer(doc).data)


# -------------------------------
# Ask follow-up question
# -------------------------------
@extend_schema(
    tags=["Doc-X V1 (Legacy)"],
    summary="Ask a follow-up question about a document",
    description=(
        "Send a follow-up question about a previously processed document. "
        "The request must include `document_id` and `question`. "
        "Limited to 3 questions per user per document."
    ),
    request=inline_serializer(
        "AskRequest",
        fields={
            "document_id": drf_serializers.IntegerField(),
            "question": drf_serializers.CharField(),
        },
    ),
    responses={
        200: inline_serializer(
            "AskResponse",
            fields={
                "answer": drf_serializers.CharField(),
                "remaining": drf_serializers.IntegerField(help_text="Questions remaining for this document"),
            },
        ),
        400: inline_serializer("AskError", fields={"error": drf_serializers.CharField()}),
        403: inline_serializer("AskLimitError", fields={"error": drf_serializers.CharField()}),
    },
    examples=[
        OpenApiExample(
            "Request",
            value={"document_id": 1, "question": "What is the monthly rent amount?"},
            request_only=True,
        ),
        OpenApiExample(
            "Success",
            value={
                "answer": "The monthly rent is $1,500 due on the 1st of each month.",
                "remaining": 2,
            },
            response_only=True,
            status_codes=["200"],
        ),
    ],
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@question_limit()
def ask(request, document, user_question_limit):
    gemini = GeminiClient()
    question = request.data.get("question")
    if not question:
        return Response({"error": "Question is required"}, status=400)

    # Fetch conversation history
    conv_history = document.conversations.order_by("id").all()
    conversation = [{"role": c.role, "content": c.message} for c in conv_history]

    # Generate AI answer
    try:
        answer = gemini.explain_text(question, conversation)
    except Exception as e:
        return Response({"error": f"AI explanation failed: {str(e)}"}, status=500)

    # Save conversation
    Conversation.objects.create(document=document, role="user", message=question)
    Conversation.objects.create(document=document, role="assistant", message=answer)

    # Increment user's question count
    user_question_limit.count += 1
    user_question_limit.save()

    remaining = 3 - user_question_limit.count
    return Response({"answer": answer, "remaining": remaining})


# -------------------------------
# Process raw text input
# -------------------------------
@extend_schema(
    tags=["Doc-X V1 (Legacy)"],
    summary="Process raw text",
    description=(
        "Submit raw text (e.g., pasted from a document) for AI-powered simplification. "
        "Optionally specify a preferred response language. "
        "Returns a `document_id` for follow-up questions."
    ),
    request=inline_serializer(
        "ProcessTextRequest",
        fields={
            "text": drf_serializers.CharField(help_text="Raw document text (minimum 10 characters)"),
            "preferred_language": drf_serializers.CharField(
                default="English",
                required=False,
                help_text="Language for the AI response (e.g. 'Spanish', 'French')",
            ),
        },
    ),
    responses={
        200: inline_serializer(
            "ProcessTextResponse",
            fields={
                "document_id": drf_serializers.IntegerField(),
                "summary": drf_serializers.CharField(),
            },
        ),
        400: inline_serializer("ProcessTextError", fields={"error": drf_serializers.CharField()}),
    },
    examples=[
        OpenApiExample(
            "Request",
            value={
                "text": "Section 4.2: The tenant shall not sublet the premises without prior written consent...",
                "preferred_language": "Spanish",
            },
            request_only=True,
        ),
        OpenApiExample(
            "Success",
            value={
                "document_id": 7,
                "summary": "El inquilino no puede subarrendar sin permiso escrito del propietario...",
            },
            response_only=True,
            status_codes=["200"],
        ),
    ],
)
@api_view(["POST"])
@permission_classes([AllowAny])
@question_limit(use_session=True)
def process_text(request, document=None, user_question_limit=None):
    gemini = GeminiClient()
    text = request.data.get("text", "").strip()
    preferred_language = request.data.get("preferred_language", "English")

    if not text or len(text) < 10:
        return Response(
            {"error": "Text is required and must be at least 10 characters."},
            status=400,
        )

    # Cap input to 500K chars (Gemini 2.5 Flash handles ~1M tokens)
    if len(text) > 500_000:
        text = text[:500_000]

    system_prompt = (
        "You explain government, school, official, legal, and general documents "
        "in very simple, clear, and practical language. "
        "Summarise the key message, what it means for the reader, and what they should do next. "
        f"Always respond in {preferred_language}."
    )

    try:
        explanation = gemini.explain_text(text=text, system_prompt=system_prompt)
    except RuntimeError:
        return Response({"error": "AI service is not configured. Please set GEMINI_API_KEY."}, status=503)
    except Exception as e:
        logger.error(f"process_text Gemini error: {e}", exc_info=True)
        return Response({"error": f"Failed to process text: {str(e)}"}, status=500)

    doc = Document.objects.create(
        s3_key="TEXT",
        content=text,
        summary=explanation,
        processing_status="completed",
        user=request.user if request.user.is_authenticated else None,
        filename="pasted-text.txt",
        file_type="txt",
        file_size=len(text.encode("utf-8")),
    )

    Conversation.objects.create(document=doc, role="assistant", message=explanation)

    # Tell the frontend how many free uses remain (for anonymous users)
    remaining = None
    if not request.user.is_authenticated:
        used = user_question_limit.count
        remaining = max(0, 3 - used)

    response_data = {"document_id": doc.id, "summary": explanation}
    if remaining is not None:
        response_data["remaining"] = remaining
    return Response(response_data)


@extend_schema(
    tags=["Doc-X V1 (Legacy)"],
    summary="Get remaining questions for a document",
    description=(
        "Returns how many follow-up questions the authenticated user can still ask " "for a given document (max 3)."
    ),
    parameters=[
        OpenApiParameter(
            name="document_id",
            location=OpenApiParameter.QUERY,
            required=True,
            type=int,
            description="ID of the document",
        )
    ],
    responses={
        200: inline_serializer(
            "RemainingQuestionsResponse",
            fields={"remaining": drf_serializers.IntegerField(help_text="Questions remaining (0–3)")},
        ),
        400: inline_serializer("RemainingQuestionsError", fields={"error": drf_serializers.CharField()}),
        404: inline_serializer("RemainingQuestionsNotFound", fields={"error": drf_serializers.CharField()}),
    },
    examples=[
        OpenApiExample(
            "Success",
            value={"remaining": 2},
            response_only=True,
            status_codes=["200"],
        )
    ],
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_remaining_questions(request):
    document_id = request.query_params.get("document_id")
    if not document_id:
        return Response({"error": "document_id is required"}, status=400)
    try:
        doc = Document.objects.get(id=document_id)
    except Document.DoesNotExist:
        return Response({"error": "Document not found"}, status=404)

    uq, _ = UserQuestionLimit.objects.get_or_create(user=request.user, document=doc)
    remaining = MAX_QUESTIONS_PER_USER - uq.count
    return Response({"remaining": remaining})
