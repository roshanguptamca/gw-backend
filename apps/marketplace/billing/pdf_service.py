import base64
import logging
from io import BytesIO
from urllib.parse import urlsplit

from django.db import transaction
from django.template.loader import render_to_string

import requests
from PIL import Image

from .models import Invoice, InvoicePDF
from .vat_service import vat_summary

logger = logging.getLogger(__name__)


def snapshot_logo(shop):
    """Only fetch uploaded Cloudinary logos, never arbitrary seller-supplied URLs."""
    url = shop.logo_url
    if not url:
        return ""
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != "res.cloudinary.com" or parsed.username or parsed.port:
        logger.warning("Unsupported invoice logo URL for shop %s", shop.pk)
        return ""
    try:
        with requests.get(url, timeout=(3, 5), allow_redirects=False, stream=True) as response:
            response.raise_for_status()
            if response.status_code != 200:
                raise ValueError("Invoice logo response is not 200.")
            content = bytearray()
            for chunk in response.iter_content(65536):
                content.extend(chunk)
                if len(content) > 2 * 1024 * 1024:
                    raise ValueError("Invoice logo exceeds 2 MB.")
        with Image.open(BytesIO(content)) as image:
            image.thumbnail((600, 600))
            output = BytesIO()
            image.convert("RGBA").save(output, format="PNG")
        return "data:image/png;base64," + base64.b64encode(output.getvalue()).decode("ascii")
    except (requests.RequestException, OSError, ValueError, Image.DecompressionBombError):
        logger.exception("Unable to snapshot invoice logo for shop %s; using seller name", shop.pk)
        return ""


def invoice_html(invoice):
    return render_to_string(
        "marketplace/billing/invoice.html",
        {
            "invoice": invoice,
            "seller": invoice.seller_snapshot,
            "customer": invoice.customer_snapshot,
            "items": invoice.items.all(),
            "vat_summary": vat_summary(invoice),
        },
    )


def _private_url_fetcher(url):
    if not url.startswith("data:image/png;base64,"):
        raise ValueError("Invoice rendering only permits embedded logo images.")
    from weasyprint import default_url_fetcher

    return default_url_fetcher(url)


@transaction.atomic
def invoice_pdf(invoice):
    invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)
    document = InvoicePDF.objects.filter(invoice=invoice).first()
    if document:
        return bytes(document.content)
    from weasyprint import HTML

    content = HTML(string=invoice_html(invoice), url_fetcher=_private_url_fetcher).write_pdf()
    InvoicePDF.objects.create(invoice=invoice, content=content)
    return content
