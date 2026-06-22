from django.db.models import Count, Q, Sum
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .models import Campaign, Category, Coupon, Order, OrderCancellationRequest, Product, ProductImage, SellerProfile, Shop
from .permissions import IsSeller, IsShopOwner, IsSuperAdmin
from .serializers import (
    AdminProductApprovalSerializer,
    AdminSellerCreateSerializer,
    AdminSellerUpdateSerializer,
    BuyerOrderSerializer,
    CampaignSerializer,
    CategorySerializer,
    CouponSerializer,
    MarketplaceSearchResultSerializer,
    OrderCancellationCreateSerializer,
    OrderCancellationRequestSerializer,
    OrderCreateSerializer,
    OrderSerializer,
    ProductImageSerializer,
    ProductSerializer,
    PublicCategorySerializer,
    PublicProductSerializer,
    PublicShopSerializer,
    SellerCancellationResponseSerializer,
    SellerProfileSerializer,
    ShopSerializer,
    ShopSettingsSerializer,
)
from .services import (
    generate_unique_slug,
    link_guest_orders_to_user,
    send_cancellation_request_email_to_seller,
    send_cancellation_result_email_to_buyer,
    update_order_status,
)


class PublicShopViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = PublicShopSerializer
    permission_classes = [AllowAny]
    lookup_field = "slug"

    def get_queryset(self):
        return (
            Shop.objects.filter(is_active=True, is_approved=True)
            .select_related("settings")
            .annotate(product_count=Count("products"))
            .order_by("name")
        )

    @action(detail=True, methods=["get"])
    def products(self, request, slug=None):
        shop = self.get_object()
        products = (
            Product.objects.filter(shop=shop, is_active=True, is_approved=True)
            .select_related("shop", "category")
            .prefetch_related("images")
            .order_by("-is_featured", "name")
        )
        return Response(PublicProductSerializer(products, many=True, context={"request": request}).data)

    @action(detail=True, methods=["get"])
    def campaigns(self, request, slug=None):
        shop = self.get_object()
        now = timezone.now()
        campaigns = Campaign.objects.filter(shop=shop, active=True, starts_at__lte=now, ends_at__gte=now)
        return Response(CampaignSerializer(campaigns, many=True, context={"request": request}).data)


class PublicProductViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = PublicProductSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        queryset = (
            Product.objects.filter(shop__is_active=True, shop__is_approved=True, is_active=True, is_approved=True)
            .select_related("shop", "shop__settings", "category")
            .prefetch_related("images")
            .order_by("-is_featured", "name")
        )
        shop_slug = self.request.query_params.get("shop")
        if shop_slug:
            queryset = queryset.filter(shop__slug=shop_slug)
        return queryset


class OrderCreateView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "marketplace_order"

    def post(self, request):
        serializer = OrderCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        order = serializer.save()
        return Response(OrderSerializer(order, context={"request": request}).data, status=status.HTTP_201_CREATED)


class CustomerOrderViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Order.objects.filter(customer=self.request.user).select_related("shop").prefetch_related("items")


class BuyerOrderViewSet(viewsets.ReadOnlyModelViewSet):
    """Buyer sees only their own orders. Sellers and guests cannot access this."""
    serializer_class = BuyerOrderSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Always filter by the current authenticated user — never expose other users' orders
        return (
            Order.objects.filter(customer=self.request.user)
            .select_related("shop", "cancellation_request")
            .prefetch_related("items")
            .order_by("-created_at")
        )

    @action(detail=True, methods=["post"])
    def cancel_request(self, request, pk=None):
        """Submit a cancellation request for an order."""
        order = self.get_object()  # already scoped to request.user
        if order.status not in (Order.STATUS_PENDING, Order.STATUS_ACCEPTED):
            return Response(
                {"detail": "Cancellation requests can only be submitted for pending or accepted orders."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if hasattr(order, "cancellation_request"):
            return Response(
                {"detail": "A cancellation request has already been submitted for this order."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = OrderCancellationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cancel_request = OrderCancellationRequest.objects.create(
            order=order,
            buyer=request.user,
            shop=order.shop,
            reason=serializer.validated_data["reason"],
            message=serializer.validated_data.get("message", ""),
            status=OrderCancellationRequest.STATUS_PENDING,
        )
        try:
            send_cancellation_request_email_to_seller(cancel_request)
        except Exception:
            pass
        return Response(
            OrderCancellationRequestSerializer(cancel_request).data,
            status=status.HTTP_201_CREATED,
        )


class SellerCancellationRequestViewSet(viewsets.GenericViewSet):
    """Seller views and responds to cancellation requests for their shop."""
    serializer_class = OrderCancellationRequestSerializer
    permission_classes = [IsSeller]

    def get_queryset(self):
        return (
            OrderCancellationRequest.objects.filter(shop=self.request.user.seller_profile.shop)
            .select_related("order", "order__shop", "buyer")
            .order_by("-created_at")
        )

    def list(self, request):
        qs = self.get_queryset()
        status_filter = request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)
        return Response(OrderCancellationRequestSerializer(qs, many=True).data)

    def partial_update(self, request, pk=None):
        cancel_request = self.get_queryset().filter(pk=pk).first()
        if not cancel_request:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if cancel_request.status != OrderCancellationRequest.STATUS_PENDING:
            return Response(
                {"detail": "This request has already been processed."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = SellerCancellationResponseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cancel_request.status = serializer.validated_data["status"]
        cancel_request.seller_note = serializer.validated_data.get("seller_note", "")
        cancel_request.save(update_fields=["status", "seller_note", "updated_at"])
        # If approved, cancel the order
        if cancel_request.status == OrderCancellationRequest.STATUS_APPROVED:
            cancel_request.order.status = Order.STATUS_CANCELLED
            cancel_request.order.save(update_fields=["status", "updated_at"])
        try:
            send_cancellation_result_email_to_buyer(cancel_request)
        except Exception:
            pass
        return Response(OrderCancellationRequestSerializer(cancel_request).data)


class MarketplaceSearchView(APIView):
    """Search marketplace products and shops with filters. Public endpoint."""
    permission_classes = [AllowAny]

    def get(self, request):
        q = request.query_params.get("q", "").strip()
        category_slug = request.query_params.get("category", "").strip()
        shop_slug = request.query_params.get("shop", "").strip()
        min_price = request.query_params.get("min_price")
        max_price = request.query_params.get("max_price")
        in_stock = request.query_params.get("in_stock", "").lower() in ("true", "1", "yes")

        # Base product queryset: only active + approved
        products_qs = (
            Product.objects.filter(
                shop__is_active=True,
                shop__is_approved=True,
                is_active=True,
                is_approved=True,
            )
            .select_related("shop", "shop__settings", "category")
            .prefetch_related("images")
        )
        # Base shop queryset
        shops_qs = (
            Shop.objects.filter(is_active=True, is_approved=True)
            .select_related("settings")
            .annotate(product_count=Count("products"))
        )

        if q:
            products_qs = products_qs.filter(
                Q(name__icontains=q) | Q(description__icontains=q)
            )
            shops_qs = shops_qs.filter(
                Q(name__icontains=q) | Q(description__icontains=q)
            )
        if category_slug:
            products_qs = products_qs.filter(category__slug=category_slug)
        if shop_slug:
            products_qs = products_qs.filter(shop__slug=shop_slug)
            shops_qs = shops_qs.filter(slug=shop_slug)
        if min_price:
            try:
                products_qs = products_qs.filter(price__gte=float(min_price))
            except (ValueError, TypeError):
                pass
        if max_price:
            try:
                products_qs = products_qs.filter(price__lte=float(max_price))
            except (ValueError, TypeError):
                pass
        if in_stock:
            products_qs = products_qs.filter(stock_quantity__gt=0)

        products_list = list(products_qs.order_by("-is_featured", "name")[:50])
        shops_list = list(shops_qs.order_by("name")[:20])

        return Response({
            "shops": PublicShopSerializer(shops_list, many=True, context={"request": request}).data,
            "products": PublicProductSerializer(products_list, many=True, context={"request": request}).data,
            "total_shops": len(shops_list),
            "total_products": len(products_list),
        })


class PublicCategoryListView(APIView):
    """List all active categories visible in the marketplace."""
    permission_classes = [AllowAny]

    def get(self, request):
        categories = (
            Category.objects.filter(is_active=True)
            .annotate(product_count=Count(
                "products",
                filter=Q(products__is_active=True, products__is_approved=True),
            ))
            .order_by("name")
        )
        return Response(PublicCategorySerializer(categories, many=True).data)


class SellerMeView(APIView):
    permission_classes = [IsSeller]

    def get(self, request):
        return Response(SellerProfileSerializer(request.user.seller_profile, context={"request": request}).data)


class SellerDashboardView(APIView):
    permission_classes = [IsSeller]

    def get(self, request):
        shop = request.user.seller_profile.shop
        today = timezone.localdate()
        month_start = today.replace(day=1)
        orders = Order.objects.filter(shop=shop)
        completed = orders.filter(status=Order.STATUS_COMPLETED)
        data = {
            "total_products": Product.objects.filter(shop=shop).count(),
            "active_products": Product.objects.filter(shop=shop, is_active=True).count(),
            "pending_orders": orders.filter(status=Order.STATUS_PENDING).count(),
            "completed_orders": completed.count(),
            "today_sales": str(
                completed.filter(created_at__date=today).aggregate(total=Sum("total"))["total"] or "0.00"
            ),
            "month_sales": str(
                completed.filter(created_at__date__gte=month_start).aggregate(total=Sum("total"))["total"] or "0.00"
            ),
            "low_stock_products": Product.objects.filter(shop=shop, stock_quantity__lte=5).count(),
            "pending_cancellations": OrderCancellationRequest.objects.filter(
                shop=shop, status=OrderCancellationRequest.STATUS_PENDING
            ).count(),
            "recent_orders": OrderSerializer(
                orders.select_related("shop").prefetch_related("items")[:5],
                many=True,
                context={"request": request},
            ).data,
        }
        return Response(data)


class SellerShopView(APIView):
    permission_classes = [IsSeller]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get(self, request):
        return Response(ShopSerializer(request.user.seller_profile.shop, context={"request": request}).data)

    def patch(self, request):
        serializer = ShopSerializer(
            request.user.seller_profile.shop,
            data=request.data,
            partial=True,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class SellerSettingsView(APIView):
    permission_classes = [IsSeller]

    def get(self, request):
        shop = request.user.seller_profile.shop
        data = ShopSettingsSerializer(shop.settings).data
        data["pickup_available"] = shop.pickup_available
        data["delivery_available"] = shop.delivery_available
        return Response(data)

    def patch(self, request):
        shop = request.user.seller_profile.shop
        # Extract shop-level fields before passing to settings serializer
        shop_fields = {}
        data = request.data.copy() if hasattr(request.data, "copy") else dict(request.data)
        for field in ("pickup_available", "delivery_available"):
            if field in data:
                val = data.pop(field)
                if isinstance(val, str):
                    shop_fields[field] = val.lower() not in ("false", "0", "")
                else:
                    shop_fields[field] = bool(val)
        if shop_fields:
            for attr, value in shop_fields.items():
                setattr(shop, attr, value)
            shop.save(update_fields=list(shop_fields.keys()) + ["updated_at"])
        serializer = ShopSettingsSerializer(shop.settings, data=data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        response_data = serializer.data
        response_data["pickup_available"] = shop.pickup_available
        response_data["delivery_available"] = shop.delivery_available
        return Response(response_data)


class SellerProductViewSet(viewsets.ModelViewSet):
    serializer_class = ProductSerializer
    permission_classes = [IsSeller, IsShopOwner]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_queryset(self):
        return (
            Product.objects.filter(shop=self.request.user.seller_profile.shop)
            .select_related("category")
            .prefetch_related("images")
            .order_by("-created_at")
        )

    @action(detail=True, methods=["post"], parser_classes=[MultiPartParser, FormParser])
    def images(self, request, pk=None):
        product = self.get_object()
        serializer = ProductImageSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save(product=product)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class SellerProductImageViewSet(viewsets.GenericViewSet):
    permission_classes = [IsSeller, IsShopOwner]

    def get_queryset(self):
        return ProductImage.objects.filter(product__shop=self.request.user.seller_profile.shop)

    def destroy(self, request, pk=None):
        image = self.get_object()
        image.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class SellerOrderViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = OrderSerializer
    permission_classes = [IsSeller, IsShopOwner]

    def get_queryset(self):
        return Order.objects.filter(shop=self.request.user.seller_profile.shop).select_related("shop").prefetch_related("items")

    @action(detail=True, methods=["patch"])
    def status(self, request, pk=None):
        order = self.get_object()
        order = update_order_status(order, request.data.get("status"))
        return Response(OrderSerializer(order, context={"request": request}).data)


class SellerCouponViewSet(viewsets.ModelViewSet):
    serializer_class = CouponSerializer
    permission_classes = [IsSeller, IsShopOwner]

    def get_queryset(self):
        return Coupon.objects.filter(shop=self.request.user.seller_profile.shop).order_by("-id")

    def perform_create(self, serializer):
        serializer.save(shop=self.request.user.seller_profile.shop)


class SellerCampaignViewSet(viewsets.ModelViewSet):
    serializer_class = CampaignSerializer
    permission_classes = [IsSeller, IsShopOwner]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_queryset(self):
        return Campaign.objects.filter(shop=self.request.user.seller_profile.shop).order_by("-starts_at")

    def perform_create(self, serializer):
        serializer.save(shop=self.request.user.seller_profile.shop)


class SellerCategoryViewSet(viewsets.ModelViewSet):
    serializer_class = CategorySerializer
    permission_classes = [IsSeller, IsShopOwner]

    def get_queryset(self):
        shop = self.request.user.seller_profile.shop
        return Category.objects.filter(shop__in=[shop, None], is_active=True).order_by("name")

    def perform_create(self, serializer):
        name = serializer.validated_data["name"]
        shop = self.request.user.seller_profile.shop
        serializer.save(shop=shop, slug=generate_unique_slug(Category, name, shop=shop))


class AdminSellerViewSet(viewsets.ModelViewSet):
    permission_classes = [IsSuperAdmin]

    def get_queryset(self):
        return SellerProfile.objects.select_related("user", "shop", "shop__settings").order_by("-created_at")

    def get_serializer_class(self):
        if self.action == "create":
            return AdminSellerCreateSerializer
        if self.action in {"partial_update", "update"}:
            return AdminSellerUpdateSerializer
        return SellerProfileSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        seller = serializer.save()
        return Response(
            SellerProfileSerializer(seller, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        seller = self.get_object()
        seller.is_active = True
        seller.user.is_active = True
        seller.save(update_fields=["is_active", "updated_at"])
        seller.user.save(update_fields=["is_active"])
        return Response(SellerProfileSerializer(seller, context={"request": request}).data)

    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        seller = self.get_object()
        seller.is_active = False
        seller.user.is_active = False
        seller.save(update_fields=["is_active", "updated_at"])
        seller.user.save(update_fields=["is_active"])
        return Response(SellerProfileSerializer(seller, context={"request": request}).data)


class AdminShopViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ShopSerializer
    permission_classes = [IsSuperAdmin]
    queryset = Shop.objects.select_related("settings").order_by("-created_at")

    @action(detail=True, methods=["patch"])
    def approve(self, request, pk=None):
        shop = self.get_object()
        shop.is_approved = True
        shop.is_active = True
        shop.save(update_fields=["is_approved", "is_active", "updated_at"])
        return Response(ShopSerializer(shop, context={"request": request}).data)


class AdminProductViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ProductSerializer
    permission_classes = [IsSuperAdmin]
    queryset = Product.objects.select_related("shop", "category").prefetch_related("images").order_by("-created_at")

    @action(detail=True, methods=["patch"])
    def approve(self, request, pk=None):
        serializer = AdminProductApprovalSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        product = self.get_object()
        product.is_approved = serializer.validated_data["is_approved"]
        product.save(update_fields=["is_approved", "updated_at"])
        return Response(ProductSerializer(product, context={"request": request}).data)
