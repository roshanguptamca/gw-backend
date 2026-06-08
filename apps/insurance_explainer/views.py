import logging
import tempfile
import os

from django.http import Http404
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, OpenApiExample

from .models import InsuranceSession, InsuranceMessage
from .serializers import (
    ExplainRequestSerializer,
    InsuranceChatRequestSerializer,
    InsuranceSessionSerializer,
    InsuranceSessionListSerializer,
    InsuranceMessageSerializer,
)
from .services.gemini import InsuranceGeminiService

logger = logging.getLogger(__name__)

ANON_FREE_LIMIT = 3


def _ensure_session(request):
    """Ensure Django session exists and return session key."""
    if not request.session.session_key:
        request.session.create()
    return request.session.session_key


def _check_anon_insurance_limit(request):
    """Returns (allowed: bool, used: int). Increments counter on each call."""
    key = "insurance_anon_count"
    count = request.session.get(key, 0)
    if count >= ANON_FREE_LIMIT:
        return False, count
    request.session[key] = count + 1
    request.session.modified = True
    return True, count + 1


def _get_anon_insurance_remaining(request):
    return max(0, ANON_FREE_LIMIT - request.session.get("insurance_anon_count", 0))


def _extract_text_from_file(file):
    """Extract text from an uploaded file. Returns (text, filename, file_bytes)."""
    from apps.doc_x.extract import extract_pdf, extract_docx, extract_text_file

    filename = file.name or "upload"
    ext = os.path.splitext(filename)[1].lower()
    file_bytes = file.read()

    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name

    try:
        if ext == ".pdf":
            text = extract_pdf(tmp_path)
        elif ext in (".docx", ".doc"):
            text = extract_docx(tmp_path)
        elif ext == ".txt":
            text = extract_text_file(tmp_path)
        else:
            raise ValueError(f"Unsupported file type: {ext}. Supported: PDF, DOCX, TXT.")
    finally:
        os.unlink(tmp_path)

    return text, filename, file_bytes


class InsuranceExplainView(APIView):
    """POST/GET /api/insurance/sessions/"""

    permission_classes = [AllowAny]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    @extend_schema(
        tags=["Insurance Explainer"],
        summary="List insurance sessions",
        responses={200: InsuranceSessionListSerializer(many=True)},
    )
    def get(self, request):
        if request.user.is_authenticated:
            sessions = InsuranceSession.objects.filter(user=request.user)
        else:
            sk = request.session.session_key or ""
            sessions = InsuranceSession.objects.filter(anon_session_key=sk) if sk else InsuranceSession.objects.none()
        return Response(InsuranceSessionListSerializer(sessions, many=True).data)

    @extend_schema(
        tags=["Insurance Explainer"],
        summary="Analyse an insurance policy",
        description=(
            "Submit an insurance policy (text or file: PDF/DOCX/TXT) with country and language. "
            "Returns structured AI analysis: coverage, gaps, risks, and action items. "
            "Anonymous users get 3 free analyses per session."
        ),
        request=ExplainRequestSerializer,
        responses={201: InsuranceSessionSerializer},
        examples=[
            OpenApiExample(
                "Text submission",
                value={
                    "country": "Netherlands",
                    "language": "English",
                    "policy_text": "This health insurance policy covers hospitalisation...",
                    "provider_url": "https://insurer.nl/policy",
                },
                request_only=True,
            )
        ],
    )
    def post(self, request):
        # Anonymous free limit check
        anon_session_key = None
        if not request.user.is_authenticated:
            anon_session_key = _ensure_session(request)
            allowed, used = _check_anon_insurance_limit(request)
            if not allowed:
                return Response(
                    {
                        "error": "free_limit_reached",
                        "message": f"You've used all {ANON_FREE_LIMIT} free analyses. Create a free account to continue.",
                        "remaining": 0,
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

        serializer = ExplainRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        country = data["country"]
        language = data["language"]
        provider_url = data.get("provider_url", "")
        policy_text = data.get("policy_text", "")
        uploaded_file = data.get("file")
        filename = ""
        file_bytes = None

        if uploaded_file:
            try:
                policy_text, filename, file_bytes = _extract_text_from_file(uploaded_file)
            except ValueError as e:
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
            except Exception as e:
                logger.error("File extraction error: %s", e)
                return Response(
                    {"error": "Could not read the uploaded file. Please try pasting the text instead."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        if not policy_text or len(policy_text.strip()) < 50:
            return Response(
                {"error": "Not enough text to analyse. Please paste more of the policy."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        session = InsuranceSession.objects.create(
            user=request.user if request.user.is_authenticated else None,
            anon_session_key=anon_session_key,
            country=country,
            language=language,
            provider_url=provider_url,
            policy_text=policy_text,
            filename=filename,
            file_data=file_bytes,
            status=InsuranceSession.Status.PROCESSING,
        )

        try:
            service = InsuranceGeminiService()
            analysis = service.analyse_policy(policy_text, country, language, provider_url)
            session.analysis = analysis
            session.insurance_type = analysis.get("insurance_type", "")
            session.raw_summary = analysis.get("summary", "")
            session.status = InsuranceSession.Status.COMPLETED
        except Exception as e:
            logger.error("Insurance analysis failed session=%s: %s", session.id, e)
            session.status = InsuranceSession.Status.FAILED
            session.error_message = str(e)
            session.save()
            return Response(
                {"error": "AI analysis failed. Please try again.", "session_id": session.id},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        session.save()
        data = InsuranceSessionSerializer(session).data
        if not request.user.is_authenticated:
            data["remaining"] = _get_anon_insurance_remaining(request)
        return Response(data, status=status.HTTP_201_CREATED)


class InsuranceSessionDetailView(APIView):
    """GET/DELETE /api/insurance/sessions/<pk>/"""

    permission_classes = [AllowAny]

    def _get_session(self, request, pk):
        try:
            if request.user.is_authenticated:
                return InsuranceSession.objects.get(pk=pk, user=request.user)
            else:
                sk = request.session.session_key or ""
                return InsuranceSession.objects.get(pk=pk, anon_session_key=sk)
        except InsuranceSession.DoesNotExist:
            raise Http404

    @extend_schema(
        tags=["Insurance Explainer"],
        summary="Get insurance session details",
        responses={200: InsuranceSessionSerializer},
    )
    def get(self, request, pk):
        return Response(InsuranceSessionSerializer(self._get_session(request, pk)).data)

    @extend_schema(
        tags=["Insurance Explainer"],
        summary="Delete an insurance session",
        responses={204: None},
    )
    def delete(self, request, pk):
        self._get_session(request, pk).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class InsuranceChatView(APIView):
    """POST /api/insurance/sessions/<pk>/chat/"""

    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Insurance Explainer"],
        summary="Ask a follow-up question about the insurance policy",
        request=InsuranceChatRequestSerializer,
        responses={
            200: {
                "type": "object",
                "properties": {
                    "assistant_message": {"type": "string"},
                    "session_id": {"type": "integer"},
                },
            }
        },
        examples=[
            OpenApiExample(
                "Ask about exclusions",
                value={"message": "What pre-existing conditions are excluded?"},
                request_only=True,
            )
        ],
    )
    def post(self, request, pk):
        try:
            if request.user.is_authenticated:
                session = InsuranceSession.objects.get(pk=pk, user=request.user)
            else:
                sk = request.session.session_key or ""
                session = InsuranceSession.objects.get(pk=pk, anon_session_key=sk)
        except InsuranceSession.DoesNotExist:
            raise Http404

        if session.status != InsuranceSession.Status.COMPLETED:
            return Response(
                {"error": "Session analysis is not complete yet."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = InsuranceChatRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        question = serializer.validated_data["message"]
        InsuranceMessage.objects.create(session=session, role=InsuranceMessage.Role.USER, content=question)

        history = list(session.messages.values("role", "content").order_by("created_at")[:20])

        try:
            service = InsuranceGeminiService()
            answer = service.chat(
                policy_text=session.policy_text,
                analysis=session.analysis,
                history=history,
                question=question,
                country=session.country,
                language=session.language,
            )
        except Exception as e:
            logger.error("Insurance chat error session=%s: %s", session.id, e)
            return Response({"error": "AI response failed. Please try again."}, status=status.HTTP_502_BAD_GATEWAY)

        InsuranceMessage.objects.create(session=session, role=InsuranceMessage.Role.ASSISTANT, content=answer)
        return Response({"assistant_message": answer, "session_id": session.id})


class InsuranceMessagesView(APIView):
    """GET /api/insurance/sessions/<pk>/messages/"""

    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Insurance Explainer"],
        summary="Get chat history for an insurance session",
        responses={200: InsuranceMessageSerializer(many=True)},
    )
    def get(self, request, pk):
        try:
            if request.user.is_authenticated:
                session = InsuranceSession.objects.get(pk=pk, user=request.user)
            else:
                sk = request.session.session_key or ""
                session = InsuranceSession.objects.get(pk=pk, anon_session_key=sk)
        except InsuranceSession.DoesNotExist:
            raise Http404
        messages = session.messages.all()
        return Response({"messages": InsuranceMessageSerializer(messages, many=True).data})
