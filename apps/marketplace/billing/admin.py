from django.contrib import admin

from .models import Invoice, InvoiceItem


class InvoiceItemInline(admin.TabularInline):
    model = InvoiceItem
    extra = 0
    can_delete = False
    readonly_fields = [field.name for field in InvoiceItem._meta.fields]

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ["invoice_number", "order", "shop", "customer", "issue_date", "total_inc_vat", "status"]
    search_fields = ["invoice_number", "order_number", "customer_snapshot__email"]
    list_filter = ["shop", "issue_date", "status"]
    readonly_fields = [field.name for field in Invoice._meta.fields]
    inlines = [InvoiceItemInline]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
