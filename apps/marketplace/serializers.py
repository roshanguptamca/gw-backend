from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import Campaign, Category, Coupon, Order, OrderCancellationRequest, OrderItem, Product, ProductImage, SellerProfile, Shop, ShopSettings
from .services import create_order_from_payload, create_seller_with_shop, generate_unique_slug

User = get_user_model()

IMAGE_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
PRODUCT_IMAGE_MAX_BYTES = 2 * 1024 * 1024
BANNER_IMAGE_MAX_BYTES = 5 * 1024 * 1024


def validate_image_upload(file, *, max_bytes):
    if not file:
        return file
    content_type = getattr(file, "content_type", "")
    if content_type not in IMAGE_CONTENT_TYPES:
        raise serializers.ValidationError("Only jpg, jpeg, png, and webp images are allowed.")
    if file.size > max_bytes:
        raise serializers.ValidationError(f"Image must be {max_bytes // (1024 * 1024)} MB or smaller.")
    return file


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

    class Meta:
        model = Shop
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "logo",
            "banner_image",
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
        read_only_fields = ["id", "slug", "is_approved", "created_at", "updated_at"]

    def validate_logo(self, value):
        return validate_image_upload(value, max_bytes=PRODUCT_IMAGE_MAX_BYTES)

    def validate_banner_image(self, value):
        return validate_image_upload(value, max_bytes=BANNER_IMAGE_MAX_BYTES)


class PublicProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ["id", "image", "alt_text", "sort_order"]


class ProductSerializer(serializers.ModelSerializer):
    category_detail = CategorySerializer(source="category", read_only=True)
    images = PublicProductImageSerializer(many=True, read_only=True)

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
            "images",
            "is_active",
            "is_approved",
            "is_featured",
            "preparation_time_minutes",
            "weight_grams",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "shop", "slug", "is_approved", "created_at", "updated_at"]

    def validate_image(self, value):
        return validate_image_upload(value, max_bytes=PRODUCT_IMAGE_MAX_BYTES)

    def validate_category(self, category):
        if category is None:
            return category
        request = self.context.get("request")
        seller_shop = getattr(getattr(request.user, "seller_profile", None), "shop", None) if request else None
        if seller_shop and category.shop_id not in {None, seller_shop.id}:
            raise serializers.ValidationError("Category does not belong to your shop.")
        return category

    def create(self, validated_data):
        shop = self.context["request"].user.seller_profile.shop
        validated_data["shop"] = shop
        validated_data["slug"] = generate_unique_slug(Product, validated_data["name"], shop=shop)
        validated_data["is_approved"] = False
        return super().create(validated_data)

    def update(self, instance, validated_data):
        if "name" in validated_data and validated_data["name"] != instance.name:
            validated_data["slug"] = generate_unique_slug(Product, validated_data["name"], shop=instance.shop)
            validated_data["is_approved"] = False
        return super().update(instance, validated_data)


class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ["id", "product", "image", "alt_text", "sort_order"]
        read_only_fields = ["id", "product"]

    def validate_image(self, value):
        return validate_image_upload(value, max_bytes=PRODUCT_IMAGE_MAX_BYTES)


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
    delivery_zone = serializers.ChoiceField(choices=Order.DELIVERY_ZONE_CHOICES, required=False, allow_blank=True, default="")
    payment_method = serializers.ChoiceField(choices=Order.PAYMENT_METHOD_CHOICES, default="cash")
    customer_note = serializers.CharField(required=False, allow_blank=True)
    coupon_code = serializers.CharField(required=False, allow_blank=True)
    items = serializers.ListField(child=serializers.DictField(), min_length=1)
    terms_accepted = serializers.BooleanField()

    def validate_terms_accepted(self, value):
        if not value:
            raise serializers.ValidationError(
                "You must accept the Terms & Conditions to place an order."
            )
        return value

    def validate_items(self, items):
        for item in items:
            if "product_id" not in item or "quantity" not in item:
                raise serializers.ValidationError("Each item needs product_id and quantity.")
        return items

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
        return validate_image_upload(value, max_bytes=BANNER_IMAGE_MAX_BYTES)

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
            "logo",
            "banner_image",
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
