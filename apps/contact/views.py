import logging

from django.conf import settings
from django.core.mail import send_mail
from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema, inline_serializer
from rest_framework import serializers as drf_serializers
from rest_framework import status
from rest_framework.parsers import JSONParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import ContactMessageSerializer

logger = logging.getLogger(__name__)


class PlainTextJSONParser(JSONParser):
    media_type = "text/plain"


@extend_schema(
    tags=["Contact"],
    summary="Submit a contact message",
    description=(
        "Accepts a contact form submission (name, email, subject, message), "
        "persists it to the database, and sends an email notification to the "
        "site admin. No authentication required."
    ),
    request=ContactMessageSerializer,
    responses={
        201: inline_serializer(
            "ContactSuccessResponse",
            fields={"message": drf_serializers.CharField(default="Message received")},
        ),
        400: OpenApiResponse(description="Validation errors"),
    },
    examples=[
        OpenApiExample(
            "Valid submission",
            value={
                "name": "Jane Doe",
                "email": "jane@example.com",
                "subject": "Question about pricing",
                "message": "Hi, I'd like to know more about your plans.",
            },
            request_only=True,
        ),
        OpenApiExample(
            "Success",
            value={"message": "Message received"},
            response_only=True,
            status_codes=["201"],
        ),
    ],
    auth=[],
)
class ContactView(APIView):
    permission_classes = [AllowAny]
    parser_classes = [JSONParser, PlainTextJSONParser]

    @csrf_exempt
    def post(self, request):
        serializer = ContactMessageSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        contact = serializer.save()
        self._notify_admin(contact)

        return Response({"message": "Message received"}, status=status.HTTP_201_CREATED)

    def _notify_admin(self, contact):
        try:
            admin_email = getattr(settings, "CONTACT_ADMIN_EMAIL", "info@guidewisey.com")
            send_mail(
                subject=f"[Contact Us] {contact.subject}",
                message=(
                    f"New contact form submission:\n\n"
                    f"Name:    {contact.name}\n"
                    f"Email:   {contact.email}\n"
                    f"Subject: {contact.subject}\n\n"
                    f"Message:\n{contact.message}"
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[admin_email],
                fail_silently=True,
            )
        except Exception:
            logger.exception("Failed to send contact notification email")
