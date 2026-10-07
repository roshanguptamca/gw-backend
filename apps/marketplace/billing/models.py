from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class ImmutableQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError("Issued invoice documents cannot be changed.")

    def delete(self):
        raise ValidationError("Issued invoice documents cannot be deleted.")

    def bulk_update(self, objs, fields, batch_size=None):
        raise ValidationError("Issued invoice documents cannot be changed.")


class ImmutableDocument(models.Model):
    objects = ImmutableQuerySet.as_manager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("Issued invoice documents cannot be changed.")
        kwargs["force_insert"] = True
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Issued invoice documents cannot be deleted.")


class Invoice(ImmutableDocument):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    invoice_number = models.CharField(max_length=80, unique=True)
    order = models.ForeignKey("marketplace.Order", on_delete=models.PROTECT, related_name="invoices")
    shop = models.ForeignKey("marketplace.Shop", on_delete=models.PROTECT, related_name="invoices")
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    status = models.CharField(max_length=20, default="issued", editable=False)
    issue_date = models.DateField()
    order_number = models.CharField(max_length=30)
    order_date = models.DateTimeField()
    currency = models.CharField(max_length=10)
    subtotal_ex_vat = models.DecimalField(max_digits=12, decimal_places=2)
    vat_total = models.DecimalField(max_digits=12, decimal_places=2)
    total_inc_vat = models.DecimalField(max_digits=12, decimal_places=2)
    discount_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    delivery_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    seller_snapshot = models.JSONField()
    customer_snapshot = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["issue_date", "invoice_number"]
        constraints = [models.UniqueConstraint(fields=["order", "shop"], name="unique_invoice_order_shop")]

    def __str__(self):
        return self.invoice_number


class InvoiceItem(ImmutableDocument):
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="items")
    order_item = models.ForeignKey("marketplace.OrderItem", on_delete=models.SET_NULL, null=True, blank=True)
    description = models.CharField(max_length=255)
    sku = models.CharField(max_length=80, blank=True)
    kind = models.CharField(max_length=20, default="product")
    quantity = models.PositiveIntegerField()
    unit_price_inc_vat = models.DecimalField(max_digits=12, decimal_places=2)
    vat_rate = models.DecimalField(max_digits=5, decimal_places=2)
    unit_price_ex_vat = models.DecimalField(max_digits=12, decimal_places=6)
    discount_inc_vat = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    line_total_ex_vat = models.DecimalField(max_digits=12, decimal_places=2)
    vat_amount = models.DecimalField(max_digits=12, decimal_places=2)
    line_total_inc_vat = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        ordering = ["id"]


class InvoiceSequence(models.Model):
    shop = models.ForeignKey("marketplace.Shop", on_delete=models.PROTECT)
    year = models.PositiveIntegerField()
    last_number = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["shop", "year"], name="unique_invoice_sequence_shop_year")]


class InvoicePDF(ImmutableDocument):
    invoice = models.OneToOneField(Invoice, on_delete=models.PROTECT, related_name="document")
    content = models.BinaryField()
    created_at = models.DateTimeField(auto_now_add=True)
