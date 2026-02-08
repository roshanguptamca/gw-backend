# apps/doc_x/views.py
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .models import Document, Conversation, UserQuestionLimit
from .serializers import DocumentSerializer
from .extract import extract_pdf, extract_docx, extract_image
from services.s3 import S3Client
from services.ai import AIClient
from services.gemini import GeminiClient
from guidewisey.decorators import question_limit  # <-- our reusable decorator
import tempfile
import os


MAX_QUESTIONS_PER_USER = 3

# -------------------------------
# Process uploaded document
# -------------------------------
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@question_limit(use_session=True)
def process_document(request, document=None, user_question_limit=None):
    """
    Upload document from S3, extract text, generate AI explanation,
    and store Document + initial Conversation.
    """
    s3_client = S3Client()
    s3_key = request.data.get("s3_key")
    if not s3_key:
        return Response({"error": "s3_key is required"}, status=400)

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
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@question_limit()
def ask(request, document, user_question_limit):
    ai_client = AIClient()
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
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@question_limit(use_session=True)
def process_text(request, document=None, user_question_limit=None):
    ai_client = AIClient()
    gemini = GeminiClient()
    text = request.data.get("text")
    preferred_language = request.data.get("preferred_language", "English")

    if not text or len(text.strip()) < 10:
        return Response(
            {"error": "Text is required and must be meaningful"},
            status=400,
        )

    system_prompt = (
        "You explain government, school, and official documents "
        "in very simple, clear language. "
        f"Always respond in {preferred_language}."
    )

    try:
        explanation = gemini.explain_text(text=text, system_prompt=system_prompt)
    except Exception as e:
        return Response({"error": f"Failed to process text: {str(e)}"}, status=500)

    doc = Document.objects.create(
        s3_key="TEXT",
        content=text,
        summary=explanation,
    )

    Conversation.objects.create(
        document=doc,
        role="assistant",
        message=explanation,
    )

    return Response({"document_id": doc.id, "summary": explanation})


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