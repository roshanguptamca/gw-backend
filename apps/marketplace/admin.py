from django.contrib import admin

from .models import Campaign, Category, Coupon, Order, OrderItem, Product, ProductImage, SellerProfile, Shop, ShopSettings


@admin.action(description="Approve selected shops")
def approve_shops(modeladmin, request, queryset):
    queryset.update(is_approved=True, is_active=True)


@admin.action(description="Deactivate selected shops")
def deactivate_shops(modeladmin, request, queryset):
    queryset.update(is_active=False)


@admin.action(description="Approve selected products")
def approve_products(modeladmin, request, queryset):
    queryset.update(is_approved=True)


@admin.action(description="Reject selected products")
def reject_products(modeladmin, request, queryset):
    queryset.update(is_approved=False)


@admin.action(description="Activate selected sellers")
def activate_sellers(modeladmin, request, queryset):
    queryset.update(is_active=True)
    for seller in queryset.select_related("user"):
        seller.user.is_active = True
        seller.user.save(update_fields=["is_active"])


@admin.action(description="Deactivate selected sellers")
def deactivate_sellers(modeladmin, request, queryset):
    queryset.update(is_active=False)
    for seller in queryset.select_related("user"):
        seller.user.is_active = False
        seller.user.save(update_fields=["is_active"])


@admin.register(SellerProfile)
class SellerProfileAdmin(admin.ModelAdmin):
    list_display = ["business_name", "user", "city", "is_active", "onboarding_completed", "created_at"]
    list_filter = ["is_active", "onboarding_completed", "city"]
    search_fields = ["business_name", "user__email", "phone", "city"]
    actions = [activate_sellers, deactivate_sellers]


@admin.register(Shop)
class ShopAdmin(admin.ModelAdmin):
    list_display = ["name", "owner", "city", "is_active", "is_approved", "created_at"]
    list_filter = ["is_active", "is_approved", "pickup_available", "delivery_available", "city"]
    search_fields = ["name", "owner__email", "slug"]
    prepopulated_fields = {"slug": ("name",)}
    actions = [approve_shops, deactivate_shops]


@admin.register(ShopSettings)
class ShopSettingsAdmin(admin.ModelAdmin):
    list_display = ["shop", "currency", "min_order_amount", "delivery_fee", "order_acceptance_mode"]
    list_filter = ["currency", "order_acceptance_mode"]


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "shop", "slug", "is_global", "is_active"]
    list_filter = ["is_global", "is_active"]
    search_fields = ["name", "slug", "shop__name"]


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 0


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ["name", "shop", "price", "stock_quantity", "is_active", "is_approved", "is_featured"]
    list_filter = ["is_active", "is_approved", "is_featured", "shop"]
    search_fields = ["name", "sku", "shop__name"]
    prepopulated_fields = {"slug": ("name",)}
    inlines = [ProductImageInline]
    actions = [approve_products, reject_products]


@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    list_display = ["product", "alt_text", "sort_order"]
    search_fields = ["product__name", "alt_text"]


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ["product", "product_name", "unit_price", "quantity", "line_total"]


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ["order_number", "shop", "customer_name", "status", "payment_status", "total", "created_at"]
    list_filter = ["status", "payment_status", "order_type", "payment_method", "shop"]
    search_fields = ["order_number", "customer_name", "customer_email", "customer_phone", "shop__name"]
    inlines = [OrderItemInline]


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ["order", "product_name", "quantity", "unit_price", "line_total"]


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = ["code", "shop", "discount_type", "discount_value", "active", "used_count"]
    list_filter = ["active", "discount_type", "shop"]
    search_fields = ["code", "shop__name"]


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ["title", "shop", "active", "starts_at", "ends_at", "featured_product"]
    list_filter = ["active", "shop"]
    search_fields = ["title", "shop__name"]
