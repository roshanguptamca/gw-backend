from django.urls import include, path

from rest_framework.routers import DefaultRouter

from .views import (
    AdminProductViewSet,
    AdminSellerViewSet,
    AdminShopViewSet,
    BuyerOrderViewSet,
    CustomerOrderViewSet,
    MarketplaceCartItemCreateView,
    MarketplaceCartItemView,
    MarketplaceCartView,
    MarketplaceMeView,
    MarketplaceOrderDetailView,
    MarketplaceSearchView,
    OrderCreateView,
    PublicCategoryListView,
    PublicProductViewSet,
    PublicShopViewSet,
    SellerCampaignViewSet,
    SellerCancellationRequestViewSet,
    SellerCategoryViewSet,
    SellerCouponViewSet,
    SellerDashboardView,
    SellerMeView,
    SellerOrderViewSet,
    SellerProductImageViewSet,
    SellerProductViewSet,
    SellerSettingsView,
    SellerShopView,
)

router = DefaultRouter()
router.register("marketplace/shops", PublicShopViewSet, basename="marketplace-shop")
router.register("marketplace/products", PublicProductViewSet, basename="marketplace-product")
router.register("customer/orders", CustomerOrderViewSet, basename="customer-order")
router.register("buyer/orders", BuyerOrderViewSet, basename="buyer-order")
router.register("seller/products", SellerProductViewSet, basename="seller-product")
router.register("seller/product-images", SellerProductImageViewSet, basename="seller-product-image")
router.register("seller/orders", SellerOrderViewSet, basename="seller-order")
router.register("seller/coupons", SellerCouponViewSet, basename="seller-coupon")
router.register("seller/campaigns", SellerCampaignViewSet, basename="seller-campaign")
router.register("seller/categories", SellerCategoryViewSet, basename="seller-category")
router.register(
    "seller/cancellation-requests",
    SellerCancellationRequestViewSet,
    basename="seller-cancellation",
)
router.register("admin/sellers", AdminSellerViewSet, basename="admin-seller")
router.register("admin/shops", AdminShopViewSet, basename="admin-shop")
router.register("admin/products", AdminProductViewSet, basename="admin-product")

urlpatterns = [
    path("orders/", OrderCreateView.as_view(), name="marketplace-order-create"),
    path("marketplace/orders/", OrderCreateView.as_view(), name="marketplace-order-request-create"),
    path(
        "marketplace/orders/<int:order_id>/",
        MarketplaceOrderDetailView.as_view(),
        name="marketplace-order-request-detail",
    ),
    path(
        "marketplace/seller/orders/",
        SellerOrderViewSet.as_view({"get": "list"}),
        name="marketplace-seller-order-list",
    ),
    path("marketplace/me/", MarketplaceMeView.as_view(), name="marketplace-me"),
    path("marketplace/search/", MarketplaceSearchView.as_view(), name="marketplace-search"),
    path("marketplace/categories/", PublicCategoryListView.as_view(), name="marketplace-categories"),
    path("marketplace/cart/", MarketplaceCartView.as_view(), name="marketplace-cart"),
    path(
        "marketplace/cart/items/",
        MarketplaceCartItemCreateView.as_view(),
        name="marketplace-cart-item-create",
    ),
    path(
        "marketplace/cart/items/<int:product_id>/",
        MarketplaceCartItemView.as_view(),
        name="marketplace-cart-item",
    ),
    path("seller/me/", SellerMeView.as_view(), name="seller-me"),
    path("seller/dashboard/", SellerDashboardView.as_view(), name="seller-dashboard"),
    path("seller/shop/", SellerShopView.as_view(), name="seller-shop"),
    path("seller/settings/", SellerSettingsView.as_view(), name="seller-settings"),
    path("", include(router.urls)),
]
