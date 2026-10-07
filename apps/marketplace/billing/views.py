from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404

from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.marketplace.models import Order

from .models import Invoice
from .pdf_service import invoice_pdf
from .serializers import InvoiceSerializer


class InvoicePDFRenderer(JSONRenderer):
    """Negotiate PDF downloads while retaining structured DRF error responses."""

    media_type = "application/pdf"
    format = "pdf"


def authorized_orders(user):
    orders = Order.objects.all()
    if user.is_superuser:
        return orders
    permissions = Q(customer=user)
    profile = getattr(user, "seller_profile", None)
    if profile and profile.is_active:
        permissions |= Q(shop__owner=user) | Q(invoices__shop__owner=user)
    return orders.filter(permissions).distinct()


def authorized_invoices(user):
    invoices = Invoice.objects.all()
    if user.is_superuser:
        return invoices
    permissions = Q(order__customer=user)
    profile = getattr(user, "seller_profile", None)
    if profile and profile.is_active:
        permissions |= Q(shop__owner=user)
    return invoices.filter(permissions)


class OrderInvoiceListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, order_id):
        order = get_object_or_404(authorized_orders(request.user), pk=order_id)
        invoices = authorized_invoices(request.user).filter(order=order).prefetch_related("items")
        return Response(InvoiceSerializer(invoices, many=True).data)


class InvoiceViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = InvoiceSerializer
    pagination_class = None

    def get_queryset(self):
        return authorized_invoices(self.request.user).prefetch_related("items")

    @action(detail=True, methods=["get"], renderer_classes=[InvoicePDFRenderer, JSONRenderer])
    def pdf(self, request, pk=None):
        invoice = self.get_object()
        response = HttpResponse(invoice_pdf(invoice), content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{invoice.invoice_number}.pdf"'
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response
