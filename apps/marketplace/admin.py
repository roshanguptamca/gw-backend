from django import forms
from django.contrib import admin
from django.core.files.uploadedfile import UploadedFile
from django.utils.html import format_html

from .cloudinary_service import (
    delete_cloudinary_image,
    upload_product_gallery_image,
    upload_product_main_image,
    validate_image_file,
)
from .models import (
    Campaign,
    Category,
    Coupon,
    Order,
    OrderItem,
    Product,
    ProductImage,
    SellerProfile,
    Shop,
    ShopSettings,
)


def image_preview(image_url):
    if not image_url:
        return "No Cloudinary image"
    return format_html(
        '<a href="{}" target="_blank" rel="noopener">'
        '<img src="{}" alt="" style="width:80px;height:80px;object-fit:cover;border-radius:6px"></a>',
        image_url,
        image_url,
    )


class ProductAdminForm(forms.ModelForm):
    image = forms.ImageField(
        required=False,
        help_text="jpg, jpeg, png, or webp; maximum 2 MB. Uploaded directly to Cloudinary.",
    )

    class Meta:
        model = Product
        fields = "__all__"

    def clean_image(self):
        image_file = self.cleaned_data.get("image")
        if isinstance(image_file, UploadedFile):
            validate_image_file(image_file)
        return image_file

    def clean(self):
        cleaned_data = super().clean()
        sku = cleaned_data.get("sku")
        image_file = cleaned_data.get("image")
        if isinstance(image_file, UploadedFile) and not sku:
            self.add_error("sku", "A SKU is required before uploading product images.")

        if self.instance.pk and sku != self.instance.sku:
            has_cloudinary_images = (
                bool(self.instance.image_public_id) or self.instance.images.exclude(image_public_id="").exists()
            )
            if has_cloudinary_images:
                self.add_error("sku", "SKU cannot be changed after Cloudinary images have been uploaded.")
        return cleaned_data


class ProductImageAdminForm(forms.ModelForm):
    image = forms.ImageField(
        required=False,
        help_text="jpg, jpeg, png, or webp; maximum 2 MB. Uploaded directly to Cloudinary.",
    )

    class Meta:
        model = ProductImage
        fields = "__all__"

    def clean_image(self):
        image_file = self.cleaned_data.get("image")
        if isinstance(image_file, UploadedFile):
            validate_image_file(image_file)
        elif not self.instance.pk:
            raise forms.ValidationError("An image file is required.")
        return image_file

    def clean(self):
        cleaned_data = super().clean()
        product = cleaned_data.get("product")
        if product is None and self.instance.product_id:
            product = self.instance.product
        sort_order = cleaned_data.get("sort_order")
        if product is not None and sort_order is not None:
            matching_image = ProductImage.objects.filter(product=product, sort_order=sort_order)
            if self.instance.pk:
                matching_image = matching_image.exclude(pk=self.instance.pk)
            if matching_image.exists():
                self.add_error("sort_order", "This product already has an image at that sort order.")
        return cleaned_data


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
    form = ProductImageAdminForm
    extra = 0
    fields = ["image", "image_preview", "image_url", "image_public_id", "alt_text", "sort_order"]
    readonly_fields = ["image_preview", "image_url", "image_public_id"]

    @admin.display(description="Cloudinary preview")
    def image_preview(self, obj):
        return image_preview(obj.image_url)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    form = ProductAdminForm
    list_display = [
        "shop",
        "name",
        "sku",
        "category",
        "price",
        "stock_quantity",
        "cloudinary_image",
        "is_active",
        "is_approved",
        "is_featured",
    ]
    list_filter = [
        ("shop", admin.RelatedOnlyFieldListFilter),
        "is_active",
        "is_approved",
        "is_featured",
        "category",
    ]
    list_select_related = ["shop", "category"]
    ordering = ["shop__name", "name"]
    list_per_page = 50
    show_full_result_count = False
    search_fields = ["name", "=sku", "shop__name", "shop__owner__email"]
    autocomplete_fields = ["shop", "category"]
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ["cloudinary_image", "image_url", "image_public_id"]
    inlines = [ProductImageInline]
    actions = [approve_products, reject_products]

    @admin.display(description="Cloudinary image")
    def cloudinary_image(self, obj):
        return image_preview(obj.image_url)

    def save_model(self, request, obj, form, change):
        image_file = form.cleaned_data.get("image")
        # The model ImageField is retained only for schema compatibility. Clear
        # it before Django saves so the upload never reaches local media storage.
        obj.image = None
        super().save_model(request, obj, form, change)
        if isinstance(image_file, UploadedFile):
            upload_product_main_image(obj, image_file)

    def save_formset(self, request, form, formset, change):
        if formset.model is not ProductImage:
            return super().save_formset(request, form, formset, change)

        upload_by_instance = {
            id(inline_form.instance): inline_form.cleaned_data.get("image")
            for inline_form in formset.forms
            if hasattr(inline_form, "cleaned_data") and not inline_form.cleaned_data.get("DELETE")
        }
        instances = formset.save(commit=False)
        for deleted_image in formset.deleted_objects:
            delete_cloudinary_image(deleted_image.image_public_id)
            deleted_image.delete()

        for gallery_image in instances:
            image_file = upload_by_instance.get(id(gallery_image))
            gallery_image.image = None
            gallery_image.save()
            if isinstance(image_file, UploadedFile):
                upload_product_gallery_image(
                    gallery_image.product,
                    image_file,
                    gallery_image.sort_order,
                )
        formset.save_m2m()

    def delete_model(self, request, obj):
        delete_cloudinary_image(obj.image_public_id)
        for gallery_image in obj.images.all():
            delete_cloudinary_image(gallery_image.image_public_id)
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        for product in queryset.prefetch_related("images"):
            delete_cloudinary_image(product.image_public_id)
            for gallery_image in product.images.all():
                delete_cloudinary_image(gallery_image.image_public_id)
        super().delete_queryset(request, queryset)


@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    form = ProductImageAdminForm
    list_display = ["product", "cloudinary_image", "image_url", "alt_text", "sort_order"]
    search_fields = ["product__name", "alt_text"]
    readonly_fields = ["cloudinary_image", "image_url", "image_public_id"]

    @admin.display(description="Cloudinary image")
    def cloudinary_image(self, obj):
        return image_preview(obj.image_url)

    def save_model(self, request, obj, form, change):
        image_file = form.cleaned_data.get("image")
        obj.image = None
        super().save_model(request, obj, form, change)
        if isinstance(image_file, UploadedFile):
            upload_product_gallery_image(obj.product, image_file, obj.sort_order)

    def delete_model(self, request, obj):
        delete_cloudinary_image(obj.image_public_id)
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        for gallery_image in queryset:
            delete_cloudinary_image(gallery_image.image_public_id)
        super().delete_queryset(request, queryset)


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
