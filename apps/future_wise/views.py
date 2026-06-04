"""
REST API views for FutureWise / DearTomorrow.

Endpoints:
  POST   /api/future-wise/reminders/                      — create reminder (anon or auth)
  GET    /api/future-wise/reminders/                      — list my reminders (auth required)
  GET    /api/future-wise/reminders/<id>/                 — detail view (owner only)
  DELETE /api/future-wise/reminders/<id>/                 — cancel reminder (owner only)
  POST   /api/future-wise/reminders/<id>/test/            — send test via one channel
  GET    /api/future-wise/reminders/<id>/delivery-status/ — per-channel delivery logs
  GET    /api/future-wise/verify/<token>/                 — one-click email verification
  GET    /api/future-wise/notification-preferences/       — list user channel prefs
  PUT    /api/future-wise/notification-preferences/       — update user channel prefs
  POST   /api/future-wise/telegram/webhook/               — Telegram Bot update webhook
"""

import logging

from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import (
    extend_schema,
    OpenApiExample,
    OpenApiParameter,
    inline_serializer,
)
from rest_framework import serializers as drf_serializers

from .email_service import BrevoEmailService
from .models import EmailReminder, ReminderAttachment, ReminderChannel, UserNotificationPreference
from .serializers import (
    AttachmentUploadSerializer,
    CreateReminderSerializer,
    NotificationPreferenceSerializer,
    ReminderDeliveryStatusSerializer,
    ReminderDetailSerializer,
    ReminderListSerializer,
    TestReminderSerializer,
    UpdateNotificationPreferencesSerializer,
)
from .storage import AttachmentStorage
from .throttle import (
    CreateReminderAnonThrottle,
    CreateReminderUserThrottle,
    VerifyEmailThrottle,
    check_daily_reminder_limit,
    log_action,
)

logger = logging.getLogger(__name__)

_FRONTEND_BASE = getattr(settings, "FUTUREWAVE_FRONTEND_BASE_URL", "https://www.guidewisey.com")


def _get_client_ip(request) -> str:
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


def _build_verification_url(token: str) -> str:
    """Build the frontend verification URL for the verification email."""
    return f"{_FRONTEND_BASE}/future-wise/verify/{token}"


# ── Create / List ─────────────────────────────────────────────────────────────

_reminder_detail_example = {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "email": "future-self@example.com",
    "subject": "A message from your past self",
    "message": "Hey future me! I hope you achieved your goals this year...",
    "scheduled_at": "2025-01-01T09:00:00Z",
    "tier": "free",
    "brand_name": "FutureWise",
    "status": "pending_verification",
    "retry_count": 0,
    "sent_at": None,
    "created_at": "2024-01-15T10:30:00Z",
    "attachments": [],
    "is_anonymous": True,
}

_reminder_list_example = {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "email": "future-self@example.com",
    "subject": "A message from your past self",
    "scheduled_at": "2025-01-01T09:00:00Z",
    "tier": "free",
    "status": "scheduled",
    "sent_at": None,
    "created_at": "2024-01-15T10:30:00Z",
    "attachment_count": 0,
}


@extend_schema(tags=["FutureWise"])
class ReminderListCreateView(APIView):
    """
    POST — create a reminder (anonymous or authenticated).
    GET  — list authenticated user's reminders.
    """

    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_throttles(self):
        if self.request.method == "POST":
            if self.request.user.is_authenticated:
                return [CreateReminderUserThrottle()]
            return [CreateReminderAnonThrottle()]
        return []

    def get_permissions(self):
        if self.request.method == "GET":
            return [IsAuthenticated()]
        return [AllowAny()]

    # ── GET /reminders/ ───────────────────────────────────────────────────────

    @extend_schema(
        summary="List my reminders",
        description="Returns all reminders created by the authenticated user, ordered most-recent first.",
        responses={200: ReminderListSerializer(many=True)},
        examples=[
            OpenApiExample(
                "Success",
                value=[_reminder_list_example],
                response_only=True,
                status_codes=["200"],
            )
        ],
    )
    def get(self, request):
        reminders = (
            EmailReminder.objects.filter(user=request.user).prefetch_related("attachments").order_by("-created_at")
        )
        serializer = ReminderListSerializer(reminders, many=True)
        return Response(serializer.data)

    # ── POST /reminders/ ──────────────────────────────────────────────────────

    @extend_schema(
        summary="Create a reminder",
        description=(
            "Schedule a future self-email reminder. Works for both anonymous and authenticated users.\n\n"
            "**Anonymous users** receive a verification email and must click the link to activate the reminder.\n\n"
            "**Authenticated users** skip email verification — the reminder is immediately `scheduled`.\n\n"
            "Optionally attach up to 5 files (max 10 MB each). "
            "Attachments are stored in S3 and included in the delivery email.\n\n"
            "Rate limits: 5/hour (anonymous), 20/hour (authenticated), 10 reminders/hour per email address."
        ),
        request=CreateReminderSerializer,
        responses={
            201: ReminderDetailSerializer,
            400: inline_serializer("CreateReminderError", fields={"detail": drf_serializers.CharField()}),
            429: inline_serializer("CreateReminderRateLimit", fields={"detail": drf_serializers.CharField()}),
        },
        examples=[
            OpenApiExample(
                "Minimal request (JSON)",
                value={
                    "email": "future-self@example.com",
                    "subject": "A message from your past self",
                    "message": "Hey future me! I hope you achieved your goals...",
                    "scheduled_at": "2025-01-01T09:00:00Z",
                },
                request_only=True,
                media_type="application/json",
            ),
            OpenApiExample(
                "Premium tier request",
                value={
                    "email": "future-self@example.com",
                    "subject": "To my future self — 5 years from now",
                    "message": "I am writing this on your 30th birthday...",
                    "scheduled_at": "2029-06-15T08:00:00Z",
                    "tier": "premium",
                },
                request_only=True,
                media_type="application/json",
            ),
            OpenApiExample(
                "Created (anonymous — pending verification)",
                value={
                    **_reminder_detail_example,
                    "detail": "Reminder created. Please check your email to verify and confirm your reminder.",
                },
                response_only=True,
                status_codes=["201"],
            ),
            OpenApiExample(
                "Created (authenticated — immediately scheduled)",
                value={**_reminder_detail_example, "status": "scheduled", "is_anonymous": False},
                response_only=True,
                status_codes=["201"],
            ),
            OpenApiExample(
                "Rate limit exceeded",
                value={"detail": "Too many reminders created for this email address. Try again later."},
                response_only=True,
                status_codes=["429"],
            ),
        ],
        auth=[],
    )
    def post(self, request):
        # 1. Validate core fields
        body_serializer = CreateReminderSerializer(data=request.data)
        if not body_serializer.is_valid():
            return Response(body_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        email = body_serializer.validated_data["email"]
        ip = _get_client_ip(request)

        # 2. Daily free-user rate-limit check (3 reminders/day per email; superusers exempt)
        if not check_daily_reminder_limit(email, user=request.user):
            return Response(
                {"detail": "Free email reminder limit reached. You can create up to 3 email reminders per day."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        # 3. Validate attachments (if any)
        files = request.FILES.getlist("attachments")
        att_serializer = AttachmentUploadSerializer(data={"attachments": files})
        if not att_serializer.is_valid():
            return Response(att_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        validated_files = att_serializer.validated_data["attachments"]

        # 4. Build the reminder
        token = EmailReminder.generate_verification_token()
        is_auth = request.user.is_authenticated

        reminder = EmailReminder(
            user=request.user if is_auth else None,
            email=email,
            email_verified=is_auth,  # skip verification for registered users
            verification_token=token,
            verification_token_expires_at=EmailReminder.make_token_expiry(),
            subject=body_serializer.validated_data["subject"],
            message=body_serializer.validated_data["message"],
            scheduled_at=body_serializer.validated_data["scheduled_at"],
            tier=body_serializer.validated_data.get("tier", EmailReminder.Tier.FREE),
            letter_type=body_serializer.validated_data.get("letter_type", EmailReminder.LetterType.FUTURE_SELF),
            phone_number=body_serializer.validated_data.get("phone_number", ""),
            telegram_chat_id=body_serializer.validated_data.get("telegram_chat_id", ""),
            channels_requested=",".join(body_serializer.validated_data.get("channels") or ["email"]),
            status=(EmailReminder.Status.SCHEDULED if is_auth else EmailReminder.Status.PENDING_VERIFICATION),
        )
        reminder.save()

        # 5. Upload attachments (S3 or DB backend)
        if validated_files:
            storage = AttachmentStorage()
            for f in validated_files:
                content = f.read()
                content_type = f.content_type or "application/octet-stream"
                # Create the record first so DB backend can write file_data onto it
                att = ReminderAttachment(
                    reminder=reminder,
                    original_filename=f.name,
                    content_type=content_type,
                    size_bytes=f.size,
                )
                att.save()
                storage_key = storage.upload(content, f.name, content_type, attachment_instance=att)
                att.storage_key = storage_key
                att.s3_key = storage_key  # keep legacy field in sync
                att.save(update_fields=["storage_key", "s3_key", "file_data"])

        # 6. Send verification email for anonymous users
        if not is_auth:
            try:
                verification_url = _build_verification_url(token)
                BrevoEmailService().send_verification_email(email, verification_url)
            except Exception as exc:
                logger.error("Failed to send verification email for %s: %s", email, exc)
                reminder.delete()
                return Response(
                    {"detail": "We couldn't send your verification email. Please try again later."},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )

        log_action(email, ip, "create_reminder")

        serializer = ReminderDetailSerializer(reminder)
        http_status = status.HTTP_201_CREATED
        response_data = serializer.data

        if not is_auth:
            response_data = {
                **response_data,
                "detail": ("Reminder created. Please check your email to verify and confirm your reminder."),
            }

        return Response(response_data, status=http_status)


# ── Detail / Cancel ───────────────────────────────────────────────────────────


@extend_schema(tags=["FutureWise"])
class ReminderDetailView(APIView):
    """
    GET    — retrieve a single reminder (owner or anonymous token holder).
    DELETE — cancel a reminder (owner only; only if not yet sent).
    """

    def _get_reminder(self, request, pk):
        """
        Return the reminder if the caller is authorized to view/modify it.
        Authorization: authenticated user must own it,
                       anonymous callers must supply ?token= query param.
        """
        reminder = get_object_or_404(EmailReminder, id=pk)

        if request.user.is_authenticated:
            if reminder.user != request.user:
                from rest_framework.exceptions import PermissionDenied

                raise PermissionDenied("You do not own this reminder.")
            return reminder

        # Anonymous access: require the verification token as a query param
        token = request.query_params.get("token", "")
        if not token or reminder.verification_token != token:
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("Invalid or missing token.")

        return reminder

    @extend_schema(
        summary="Get reminder detail",
        description=(
            "Retrieve a single reminder. "
            "Authenticated users can access their own reminders. "
            "Anonymous users must supply the `?token=` query parameter "
            "(the verification token sent to their email)."
        ),
        parameters=[
            OpenApiParameter(
                name="pk",
                location=OpenApiParameter.PATH,
                type=str,
                description="Reminder UUID",
            ),
            OpenApiParameter(
                name="token",
                location=OpenApiParameter.QUERY,
                required=False,
                type=str,
                description="Verification token (required for anonymous access)",
            ),
        ],
        responses={
            200: ReminderDetailSerializer,
            403: inline_serializer("ReminderForbidden", fields={"detail": drf_serializers.CharField()}),
            404: inline_serializer("ReminderNotFound", fields={"detail": drf_serializers.CharField()}),
        },
        examples=[
            OpenApiExample(
                "Success",
                value=_reminder_detail_example,
                response_only=True,
                status_codes=["200"],
            )
        ],
    )
    def get(self, request, pk):
        reminder = self._get_reminder(request, pk)
        serializer = ReminderDetailSerializer(reminder)
        return Response(serializer.data)

    @extend_schema(
        summary="Cancel a reminder",
        description=(
            "Cancel a scheduled reminder. "
            "Only the owner (authenticated) can cancel. "
            "Cannot cancel reminders that are already `sent`, `dead_letter`, or `cancelled`."
        ),
        parameters=[
            OpenApiParameter(
                name="pk",
                location=OpenApiParameter.PATH,
                type=str,
                description="Reminder UUID",
            )
        ],
        request=None,
        responses={
            200: inline_serializer(
                "CancelReminderResponse",
                fields={"detail": drf_serializers.CharField(default="Reminder cancelled.")},
            ),
            400: inline_serializer(
                "CancelReminderError",
                fields={"detail": drf_serializers.CharField()},
            ),
            403: inline_serializer("CancelForbidden", fields={"detail": drf_serializers.CharField()}),
            404: inline_serializer("CancelNotFound", fields={"detail": drf_serializers.CharField()}),
        },
        examples=[
            OpenApiExample(
                "Cancelled",
                value={"detail": "Reminder cancelled."},
                response_only=True,
                status_codes=["200"],
            ),
            OpenApiExample(
                "Cannot cancel sent reminder",
                value={"detail": "Cannot cancel a reminder with status 'sent'."},
                response_only=True,
                status_codes=["400"],
            ),
        ],
    )
    def delete(self, request, pk):
        reminder = self._get_reminder(request, pk)

        non_cancellable = {
            EmailReminder.Status.SENT,
            EmailReminder.Status.DEAD_LETTER,
            EmailReminder.Status.CANCELLED,
        }
        if reminder.status in non_cancellable:
            return Response(
                {"detail": f"Cannot cancel a reminder with status '{reminder.status}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        reminder.status = EmailReminder.Status.CANCELLED
        reminder.save(update_fields=["status", "updated_at"])
        return Response({"detail": "Reminder cancelled."}, status=status.HTTP_200_OK)


# ── Email Verification ────────────────────────────────────────────────────────


class VerifyEmailView(APIView):
    """
    GET /verify/<token>/
    One-click email verification that activates the reminder.
    After verification the reminder moves from PENDING_VERIFICATION → SCHEDULED.
    """

    permission_classes = [AllowAny]
    throttle_classes = [VerifyEmailThrottle]

    @extend_schema(
        tags=["FutureWise"],
        summary="Verify email and activate reminder",
        description=(
            "One-click email verification link. "
            "When an anonymous user creates a reminder, a verification email is sent. "
            "Clicking the link calls this endpoint, which moves the reminder from "
            "`pending_verification` → `scheduled`.\n\n"
            "Tokens are valid for **30 minutes**. "
            "If expired, the reminder is cancelled and a new one must be created."
        ),
        parameters=[
            OpenApiParameter(
                name="token",
                location=OpenApiParameter.PATH,
                required=True,
                type=str,
                description="URL-safe verification token from the email link",
            )
        ],
        responses={
            200: inline_serializer(
                "VerifyEmailResponse",
                fields={
                    "detail": drf_serializers.CharField(),
                    "reminder_id": drf_serializers.UUIDField(),
                    "scheduled_at": drf_serializers.DateTimeField(),
                    "redirect_url": drf_serializers.URLField(),
                },
            ),
            404: inline_serializer(
                "VerifyEmailNotFound",
                fields={"detail": drf_serializers.CharField()},
            ),
            410: inline_serializer(
                "VerifyEmailExpired",
                fields={"detail": drf_serializers.CharField()},
            ),
        },
        examples=[
            OpenApiExample(
                "Verified successfully",
                value={
                    "detail": "Email verified. Your reminder is now scheduled.",
                    "reminder_id": "550e8400-e29b-41d4-a716-446655440000",
                    "scheduled_at": "2025-01-01T09:00:00Z",
                    "redirect_url": "https://www.guidewisey.com/reminder-confirmed?id=550e8400-...",
                },
                response_only=True,
                status_codes=["200"],
            ),
            OpenApiExample(
                "Invalid token",
                value={"detail": "Invalid or already-used verification token."},
                response_only=True,
                status_codes=["404"],
            ),
            OpenApiExample(
                "Expired token",
                value={"detail": "Verification link has expired. Please create a new reminder."},
                response_only=True,
                status_codes=["410"],
            ),
        ],
        auth=[],
    )
    def get(self, request, token):
        try:
            reminder = EmailReminder.objects.get(
                verification_token=token,
                status=EmailReminder.Status.PENDING_VERIFICATION,
            )
        except EmailReminder.DoesNotExist:
            return Response(
                {"detail": "Invalid or already-used verification token."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if not reminder.is_verification_token_valid():
            reminder.status = EmailReminder.Status.CANCELLED
            reminder.save(update_fields=["status", "updated_at"])
            return Response(
                {"detail": "Verification link has expired. Please create a new reminder."},
                status=status.HTTP_410_GONE,
            )

        reminder.email_verified = True
        reminder.status = EmailReminder.Status.SCHEDULED
        reminder.save(update_fields=["email_verified", "status", "updated_at"])

        ip = _get_client_ip(request)
        log_action(reminder.email, ip, "verify_email")

        logger.info(
            "FutureWise: email verified for reminder %s (scheduled: %s)",
            reminder.id,
            reminder.scheduled_at,
        )

        # Optionally redirect to frontend confirmation page
        frontend_url = f"{_FRONTEND_BASE}/reminder-confirmed?id={reminder.id}"
        # Return JSON for API clients; frontend can also follow the redirect
        return Response(
            {
                "detail": "Email verified. Your reminder is now scheduled.",
                "reminder_id": str(reminder.id),
                "scheduled_at": reminder.scheduled_at,
                "redirect_url": frontend_url,
            },
            status=status.HTTP_200_OK,
        )


# ── Delivery Status ───────────────────────────────────────────────────────────


@extend_schema(tags=["FutureWise"])
class ReminderDeliveryStatusView(APIView):
    """
    GET /reminders/<id>/delivery-status/
    Returns per-channel delivery log for a reminder.
    Requires authentication (owner only).
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Get reminder delivery status",
        description="Returns per-channel delivery logs for the given reminder.",
        responses={200: ReminderDeliveryStatusSerializer},
    )
    def get(self, request, pk):
        reminder = get_object_or_404(EmailReminder, id=pk, user=request.user)
        serializer = ReminderDeliveryStatusSerializer(reminder)
        return Response(serializer.data)


# ── Test Send ─────────────────────────────────────────────────────────────────


@extend_schema(tags=["FutureWise"])
class ReminderTestSendView(APIView):
    """
    POST /reminders/<id>/test/
    Trigger an immediate test delivery on the specified channel.
    Does not affect reminder status or retry_count.
    Requires authentication.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Send a test reminder",
        description=(
            "Immediately deliver the reminder via the specified channel. "
            "Does not change the reminder's status or retry count. "
            "Useful for verifying credentials and contact details before the scheduled date."
        ),
        request=TestReminderSerializer,
        responses={
            200: inline_serializer(
                "TestSendResponse",
                fields={
                    "channel": drf_serializers.CharField(),
                    "success": drf_serializers.BooleanField(),
                    "provider_message_id": drf_serializers.CharField(),
                    "error": drf_serializers.CharField(allow_null=True),
                },
            ),
        },
    )
    def post(self, request, pk):
        reminder = get_object_or_404(EmailReminder, id=pk, user=request.user)

        ser = TestReminderSerializer(data=request.data)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)

        channel_code = ser.validated_data["channel"]

        from .providers import PROVIDER_REGISTRY
        from .dispatcher import ReminderDispatcher

        provider_cls = PROVIDER_REGISTRY.get(channel_code)
        if provider_cls is None:
            return Response(
                {"detail": f"Unknown channel '{channel_code}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        dispatcher = ReminderDispatcher()
        ctx = dispatcher._build_recipient_context(reminder)
        provider = provider_cls()

        if not provider.is_available(ctx):
            return Response(
                {
                    "channel": channel_code,
                    "success": False,
                    "provider_message_id": "",
                    "error": (
                        "Channel not available: missing contact details or opt-in consent. "
                        "Update your notification preferences first."
                    ),
                },
                status=status.HTTP_200_OK,
            )

        result = provider.send(reminder, ctx)
        return Response(
            {
                "channel": channel_code,
                "success": result.success,
                "provider_message_id": result.provider_message_id,
                "error": result.error_message if not result.success else None,
            },
            status=status.HTTP_200_OK,
        )


# ── Notification Preferences ──────────────────────────────────────────────────


@extend_schema(tags=["FutureWise"])
class NotificationPreferencesView(APIView):
    """
    GET /notification-preferences/  — list the authenticated user's channel prefs.
    PUT /notification-preferences/  — bulk-update channel prefs.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Get notification preferences",
        description="Returns channel opt-in state and contact details for the authenticated user.",
        responses={200: NotificationPreferenceSerializer(many=True)},
    )
    def get(self, request):
        prefs = (
            UserNotificationPreference.objects.filter(user=request.user)
            .select_related("channel")
            .order_by("channel__code")
        )
        serializer = NotificationPreferenceSerializer(prefs, many=True)
        return Response(serializer.data)

    @extend_schema(
        summary="Update notification preferences",
        description=(
            "Bulk-update channel preferences. "
            "Pass a dict keyed by channel code with the fields to update. "
            "Missing channels are left unchanged."
        ),
        request=UpdateNotificationPreferencesSerializer,
        responses={
            200: NotificationPreferenceSerializer(many=True),
            400: inline_serializer("PrefError", fields={"detail": drf_serializers.CharField()}),
        },
    )
    def put(self, request):
        ser = UpdateNotificationPreferencesSerializer(data=request.data)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)

        updated = []
        for channel_code, fields in request.data.items():
            if not isinstance(fields, dict):
                continue
            try:
                channel = ReminderChannel.objects.get(code=channel_code, is_active=True)
            except ReminderChannel.DoesNotExist:
                continue

            pref, _ = UserNotificationPreference.objects.get_or_create(
                user=request.user,
                channel=channel,
                defaults={"email": request.user.email},
            )

            if "is_opted_in" in fields:
                pref.is_opted_in = str(fields["is_opted_in"]).lower() in ("true", "1", "yes")
            if "phone_number" in fields:
                phone = fields["phone_number"]
                import re as _re

                if phone and not _re.match(r"^\+[1-9]\d{7,14}$", phone):
                    return Response(
                        {"detail": f"Invalid phone_number for {channel_code}. Use E.164 format."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                pref.phone_number = phone
            if "telegram_chat_id" in fields:
                pref.telegram_chat_id = fields["telegram_chat_id"]
            if "whatsapp_opted_in" in fields:
                pref.whatsapp_opted_in = str(fields["whatsapp_opted_in"]).lower() in ("true", "1", "yes")
            pref.save()
            updated.append(pref)

        serializer = NotificationPreferenceSerializer(updated, many=True)
        return Response(serializer.data)


# ── Telegram Bot Webhook ──────────────────────────────────────────────────────


@extend_schema(tags=["FutureWise"])
class TelegramWebhookView(APIView):
    """
    POST /telegram/webhook/
    Receives update events from the Telegram Bot API.

    On /start <token>, links the user's Telegram chat_id to their account.
    The start parameter should be a URL-safe token identifying the user
    (e.g. their reminder UUID encoded as a URL-safe string).

    Register this webhook:
        curl -F "url=https://<domain>/api/future-wise/telegram/webhook/" \\
             https://api.telegram.org/bot<TOKEN>/setWebhook
    """

    permission_classes = [AllowAny]
    # No CSRF needed — Telegram sends POST with JSON body

    @extend_schema(
        summary="Telegram Bot webhook",
        description="Receives Telegram Bot updates. Captures chat_id on /start command.",
        request=inline_serializer(
            "TelegramUpdate",
            fields={"update_id": drf_serializers.IntegerField()},
        ),
        responses={200: inline_serializer("TelegramOK", fields={"ok": drf_serializers.BooleanField()})},
        auth=[],
    )
    def post(self, request):
        data = request.data or {}
        message = data.get("message") or data.get("edited_message") or {}
        text: str = (message.get("text") or "").strip()
        chat_id = str(message.get("chat", {}).get("id", ""))

        logger.info(
            "TelegramWebhookView: update from chat_id=%s text='%s'",
            chat_id,
            text[:100],
        )

        if text.startswith("/start") and chat_id:
            # /start may carry a payload: /start <reminder_uuid>
            # For now, store the chat_id against any matching unlinked preference
            # or create a new one if a Telegram channel exists.
            parts = text.split(None, 1)
            start_param = parts[1].strip() if len(parts) > 1 else ""

            self._handle_start(chat_id, start_param, request)

        return Response({"ok": True})

    def _handle_start(self, chat_id: str, start_param: str, request) -> None:
        """
        Link chat_id to a UserNotificationPreference.

        If start_param is a valid reminder UUID, link it to that reminder's user.
        Otherwise, update any existing Telegram pref without a chat_id that is
        attached to the authenticated user (fallback — mainly useful in testing).
        """
        telegram_channel = ReminderChannel.objects.filter(code="telegram", is_active=True).first()
        if telegram_channel is None:
            logger.warning("TelegramWebhookView: telegram channel not found in DB — run seed_channels")
            return

        # Attempt to match via start_param (reminder UUID)
        if start_param:
            try:
                import uuid as _uuid

                reminder_id = _uuid.UUID(start_param)
                reminder = EmailReminder.objects.select_related("user").get(id=reminder_id)
                if reminder.user_id:
                    pref, _ = UserNotificationPreference.objects.get_or_create(
                        user=reminder.user,
                        channel=telegram_channel,
                        defaults={"email": reminder.email},
                    )
                    pref.telegram_chat_id = chat_id
                    pref.is_opted_in = True
                    pref.save(update_fields=["telegram_chat_id", "is_opted_in", "updated_at"])
                    logger.info(
                        "TelegramWebhookView: linked chat_id=%s to user=%s via reminder=%s",
                        chat_id,
                        reminder.user_id,
                        reminder_id,
                    )
                    return
            except (ValueError, EmailReminder.DoesNotExist):
                pass

        logger.info(
            "TelegramWebhookView: /start received from chat_id=%s (no matching reminder param)",
            chat_id,
        )
