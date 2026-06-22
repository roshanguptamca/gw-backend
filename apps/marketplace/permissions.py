from rest_framework.permissions import BasePermission


class IsSuperAdmin(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_superuser)


class IsSeller(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and hasattr(request.user, "seller_profile")
            and request.user.seller_profile.is_active
            and hasattr(request.user.seller_profile, "shop")
        )


class IsShopOwner(BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.user.is_superuser:
            return True
        shop = getattr(obj, "shop", None)
        if shop:
            return shop.owner_id == request.user.id
        product = getattr(obj, "product", None)
        if product:
            return product.shop.owner_id == request.user.id
        owner = getattr(obj, "owner", None)
        return bool(owner and owner.id == request.user.id)

