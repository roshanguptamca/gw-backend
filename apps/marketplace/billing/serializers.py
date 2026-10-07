from rest_framework import serializers

from .models import Invoice, InvoiceItem
from .vat_service import vat_summary


class InvoiceItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = InvoiceItem
        fields = [
            "id",
            "description",
            "sku",
            "kind",
            "quantity",
            "unit_price_inc_vat",
            "vat_rate",
            "unit_price_ex_vat",
            "discount_inc_vat",
            "line_total_ex_vat",
            "vat_amount",
            "line_total_inc_vat",
        ]
        read_only_fields = fields


class InvoiceSerializer(serializers.ModelSerializer):
    shop_name = serializers.CharField(source="seller_snapshot.shop_name", read_only=True)
    items = InvoiceItemSerializer(many=True, read_only=True)
    vat_summary = serializers.SerializerMethodField()

    class Meta:
        model = Invoice
        fields = [
            "id",
            "invoice_number",
            "order",
            "order_number",
            "shop",
            "shop_name",
            "issue_date",
            "status",
            "currency",
            "subtotal_ex_vat",
            "vat_total",
            "total_inc_vat",
            "discount_total",
            "delivery_total",
            "items",
            "vat_summary",
        ]
        read_only_fields = fields

    def get_vat_summary(self, invoice):
        return [{key: str(value) for key, value in row.items()} for row in vat_summary(invoice)]
