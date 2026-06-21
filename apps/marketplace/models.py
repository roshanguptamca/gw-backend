from decimal import Decimal

from django.conf import settings
from django.db import models


class SellerProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="seller_profile")
    business_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=30, blank=True)
    city = models.CharField(max_length=100, blank=True)
    address = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    onboarding_completed = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_sellers",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.business_name


class Shop(models.Model):
    owner = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="shop")
    seller_profile = models.OneToOneField(SellerProfile, on_delete=models.CASCADE, related_name="shop")
    name = models.CharField(max_length=150)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    logo = models.ImageField(upload_to="shops/logos/", blank=True, null=True)
    banner_image = models.ImageField(upload_to="shops/banners/", blank=True, null=True)
    city = models.CharField(max_length=100, blank=True)
    delivery_area = models.TextField(blank=True)
    pickup_available = models.BooleanField(default=True)
    delivery_available = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    is_approved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["is_active", "is_approved"]),
            models.Index(fields=["slug"]),
        ]

    def __str__(self):
        return self.name


class ShopSettings(models.Model):
    ORDER_ACCEPTANCE_MANUAL = "manual"
    ORDER_ACCEPTANCE_AUTO = "auto"
    ORDER_ACCEPTANCE_CHOICES = [
        (ORDER_ACCEPTANCE_MANUAL, "Manual"),
        (ORDER_ACCEPTANCE_AUTO, "Automatic"),
    ]

    shop = models.OneToOneField(Shop, on_delete=models.CASCADE, related_name="settings")
    currency = models.CharField(max_length=10, default="EUR")
    min_order_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    delivery_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    free_delivery_above = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    order_acceptance_mode = models.CharField(
        max_length=30,
        choices=ORDER_ACCEPTANCE_CHOICES,
        default=ORDER_ACCEPTANCE_MANUAL,
    )
    local_delivery_fee = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("5.00"))
    international_delivery_fee = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("10.00"))
    delivery_notes = models.TextField(blank=True)
    whatsapp_number = models.CharField(max_length=30, blank=True)
    bank_transfer_instructions = models.TextField(blank=True)

    def __str__(self):
        return f"Settings for {self.shop}"


class Category(models.Model):
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name="categories", null=True, blank=True)
    name = models.CharField(max_length=120)
    slug = models.SlugField()
    is_global = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["shop", "slug"], name="unique_marketplace_category_per_shop"),
            models.UniqueConstraint(fields=["slug"], condition=models.Q(shop__isnull=True), name="unique_global_category"),
        ]
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name


class Product(models.Model):
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name="products")
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name="products")
    name = models.CharField(max_length=150)
    slug = models.SlugField()
    description = models.TextField(blank=True)
    ingredients = models.TextField(blank=True)
    allergens = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    compare_at_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    stock_quantity = models.PositiveIntegerField(default=0)
    sku = models.CharField(max_length=80, blank=True)
    image = models.ImageField(upload_to="products/main/", blank=True, null=True)
    is_active = models.BooleanField(default=True)
    is_approved = models.BooleanField(default=False)
    is_featured = models.BooleanField(default=False)
    preparation_time_minutes = models.PositiveIntegerField(default=0)
    weight_grams = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["shop", "slug"], name="unique_marketplace_product_per_shop"),
        ]
        indexes = [
            models.Index(fields=["shop", "is_active", "is_approved"]),
            models.Index(fields=["shop", "slug"]),
        ]

    def __str__(self):
        return self.name


class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="products/gallery/")
    alt_text = models.CharField(max_length=150, blank=True)
    sort_order = models.PositiveIntegerField(default=0)

    def __str__(self):
        return self.alt_text or self.product.name


class CustomerProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="customer_profile")
    phone = models.CharField(max_length=30, blank=True)
    default_address = models.TextField(blank=True)

    def __str__(self):
        return self.user.get_username()


class Order(models.Model):
    STATUS_PENDING = "pending"
    STATUS_ACCEPTED = "accepted"
    STATUS_PREPARING = "preparing"
    STATUS_READY = "ready"
    STATUS_OUT_FOR_DELIVERY = "out_for_delivery"
    STATUS_COMPLETED = "completed"
    STATUS_CANCELLED = "cancelled"
    STATUS_REJECTED = "rejected"
    ORDER_STATUS = [
        (STATUS_PENDING, "Pending"),
        (STATUS_ACCEPTED, "Accepted"),
        (STATUS_PREPARING, "Preparing"),
        (STATUS_READY, "Ready"),
        (STATUS_OUT_FOR_DELIVERY, "Out for delivery"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_CANCELLED, "Cancelled"),
        (STATUS_REJECTED, "Rejected"),
    ]
    PAYMENT_STATUS = [
        ("unpaid", "Unpaid"),
        ("pending", "Pending"),
        ("paid", "Paid"),
        ("refunded", "Refunded"),
    ]
    ORDER_TYPE_CHOICES = [
        ("pickup", "Pickup"),
        ("delivery", "Delivery"),
    ]
    PAYMENT_METHOD_CHOICES = [
        ("cash", "Cash"),
        ("bank_transfer", "Bank Transfer"),
        ("online", "Online"),
    ]

    DELIVERY_ZONE_CHOICES = [("local", "Local"), ("international", "International")]

    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name="orders")
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="orders"
    )
    order_number = models.CharField(max_length=30, unique=True)
    customer_name = models.CharField(max_length=150)
    customer_email = models.EmailField(blank=True)
    customer_phone = models.CharField(max_length=30)
    delivery_address = models.TextField(blank=True)
    order_type = models.CharField(max_length=30, choices=ORDER_TYPE_CHOICES, default="pickup")
    delivery_zone = models.CharField(max_length=30, choices=DELIVERY_ZONE_CHOICES, blank=True, null=True, default="")
    status = models.CharField(max_length=30, choices=ORDER_STATUS, default=STATUS_PENDING)
    payment_method = models.CharField(max_length=30, choices=PAYMENT_METHOD_CHOICES, default="cash")
    payment_status = models.CharField(max_length=30, choices=PAYMENT_STATUS, default="unpaid")
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    discount_total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    delivery_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=10, decimal_places=2)
    customer_note = models.TextField(blank=True)
    seller_note = models.TextField(blank=True)
    terms_accepted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["shop", "status"]),
            models.Index(fields=["shop", "created_at"]),
            models.Index(fields=["order_number"]),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return self.order_number


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True)
    product_name = models.CharField(max_length=150)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField()
    line_total = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.quantity} x {self.product_name}"


class Coupon(models.Model):
    DISCOUNT_PERCENTAGE = "percentage"
    DISCOUNT_FIXED = "fixed"
    DISCOUNT_TYPE = [
        (DISCOUNT_PERCENTAGE, "Percentage"),
        (DISCOUNT_FIXED, "Fixed Amount"),
    ]
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name="coupons")
    code = models.CharField(max_length=50)
    discount_type = models.CharField(max_length=30, choices=DISCOUNT_TYPE)
    discount_value = models.DecimalField(max_digits=10, decimal_places=2)
    min_order_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    usage_limit = models.PositiveIntegerField(null=True, blank=True)
    used_count = models.PositiveIntegerField(default=0)
    active = models.BooleanField(default=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["shop", "code"], name="unique_marketplace_coupon_per_shop"),
        ]

    def __str__(self):
        return self.code


class OrderCancellationRequest(models.Model):
    STATUS_PENDING = "pending"
    STATUS_APPROVED = "approved"
    STATUS_REJECTED = "rejected"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_REJECTED, "Rejected"),
    ]
    REASON_CHOICES = [
        ("wrong_order", "I ordered the wrong item"),
        ("changed_mind", "I changed my mind"),
        ("too_long", "Taking too long"),
        ("duplicate", "Duplicate order"),
        ("payment_issue", "Payment issue"),
        ("other", "Other"),
    ]

    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name="cancellation_request")
    buyer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="cancellation_requests",
    )
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name="cancellation_requests")
    reason = models.CharField(max_length=50, choices=REASON_CHOICES)
    message = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    seller_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["shop", "status"]),
            models.Index(fields=["buyer", "status"]),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"Cancel request for {self.order.order_number} – {self.get_status_display()}"


class Campaign(models.Model):
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name="campaigns")
    title = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    banner_image = models.ImageField(upload_to="campaigns/", blank=True, null=True)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    active = models.BooleanField(default=True)
    featured_product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["shop", "active", "starts_at", "ends_at"]),
        ]
        ordering = ["-starts_at"]

    def __str__(self):
        return self.title
