"""Optional, fail-closed Twilio WhatsApp notification for marketplace sellers.

Only explicitly allowlisted shops receive messages. WhatsApp is NEVER required
for checkout and is never used to send customer-facing marketing messages.
The approved Twilio Content Template must use five ordered variables:
  {{1}} order number, {{2}} items, {{3}} total,
  {{4}} pickup/delivery information, {{5}} customer name.
"""
import json
import logging
import re

from django.conf import settings
from django.db import close_old_connections

logger = logging.getLogger(__name__)
_E164 = re.compile(r"^\+[1-9]\d{7,14}$")
_CONTENT_SID = re.compile(r"^HX[a-fA-F0-9]{32}$")


def notification_config(order):
    """Return recipient, sender, template and credentials, or None.

    No implicit opt-in: the global switch, shop slug allowlist and seller
    number all must be configured. An allowlisted shop can be removed without
    code or data changes. Do not log tokens or phone numbers.
    """
    if not getattr(settings, "MARKETPLACE_SELLER_WHATSAPP_ENABLED", False):
        return None
    allowed = {
        value.strip()
        for value in getattr(settings, "MARKETPLACE_SELLER_WHATSAPP_SHOPS", "").split(",")
        if value.strip()
    }
    if order.shop.slug not in allowed:
        return None
    shop_settings = getattr(order.shop, "settings", None)
    recipient = (getattr(shop_settings, "whatsapp_number", "") or "").strip().replace(" ", "")
    sender = (getattr(settings, "TWILIO_WHATSAPP_FROM", "") or "").strip()
    sid = (getattr(settings, "MARKETPLACE_WHATSAPP_CONTENT_SID", "") or "").strip()
    account_sid = (getattr(settings, "TWILIO_ACCOUNT_SID", "") or "").strip()
    token = (getattr(settings, "TWILIO_AUTH_TOKEN", "") or "").strip()
    if not (_E164.fullmatch(recipient) and _E164.fullmatch(sender)):
        logger.warning("Marketplace WhatsApp not configured with E.164 numbers for shop %s", order.shop_id)
        return None
    if not (_CONTENT_SID.fullmatch(sid) and account_sid.startswith("AC") and token):
        logger.warning("Marketplace WhatsApp missing valid template or credentials for shop %s", order.shop_id)
        return None
    return recipient, sender, sid, account_sid, token


def template_variables(order):
    snapshot = order.fulfillment_snapshot or {}
    currency = snapshot.get("currency") or "EUR"
    items = "; ".join(f"{item.quantity} x {item.product_name}" for item in order.items.all())
    details = (
        f"Pickup {snapshot.get('pickup_date') or ''} {snapshot.get('pickup_time') or ''}"
        if order.order_type == "pickup"
        else "Delivery"
    )
    # Limit template variable sizes; no buyer phone/email sent to third party.
    return {
        "1": str(order.order_number)[:80],
        "2": (items or "Order items")[:900],
        "3": f"{order.total} {currency}"[:80],
        "4": details.strip()[:160],
        "5": (order.customer_name or "Customer")[:120],
    }


def send_seller_whatsapp(order_id):
    """Best-effort delivery from an isolated daemon thread, after DB commit.

    A successful Twilio API call only means accepted by Twilio, not delivered.
    An explicit retry must be a manual operation: automatic retries after
    ambiguous network failures could duplicate order alerts.
    """
    from .models import Order

    close_old_connections()
    try:
        order = (
            Order.objects.select_related("shop__settings")
            .prefetch_related("items")
            .get(pk=order_id)
        )
        config = notification_config(order)
        if config is None:
            return False
        recipient, sender, sid, account_sid, token = config
        from twilio.rest import Client

        message = Client(account_sid, token).messages.create(
            from_=f"whatsapp:{sender}",
            to=f"whatsapp:{recipient}",
            content_sid=sid,
            content_variables=json.dumps(template_variables(order)),
        )
        logger.info(
            "Marketplace WhatsApp accepted by Twilio: order_id=%s shop_id=%s message_sid=%s",
            order.pk, order.shop_id, message.sid,
        )
        return True
    except Exception:
        logger.exception("Marketplace WhatsApp failed for order_id=%s; checkout unaffected", order_id)
        return False
    finally:
        close_old_connections()
