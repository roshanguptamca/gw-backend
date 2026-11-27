"""Seller-owned pages and durable catering enquiries. No seeded storefront content."""

from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle

from .models import Product, Shop, ShopEnquiry, ShopPage
from .permissions import IsSeller, IsShopOwner


class ShopPageSerializer(serializers.ModelSerializer):
    product_ids = serializers.PrimaryKeyRelatedField(
        source="products", many=True, queryset=Product.objects.none(), required=False
    )
    ordering_open = serializers.SerializerMethodField()

    class Meta:
        model = ShopPage
        fields = [
            "id",
            "slug",
            "title",
            "kind",
            "description",
            "fulfilment_notes",
            "cover_url",
            "is_published",
            "is_featured",
            "position",
            "order_deadline",
            "product_ids",
            "ordering_open",
        ]
        read_only_fields = ["id", "ordering_open"]
        # Validate per-shop uniqueness explicitly; shop is always supplied by the authenticated seller.
        validators = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if (
            request
            and request.user.is_authenticated
            and hasattr(request.user, "seller_profile")
            and hasattr(self.fields["product_ids"], "child_relation")
        ):
            self.fields["product_ids"].child_relation.queryset = Product.objects.filter(
                shop=request.user.seller_profile.shop
            )

    def get_ordering_open(self, obj):
        return not obj.order_deadline or obj.order_deadline > timezone.now()

    def validate_slug(self, value):
        import re

        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", value):
            raise serializers.ValidationError("Use lowercase letters, numbers and hyphens.")
        return value

    def validate_cover_url(self, value):
        if value and not value.startswith("https://"):
            raise serializers.ValidationError("Use an HTTPS image URL.")
        return value

    def validate(self, attrs):
        shop = self.context["request"].user.seller_profile.shop
        slug = attrs.get("slug", getattr(self.instance, "slug", ""))
        others = ShopPage.objects.filter(shop=shop, slug=slug)
        if self.instance:
            others = others.exclude(pk=self.instance.pk)
        if others.exists():
            raise serializers.ValidationError({"slug": "This shop already has a page with this URL."})
        published = attrs.get("is_published", getattr(self.instance, "is_published", False))
        kind = attrs.get("kind", getattr(self.instance, "kind", "menu"))
        products = attrs.get("products", self.instance.products.all() if self.instance else [])
        if published and kind == "menu" and not products:
            raise serializers.ValidationError({"product_ids": "Select at least one product before publishing a menu."})
        return attrs


class PublicShopPageSerializer(ShopPageSerializer):
    product_ids = serializers.SerializerMethodField()

    def get_product_ids(self, obj):
        return [p.id for p in obj.products.all() if p.shop_id == obj.shop_id and p.is_active and p.is_approved]


class SellerShopPageViewSet(viewsets.ModelViewSet):
    serializer_class = ShopPageSerializer
    permission_classes = [IsSeller, IsShopOwner]
    pagination_class = None

    def get_queryset(self):
        return ShopPage.objects.filter(shop=self.request.user.seller_profile.shop).prefetch_related("products")

    def _save(self, serializer, **kwargs):
        try:
            with transaction.atomic():
                serializer.save(**kwargs)
        except IntegrityError as exc:
            raise ValidationError({"slug": "This shop already has a page with this URL."}) from exc

    def perform_create(self, serializer):
        self._save(serializer, shop=self.request.user.seller_profile.shop)

    def perform_update(self, serializer):
        self._save(serializer)


class EnquiryThrottle(SimpleRateThrottle):
    scope = "shop_page_enquiry"
    rate = "5/hour"

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


class ShopEnquirySerializer(serializers.ModelSerializer):
    product_ids = serializers.ListField(child=serializers.IntegerField(min_value=1), max_length=100, required=False)
    privacy_accepted = serializers.BooleanField(write_only=True, required=True)

    class Meta:
        model = ShopEnquiry
        fields = [
            "id",
            "page",
            "page_title",
            "customer_name",
            "email",
            "phone",
            "event_date",
            "guests",
            "message",
            "product_ids",
            "privacy_accepted",
            "status",
            "created_at",
        ]
        read_only_fields = ["id", "page", "page_title", "status", "created_at"]
        extra_kwargs = {"message": {"max_length": 4000}}

    def validate_privacy_accepted(self, value):
        if not value:
            raise serializers.ValidationError("Consent to sharing your details with this seller is required.")
        return value

    def validate_event_date(self, value):
        if value < timezone.localdate():
            raise serializers.ValidationError("Choose today or a future date.")
        return value

    def validate_product_ids(self, values):
        page = self.context["page"]
        allowed = set(
            page.products.filter(shop=page.shop, is_active=True, is_approved=True).values_list("id", flat=True)
        )
        if not set(values).issubset(allowed):
            raise serializers.ValidationError("Choose dishes offered on this page.")
        return list(dict.fromkeys(values))

    def create(self, validated_data):
        validated_data.pop("privacy_accepted")
        return super().create(validated_data)


class PublicShopPageViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = PublicShopPageSerializer
    permission_classes = [AllowAny]
    lookup_field = "slug"
    pagination_class = None

    def get_shop(self):
        return get_object_or_404(Shop, slug=self.kwargs["shop_slug"], is_active=True, is_approved=True)

    def get_queryset(self):
        return ShopPage.objects.filter(shop=self.get_shop(), is_published=True).prefetch_related("products")

    @action(detail=True, methods=["post"], throttle_classes=[EnquiryThrottle])
    def enquiries(self, request, **kwargs):
        page = self.get_object()
        if page.kind != "enquiry":
            raise ValidationError("This page does not accept quote requests.")
        if not ShopPageSerializer().get_ordering_open(page) or not getattr(
            page.shop.settings, "accepting_orders", True
        ):
            raise ValidationError("This seller is not accepting requests for this page.")
        serializer = ShopEnquirySerializer(data=request.data, context={"page": page})
        serializer.is_valid(raise_exception=True)
        enquiry = serializer.save(shop=page.shop, page=page, page_title=page.title)
        return Response({"id": enquiry.id}, status=201)


class SellerShopEnquiryViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ShopEnquirySerializer
    permission_classes = [IsSeller, IsShopOwner]
    pagination_class = None

    def get_queryset(self):
        return ShopEnquiry.objects.filter(shop=self.request.user.seller_profile.shop).select_related("page")

    def list(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_queryset()[:200], many=True)
        return Response(serializer.data)
