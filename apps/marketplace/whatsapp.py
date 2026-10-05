"""Template-only seller notifications, independent of the FutureWise reminder provider."""

import logging
import os
import re
from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol
from urllib.parse import urlsplit

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import close_old_connections
from django.db.models import F
from django.utils import timezone

import requests

from .models import OrderWhatsAppNotification
from .ordering import describe_quantity
from .validators import normalize_whatsapp_phone

logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 4
CLAIM_TIMEOUT = timedelta(minutes=5)
RETRYABLE_ERROR_CODES = {2, 4, 80007, 130429, 131000, 131016, 131056}
TEMPLATE_BODY = (
    "New order - {{1}}\nAn order has been placed in your shop.\n"
    "Order: {{2}}\nCustomer: {{3}}\nPhone: {{4}}\nEmail: {{5}}\n"
    "Items: {{6}}\nTotal: {{7}}\nDelivery method: {{8}}\nAddress: {{9}}\n"
    "Requested date: {{10}}\nRequested time: {{11}}\nCustomer note: {{12}}\nOpen order: {{13}}\n"
    "Please review this order in the seller portal before preparing it."
)


def config(name: str) -> str:
    return str(getattr(settings, name, os.environ.get(name, ""))).strip()


@dataclass(frozen=True)
class DeliveryResult:
    message_id: str = ""
    error: str = ""
    retryable: bool = False
    uncertain: bool = False


class WhatsAppProvider(Protocol):
    def send(self, recipient: str, parameters: list[str]) -> DeliveryResult: ...


class MetaCloudWhatsAppProvider:
    def send(self, recipient: str, parameters: list[str]) -> DeliveryResult:
        token = config("WHATSAPP_ACCESS_TOKEN")
        phone_id = config("WHATSAPP_PHONE_NUMBER_ID")
        version = config("WHATSAPP_API_VERSION")
        template = config("WHATSAPP_ORDER_TEMPLATE_NAME")
        language = config("WHATSAPP_ORDER_TEMPLATE_LANGUAGE")
        if (
            not token
            or not re.fullmatch(r"[0-9]+", phone_id)
            or not re.fullmatch(r"v[0-9]+\.[0-9]+", version)
            or not re.fullmatch(r"[a-z0-9_]{1,512}", template)
            or not re.fullmatch(r"[a-z]{2}(?:_[A-Z]{2})?", language)
        ):
            return DeliveryResult(error="WhatsApp provider configuration is missing or invalid.")
        try:
            response = requests.post(
                f"https://graph.facebook.com/{version}/{phone_id}/messages",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "messaging_product": "whatsapp",
                    "recipient_type": "individual",
                    "to": recipient,
                    "type": "template",
                    "template": {
                        "name": template,
                        "language": {"code": language},
                        "components": [
                            {
                                "type": "body",
                                "parameters": [{"type": "text", "text": value} for value in parameters],
                            }
                        ],
                    },
                },
                timeout=(5, 15),
                allow_redirects=False,
            )
        except requests.RequestException:
            # A timeout/reset can happen AFTER Meta accepted the message. Meta
            # offers no send idempotency key: automatic resend could spam sellers.
            return DeliveryResult(error="Network outcome uncertain; reconcile before resending.", uncertain=True)
        try:
            body = response.json()
        except ValueError:
            return DeliveryResult(error="Invalid provider response; outcome uncertain.", uncertain=True)
        if not isinstance(body, dict):
            return DeliveryResult(error="Invalid provider response; outcome uncertain.", uncertain=True)
        if 200 <= response.status_code < 300:
            messages = body.get("messages")
            message_id = (
                messages[0].get("id")
                if isinstance(messages, list) and messages and isinstance(messages[0], dict)
                else None
            )
            if isinstance(message_id, str) and 0 < len(message_id) <= 255:
                return DeliveryResult(message_id=message_id)
            return DeliveryResult(error="Provider accepted request without message ID.", uncertain=True)
        error = body.get("error")
        code = error.get("code") if isinstance(error, dict) else None
        if not isinstance(code, int):
            code = None
        # Only documented explicit transient rejections are retried. Neither raw response
        # text nor exception strings are retained (they may contain PII/secrets).
        retryable = response.status_code == 429 or code in RETRYABLE_ERROR_CODES
        safe_code = str(code) if isinstance(code, int) else "unavailable"
        return DeliveryResult(
            error=f"Meta rejected request (HTTP {response.status_code}, code {safe_code}).",
            retryable=retryable,
            uncertain=response.status_code >= 500 and not retryable,
        )


def _text(value, limit: int) -> str:
    text = " ".join(str(value or "").split()) or "Not provided"
    return text if len(text) <= limit else text[: limit - 3] + "..."


def order_parameters(order) -> list[str]:
    snapshot = order.fulfillment_snapshot
    base_url = config("MARKETPLACE_SELLER_PORTAL_URL")
    parsed = urlsplit(base_url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or len(base_url) > 180
    ):
        raise ValueError("MARKETPLACE_SELLER_PORTAL_URL must be an HTTPS marketplace origin.")
    order_url = f"{base_url.rstrip('/')}/seller/orders?order={order.pk}"
    address = snapshot.get("shop_address", "") if order.order_type == "pickup" else order.delivery_address
    parameters = [
        _text(snapshot.get("shop_name") or order.shop.name, 60),
        _text(order.order_number, 30),
        _text(order.customer_name, 60),
        _text(order.customer_phone, 30),
        _text(order.customer_email, 80),
        _text(
            "; ".join(f"{describe_quantity(item, item.quantity)} {item.product_name}" for item in order.items.all()),
            220,
        ),
        _text(f"{snapshot.get('currency', 'EUR')} {order.total:.2f}", 30),
        order.get_order_type_display(),
        _text(address, 160),
        _text(snapshot.get("pickup_date") if order.order_type == "pickup" else "Not applicable", 30),
        _text(snapshot.get("pickup_time") if order.order_type == "pickup" else "Not applicable", 35),
        _text(order.customer_note, 120),
        order_url,
    ]
    # Meta text template parameters cannot contain newlines/tabs. Bound the
    # entire rendered template, not only individual variables.
    for index in (5, 11, 8, 4, 0, 2):
        excess = len(render_message(parameters)) - 1024
        if excess <= 0:
            break
        parameters[index] = _text(parameters[index], max(16, len(parameters[index]) - excess))
    if len(render_message(parameters)) > 1024:
        raise ValueError("Order template exceeds the Meta body limit.")
    return parameters


def render_message(parameters: list[str]) -> str:
    return re.sub(r"\{\{(\d+)\}\}", lambda match: parameters[int(match.group(1)) - 1], TEMPLATE_BODY)


class WhatsAppNotificationService:
    @staticmethod
    def enqueue(order):
        shop_settings = getattr(order.shop, "settings", None)
        if not shop_settings or not shop_settings.whatsapp_notifications_enabled:
            return None
        try:
            recipient = normalize_whatsapp_phone(shop_settings.whatsapp_number)
        except ValidationError:
            logger.warning("WhatsApp skipped for order %s: missing/invalid recipient.", order.pk)
            return None
        notification, _ = OrderWhatsAppNotification.objects.get_or_create(
            order=order, defaults={"recipient": recipient}
        )
        return notification

    @staticmethod
    def deliver(notification_id: int, provider: WhatsAppProvider | None = None) -> None:
        now = timezone.now()
        claimed = OrderWhatsAppNotification.objects.filter(
            pk=notification_id,
            status=OrderWhatsAppNotification.Status.PENDING,
            next_attempt_at__lte=now,
            attempts__lt=MAX_ATTEMPTS,
        ).update(status=OrderWhatsAppNotification.Status.PROCESSING, claimed_at=now, attempts=F("attempts") + 1)
        if not claimed:
            return
        notification = (
            OrderWhatsAppNotification.objects.select_related("order__shop__settings")
            .prefetch_related("order__items")
            .get(pk=notification_id)
        )
        shop_settings = getattr(notification.order.shop, "settings", None)
        current_recipient = ""
        if shop_settings and shop_settings.whatsapp_notifications_enabled:
            try:
                current_recipient = normalize_whatsapp_phone(shop_settings.whatsapp_number)
            except ValidationError:
                logger.warning("WhatsApp order=%s: shop number is no longer valid.", notification.order_id)
        if current_recipient != notification.recipient:
            notification.status = OrderWhatsAppNotification.Status.SKIPPED
            notification.error = "Notifications disabled or recipient changed before delivery."
        else:
            try:
                parameters = order_parameters(notification.order)
            except ValueError as exc:
                result = DeliveryResult(error=str(exc))
            else:
                result = (provider or MetaCloudWhatsAppProvider()).send(notification.recipient, parameters)
            if result.message_id:
                notification.status = OrderWhatsAppNotification.Status.SENT
                notification.provider_message_id = result.message_id
                notification.sent_at = timezone.now()
            elif result.uncertain:
                notification.status = OrderWhatsAppNotification.Status.UNKNOWN
            elif result.retryable and notification.attempts < MAX_ATTEMPTS:
                notification.status = OrderWhatsAppNotification.Status.PENDING
                notification.next_attempt_at = now + timedelta(seconds=30 * 2 ** (notification.attempts - 1))
            else:
                notification.status = OrderWhatsAppNotification.Status.FAILED
            notification.error = result.error
        notification.save(update_fields=["status", "provider_message_id", "sent_at", "next_attempt_at", "error"])
        logger.log(
            logging.INFO if notification.status == OrderWhatsAppNotification.Status.SENT else logging.WARNING,
            "WhatsApp order=%s status=%s attempt=%s",
            notification.order_id,
            notification.status,
            notification.attempts,
        )


def dispatch_order_whatsapp_notifications():
    close_old_connections()
    try:
        stale = OrderWhatsAppNotification.objects.filter(
            status=OrderWhatsAppNotification.Status.PROCESSING, claimed_at__lt=timezone.now() - CLAIM_TIMEOUT
        ).update(
            status=OrderWhatsAppNotification.Status.UNKNOWN,
            error="Worker interrupted; reconcile provider acceptance before resending.",
        )
        if stale:
            logger.error("WhatsApp: %s interrupted deliveries require reconciliation.", stale)
        ids = list(
            OrderWhatsAppNotification.objects.filter(
                status=OrderWhatsAppNotification.Status.PENDING, next_attempt_at__lte=timezone.now()
            )
            .order_by("next_attempt_at")
            .values_list("pk", flat=True)[:50]
        )
        for notification_id in ids:
            try:
                WhatsAppNotificationService.deliver(notification_id)
            except Exception as exc:
                # Unexpected bugs leave the claimed record non-retryable. Do not
                # log exception text: a provider implementation might expose tokens.
                logger.error(
                    "WhatsApp worker failed for notification %s (%s); inspect audit status.",
                    notification_id,
                    type(exc).__name__,
                )
    finally:
        close_old_connections()
