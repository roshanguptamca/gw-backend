import re

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Max

from rest_framework import serializers

from .cloudinary_service import (
    PRODUCT_IMAGE_MAX_BYTES,
    SHOP_BANNER_MAX_BYTES,
    SHOP_LOGO_MAX_BYTES,
    upload_product_gallery_image,
    upload_product_main_image,
    upload_shop_banner,
    upload_shop_logo,
    validate_image_file,
)
from .models import (
    Campaign,
    Category,
    Coupon,
    Order,
    OrderCancellationRequest,
    OrderItem,
    Product,
    ProductImage,
    SellerProfile,
    Shop,
    ShopSettings,
)
from .services import create_order_from_payload, create_seller_with_shop, generate_unique_slug

User = get_user_model()


def validate_image_upload(file, *, max_bytes):
    try:
        return validate_image_file(file, max_bytes=max_bytes)
    except DjangoValidationError as exc:
        raise serializers.ValidationError(exc.messages) from exc


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "shop", "name", "slug", "is_global", "is_active"]
        read_only_fields = ["id", "shop", "slug", "is_global"]


class ShopSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShopSettings
        fields = [
            "currency",
            "min_order_amount",
            "delivery_fee",
            "local_delivery_fee",
            "international_delivery_fee",
            "free_delivery_above",
            "delivery_notes",
            "order_acceptance_mode",
            "whatsapp_number",
            "bank_transfer_instructions",
        ]


class ShopSerializer(serializers.ModelSerializer):
    settings = ShopSettingsSerializer(read_only=True)
    product_count = serializers.IntegerField(read_only=True)
    logo = serializers.ImageField(write_only=True, required=False)
    banner_image = serializers.ImageField(write_only=True, required=False)

    class Meta:
        model = Shop
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "logo",
            "logo_public_id",
            "logo_url",
            "banner_image",
            "banner_public_id",
            "banner_url",
            "city",
            "delivery_area",
            "pickup_available",
            "delivery_available",
            "is_active",
            "is_approved",
            "settings",
            "product_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "slug",
            "logo_public_id",
            "logo_url",
            "banner_public_id",
            "banner_url",
            "is_approved",
            "created_at",
            "updated_at",
        ]

    def validate_logo(self, value):
        return validate_image_upload(value, max_bytes=SHOP_LOGO_MAX_BYTES)

    def validate_banner_image(self, value):
        return validate_image_upload(value, max_bytes=SHOP_BANNER_MAX_BYTES)

    @transaction.atomic
    def update(self, instance, validated_data):
        logo_file = validated_data.pop("logo", None)
        banner_file = validated_data.pop("banner_image", None)
        shop = super().update(instance, validated_data)
        try:
            if logo_file:
                upload_shop_logo(shop, logo_file)
            if banner_file:
                upload_shop_banner(shop, banner_file)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"images": exc.messages}) from exc
        return shop


class PublicProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ["id", "image_url", "alt_text", "sort_order"]


class ProductSerializer(serializers.ModelSerializer):
    category_detail = CategorySerializer(source="category", read_only=True)
    images = PublicProductImageSerializer(many=True, read_only=True)
    image = serializers.ImageField(write_only=True, required=False, allow_null=True)
    image_url = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Product
        fields = [
            "id",
            "shop",
            "category",
            "category_detail",
            "name",
            "slug",
            "description",
            "ingredients",
            "allergens",
            "price",
            "compare_at_price",
            "stock_quantity",
            "sku",
            "image",
            "image_public_id",
            "image_url",
            "external_image_url",
            "images",
            "is_active",
            "is_approved",
            "is_featured",
            "preparation_time_minutes",
            "weight_grams",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "shop",
            "slug",
            "image_public_id",
            "image_url",
            "is_approved",
            "created_at",
            "updated_at",
        ]

    def get_image_url(self, obj):
        return obj.image_url or ""

    def validate_image(self, value):
        return validate_image_upload(value, max_bytes=PRODUCT_IMAGE_MAX_BYTES)

    def validate_sku(self, value):
        if value in (None, ""):
            return None
        value = value.strip().upper()
        if not re.fullmatch(r"[A-Z0-9_-]+", value):
            raise serializers.ValidationError("SKU may contain only letters, numbers, hyphens, and underscores.")
        return value

    def validate(self, attrs):
        image = attrs.get("image")
        sku = attrs.get("sku", getattr(self.instance, "sku", None))
        if image and not sku:
            raise serializers.ValidationError({"sku": "A SKU is required before uploading product images."})
        if (
            self.instance
            and "sku" in attrs
            and attrs["sku"] != self.instance.sku
            and (self.instance.image_public_id or self.instance.images.exclude(image_public_id="").exists())
        ):
            raise serializers.ValidationError(
                {"sku": "SKU cannot be changed after Cloudinary images have been uploaded."}
            )
        return attrs

    def validate_category(self, category):
        if category is None:
            return category
        request = self.context.get("request")
        seller_shop = getattr(getattr(request.user, "seller_profile", None), "shop", None) if request else None
        if seller_shop and category.shop_id not in {None, seller_shop.id}:
            raise serializers.ValidationError("Category does not belong to your shop.")
        return category

    @transaction.atomic
    def create(self, validated_data):
        image_file = validated_data.pop("image", None)
        shop = self.context["request"].user.seller_profile.shop
        validated_data["shop"] = shop
        validated_data["slug"] = generate_unique_slug(Product, validated_data["name"], shop=shop)
        validated_data["is_approved"] = False
        product = super().create(validated_data)
        if image_file:
            try:
                upload_product_main_image(product, image_file)
            except DjangoValidationError as exc:
                raise serializers.ValidationError({"image": exc.messages}) from exc
        return product

    @transaction.atomic
    def update(self, instance, validated_data):
        image_file = validated_data.pop("image", None)
        if "name" in validated_data and validated_data["name"] != instance.name:
            validated_data["slug"] = generate_unique_slug(Product, validated_data["name"], shop=instance.shop)
            validated_data["is_approved"] = False
        product = super().update(instance, validated_data)
        if image_file:
            try:
                upload_product_main_image(product, image_file)
            except DjangoValidationError as exc:
                raise serializers.ValidationError({"image": exc.messages}) from exc
        return product


class ProductImageSerializer(serializers.ModelSerializer):
    image = serializers.ImageField(write_only=True, required=True)

    class Meta:
        model = ProductImage
        fields = ["id", "product", "image", "image_public_id", "image_url", "alt_text", "sort_order"]
        read_only_fields = ["id", "product", "image_public_id", "image_url"]

    def validate_image(self, value):
        return validate_image_upload(value, max_bytes=PRODUCT_IMAGE_MAX_BYTES)

    def create(self, validated_data):
        product = validated_data.pop("product")
        image_file = validated_data.pop("image")
        sort_order = validated_data.get("sort_order")
        if sort_order is None:
            highest = product.images.aggregate(value=Max("sort_order"))["value"]
            sort_order = 0 if highest is None else highest + 1
        try:
            gallery_image = upload_product_gallery_image(product, image_file, sort_order)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"image": exc.messages}) from exc
        gallery_image.alt_text = validated_data.get("alt_text", "")
        gallery_image.save(update_fields=["alt_text"])
        return gallery_image


class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = ["id", "product", "product_name", "unit_price", "quantity", "line_total"]


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    shop_name = serializers.CharField(source="shop.name", read_only=True)
    shop_slug = serializers.CharField(source="shop.slug", read_only=True)

    class Meta:
        model = Order
        fields = [
            "id",
            "shop",
            "shop_name",
            "shop_slug",
            "customer",
            "order_number",
            "customer_name",
            "customer_email",
            "customer_phone",
            "delivery_address",
            "order_type",
            "delivery_zone",
            "status",
            "payment_method",
            "payment_status",
            "subtotal",
            "discount_total",
            "delivery_fee",
            "total",
            "customer_note",
            "seller_note",
            "terms_accepted",
            "items",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "shop",
            "customer",
            "order_number",
            "subtotal",
            "discount_total",
            "delivery_fee",
            "total",
            "created_at",
            "updated_at",
        ]


class OrderCreateSerializer(serializers.Serializer):
    shop_id = serializers.IntegerField()
    customer_name = serializers.CharField(max_length=150)
    customer_email = serializers.EmailField(required=False, allow_blank=True)
    customer_phone = serializers.CharField(max_length=30)
    delivery_address = serializers.CharField(required=False, allow_blank=True)
    order_type = serializers.ChoiceField(choices=Order.ORDER_TYPE_CHOICES, default="pickup")
    delivery_zone = serializers.ChoiceField(
        choices=Order.DELIVERY_ZONE_CHOICES, required=False, allow_blank=True, default=""
    )
    payment_method = serializers.ChoiceField(choices=Order.PAYMENT_METHOD_CHOICES, default="cash")
    customer_note = serializers.CharField(required=False, allow_blank=True)
    coupon_code = serializers.CharField(required=False, allow_blank=True)
    items = serializers.ListField(child=serializers.DictField(), min_length=1)
    terms_accepted = serializers.BooleanField()
    create_account = serializers.BooleanField(required=False, default=False)
    password = serializers.CharField(required=False, allow_blank=True, write_only=True)
    password_confirm = serializers.CharField(required=False, allow_blank=True, write_only=True)

    def validate_terms_accepted(self, value):
        if not value:
            raise serializers.ValidationError("You must accept the Terms & Conditions to place an order.")
        return value

    def validate_items(self, items):
        for item in items:
            if "product_id" not in item or "quantity" not in item:
                raise serializers.ValidationError("Each item needs product_id and quantity.")
        return items

    def validate(self, attrs):
        request = self.context["request"]
        user = getattr(request, "user", None)

        # Logged-in customers already have an account — ignore any create_account/password
        # fields that may have been sent and link the order straight to request.user.
        if user and user.is_authenticated:
            attrs["create_account"] = False
            return attrs

        if not attrs.get("create_account"):
            return attrs

        email = (attrs.get("customer_email") or "").strip()
        if not email:
            raise serializers.ValidationError({"customer_email": "Email is required to create an account."})

        password = attrs.get("password") or ""
        password_confirm = attrs.get("password_confirm") or ""
        if not password:
            raise serializers.ValidationError({"password": "Password is required to create an account."})
        if password != password_confirm:
            raise serializers.ValidationError({"password_confirm": "Passwords must match."})

        try:
            validate_password(password)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": list(exc.messages)})

        User = get_user_model()
        if User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError(
                {"customer_email": ("An account already exists with this email. Please log in to track this order.")}
            )

        return attrs

    def create(self, validated_data):
        return create_order_from_payload(validated_data, user=self.context["request"].user)


class CouponSerializer(serializers.ModelSerializer):
    class Meta:
        model = Coupon
        fields = [
            "id",
            "code",
            "discount_type",
            "discount_value",
            "min_order_amount",
            "usage_limit",
            "used_count",
            "active",
            "starts_at",
            "ends_at",
        ]
        read_only_fields = ["id", "used_count"]

    def validate_code(self, value):
        return value.strip().upper()


class CampaignSerializer(serializers.ModelSerializer):
    class Meta:
        model = Campaign
        fields = ["id", "title", "description", "banner_image", "starts_at", "ends_at", "active", "featured_product"]
        read_only_fields = ["id"]

    def validate_banner_image(self, value):
        return validate_image_upload(value, max_bytes=SHOP_BANNER_MAX_BYTES)

    def validate_featured_product(self, product):
        if product is None:
            return product
        shop = self.context["request"].user.seller_profile.shop
        if product.shop_id != shop.id:
            raise serializers.ValidationError("Featured product must belong to your shop.")
        return product


class SellerProfileSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source="user.email", read_only=True)
    first_name = serializers.CharField(source="user.first_name", read_only=True)
    last_name = serializers.CharField(source="user.last_name", read_only=True)
    shop = ShopSerializer(read_only=True)

    class Meta:
        model = SellerProfile
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "business_name",
            "phone",
            "city",
            "address",
            "is_active",
            "onboarding_completed",
            "shop",
            "created_at",
            "updated_at",
        ]


class OrderCancellationRequestSerializer(serializers.ModelSerializer):
    reason_display = serializers.CharField(source="get_reason_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    order_number = serializers.CharField(source="order.order_number", read_only=True)
    shop_name = serializers.CharField(source="shop.name", read_only=True)

    class Meta:
        model = OrderCancellationRequest
        fields = [
            "id",
            "order",
            "order_number",
            "shop",
            "shop_name",
            "reason",
            "reason_display",
            "message",
            "status",
            "status_display",
            "seller_note",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "order", "shop", "status", "seller_note", "created_at", "updated_at"]


class OrderCancellationCreateSerializer(serializers.Serializer):
    reason = serializers.ChoiceField(choices=OrderCancellationRequest.REASON_CHOICES)
    message = serializers.CharField(required=False, allow_blank=True, max_length=1000)


class SellerCancellationResponseSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=[
            (OrderCancellationRequest.STATUS_APPROVED, "Approved"),
            (OrderCancellationRequest.STATUS_REJECTED, "Rejected"),
        ]
    )
    seller_note = serializers.CharField(required=False, allow_blank=True, max_length=500)


class AdminSellerCreateSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8)
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    business_name = serializers.CharField(max_length=150)
    phone = serializers.CharField(max_length=30, required=False, allow_blank=True)
    city = serializers.CharField(max_length=100, required=False, allow_blank=True)
    address = serializers.CharField(required=False, allow_blank=True)

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists() or User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value.lower()

    def create(self, validated_data):
        first_name = validated_data.pop("first_name", "")
        last_name = validated_data.pop("last_name", "")
        user, profile, shop = create_seller_with_shop(
            created_by=self.context["request"].user,
            first_name=first_name,
            last_name=last_name,
            **validated_data,
        )
        return profile


class AdminSellerUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SellerProfile
        fields = ["business_name", "phone", "city", "address", "is_active", "onboarding_completed"]


class AdminProductApprovalSerializer(serializers.Serializer):
    is_approved = serializers.BooleanField(default=True)


class PublicShopSerializer(ShopSerializer):
    class Meta(ShopSerializer.Meta):
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "logo_url",
            "banner_url",
            "city",
            "delivery_area",
            "pickup_available",
            "delivery_available",
            "settings",
            "product_count",
        ]
        read_only_fields = fields


class PublicProductSerializer(ProductSerializer):
    shop = PublicShopSerializer(read_only=True)

    class Meta(ProductSerializer.Meta):
        read_only_fields = ProductSerializer.Meta.fields


class BuyerOrderSerializer(OrderSerializer):
    """OrderSerializer extended with cancellation request details for buyers."""

    cancellation_request = OrderCancellationRequestSerializer(read_only=True)

    class Meta(OrderSerializer.Meta):
        fields = OrderSerializer.Meta.fields + ["cancellation_request"]


class MarketplaceSearchResultSerializer(serializers.Serializer):
    """Used internally; actual response built directly in MarketplaceSearchView."""

    shops = PublicShopSerializer(many=True, read_only=True)
    products = PublicProductSerializer(many=True, read_only=True)
    total_shops = serializers.IntegerField(read_only=True)
    total_products = serializers.IntegerField(read_only=True)


class PublicCategorySerializer(serializers.ModelSerializer):
    product_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Category
        fields = ["id", "name", "slug", "is_global", "product_count"]
