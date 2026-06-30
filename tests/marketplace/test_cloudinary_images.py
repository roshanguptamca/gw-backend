from decimal import Decimal
from io import BytesIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from PIL import Image
from rest_framework import status
from rest_framework.test import APIClient

from apps.marketplace.models import Product, ProductImage
from apps.marketplace.services import create_seller_with_shop

User = get_user_model()

CLOUDINARY_TEST_SETTINGS = {
    "CLOUDINARY_CLOUD_NAME": "test-cloud",
    "CLOUDINARY_API_KEY": "test-key",
    "CLOUDINARY_API_SECRET": "test-secret",
    "CLOUDINARY_FOLDER_PREFIX": "guidewisey/products",
}


def image_upload(name="product.png", *, extra_bytes=0):
    content = BytesIO()
    Image.new("RGB", (2, 2), color=(40, 160, 90)).save(content, format="PNG")
    data = content.getvalue() + (b"\0" * extra_bytes)
    return SimpleUploadedFile(name, data, content_type="image/png")


@override_settings(**CLOUDINARY_TEST_SETTINGS)
class CloudinaryProductImageAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_superuser(
            username="image-admin@example.com",
            email="image-admin@example.com",
            password="adminpass123",
        )
        self.seller, _, self.shop = create_seller_with_shop(
            email="image-seller@example.com",
            password="sellerpass123",
            first_name="Image",
            last_name="Seller",
            business_name="Image Seller",
            created_by=self.admin,
        )
        self.other_seller, _, self.other_shop = create_seller_with_shop(
            email="other-image-seller@example.com",
            password="sellerpass123",
            first_name="Other",
            last_name="Seller",
            business_name="Other Image Seller",
            created_by=self.admin,
        )
        self.product = Product.objects.create(
            shop=self.shop,
            name="Namak Para",
            slug="namak-para",
            sku="RK-NP-500",
            price=Decimal("5.00"),
        )
        self.other_product = Product.objects.create(
            shop=self.other_shop,
            name="Gulab Jamun",
            slug="gulab-jamun",
            sku="RK-GJ-500",
            price=Decimal("10.00"),
        )

    @patch("cloudinary.uploader.upload")
    def test_valid_main_image_upload_returns_secure_url(self, upload):
        upload.return_value = {
            "public_id": "guidewisey/products/RK-NP-500/main",
            "secure_url": "https://res.cloudinary.com/test-cloud/image/upload/main.webp",
        }
        self.client.force_authenticate(self.seller)

        response = self.client.patch(
            f"/api/seller/products/{self.product.id}/",
            {"image": image_upload()},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["image_url"], upload.return_value["secure_url"])
        self.product.refresh_from_db()
        self.assertEqual(self.product.image_public_id, "guidewisey/products/RK-NP-500/main")
        self.assertEqual(self.product.image_url, upload.return_value["secure_url"])
        self.assertEqual(upload.call_args.kwargs["public_id"], "guidewisey/products/RK-NP-500/main")
        self.assertTrue(upload.call_args.kwargs["overwrite"])

    @patch("cloudinary.uploader.upload")
    def test_product_create_accepts_main_image(self, upload):
        upload.return_value = {
            "public_id": "guidewisey/products/RK-NEW-1/main",
            "secure_url": "https://res.cloudinary.com/test-cloud/image/upload/new-main.webp",
        }
        self.client.force_authenticate(self.seller)

        response = self.client.post(
            "/api/seller/products/",
            {
                "name": "New Product",
                "sku": "RK-NEW-1",
                "price": "7.50",
                "stock_quantity": 4,
                "image": image_upload(),
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["image_url"], upload.return_value["secure_url"])
        self.assertTrue(Product.objects.filter(sku="RK-NEW-1", image_url=upload.return_value["secure_url"]).exists())

    @patch("cloudinary.uploader.upload")
    def test_gallery_upload_uses_sort_order_path(self, upload):
        upload.return_value = {
            "public_id": "guidewisey/products/RK-NP-500/gallery/3",
            "secure_url": "https://res.cloudinary.com/test-cloud/image/upload/gallery-3.webp",
        }
        self.client.force_authenticate(self.seller)

        response = self.client.post(
            f"/api/seller/products/{self.product.id}/images/",
            {"image": image_upload(), "sort_order": 3, "alt_text": "Namak para packet"},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["image_url"], upload.return_value["secure_url"])
        gallery = ProductImage.objects.get(product=self.product, sort_order=3)
        self.assertEqual(gallery.image_public_id, "guidewisey/products/RK-NP-500/gallery/3")
        self.assertEqual(gallery.alt_text, "Namak para packet")

    @patch("cloudinary.uploader.upload")
    def test_invalid_file_type_is_rejected_before_upload(self, upload):
        self.client.force_authenticate(self.seller)
        invalid = SimpleUploadedFile("product.gif", b"GIF89a", content_type="image/gif")

        response = self.client.patch(
            f"/api/seller/products/{self.product.id}/",
            {"image": invalid},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        upload.assert_not_called()

    @patch("cloudinary.uploader.upload")
    def test_oversized_file_is_rejected_before_upload(self, upload):
        self.client.force_authenticate(self.seller)
        oversized = image_upload(extra_bytes=2 * 1024 * 1024)

        response = self.client.patch(
            f"/api/seller/products/{self.product.id}/",
            {"image": oversized},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("2 MB", str(response.data))
        upload.assert_not_called()

    @patch("cloudinary.uploader.upload")
    def test_seller_cannot_upload_for_another_sellers_product(self, upload):
        self.client.force_authenticate(self.seller)

        response = self.client.patch(
            f"/api/seller/products/{self.other_product.id}/",
            {"image": image_upload()},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        upload.assert_not_called()

    @patch("cloudinary.uploader.upload")
    def test_super_admin_can_upload_for_any_product(self, upload):
        upload.return_value = {
            "public_id": "guidewisey/products/RK-GJ-500/main",
            "secure_url": "https://res.cloudinary.com/test-cloud/image/upload/admin-main.webp",
        }
        self.client.force_authenticate(self.admin)

        response = self.client.patch(
            f"/api/admin/products/{self.other_product.id}/",
            {"image": image_upload()},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["image_url"], upload.return_value["secure_url"])

    @patch("cloudinary.uploader.upload")
    def test_super_admin_can_upload_gallery_image_for_any_product(self, upload):
        upload.return_value = {
            "public_id": "guidewisey/products/RK-GJ-500/gallery/0",
            "secure_url": "https://res.cloudinary.com/test-cloud/image/upload/admin-gallery.webp",
        }
        self.client.force_authenticate(self.admin)

        response = self.client.post(
            f"/api/admin/products/{self.other_product.id}/images/",
            {"image": image_upload(), "sort_order": 0},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["image_url"], upload.return_value["secure_url"])

    def test_buyer_cannot_upload_product_image(self):
        buyer = User.objects.create_user(
            username="image-buyer@example.com",
            email="image-buyer@example.com",
            password="buyerpass123",
        )
        self.client.force_authenticate(buyer)

        response = self.client.patch(
            f"/api/seller/products/{self.product.id}/",
            {"image": image_upload()},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_api_returns_empty_image_url_for_frontend_fallback(self):
        self.shop.is_approved = True
        self.shop.save(update_fields=["is_approved"])
        self.product.is_active = True
        self.product.is_approved = True
        self.product.save(update_fields=["is_active", "is_approved"])

        response = self.client.get(f"/api/marketplace/products/{self.product.id}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["image_url"], "")


class RishiKitchenCloudinarySeedTests(TestCase):
    @override_settings(CLOUDINARY_FOLDER_PREFIX="guidewisey/products")
    def test_seed_is_idempotent_and_uses_stable_skus_and_placeholder(self):
        with patch.dict("os.environ", {"RISHI_KITCHEN_PASSWORD": "safe-test-password"}):
            call_command("seed_rishi_kitchen", verbosity=0)
            call_command("seed_rishi_kitchen", verbosity=0)

        expected_skus = {
            "RK-NP-500",
            "RK-GJ-500",
            "RK-SAM-2",
            "RK-VP-2",
            "RK-MN-250",
            "RK-MN-500",
            "RK-IDLI-2",
            "RK-MG-2",
            "RK-GR-250",
            "RK-GR-500",
            "RK-GM-250",
            "RK-GM-500",
        }
        products = Product.objects.filter(shop__slug="rishi-kitchen")
        self.assertEqual(products.count(), 12)
        self.assertEqual(set(products.values_list("sku", flat=True)), expected_skus)
        self.assertFalse(products.exclude(image_url="/assets/images/product-placeholder.webp").exists())


@override_settings(**CLOUDINARY_TEST_SETTINGS)
class CloudinaryDjangoAdminTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_superuser(
            username="django-admin@example.com",
            email="django-admin@example.com",
            password="adminpass123",
        )
        seller, _, self.shop = create_seller_with_shop(
            email="admin-product-seller@example.com",
            password="sellerpass123",
            first_name="Admin",
            last_name="Seller",
            business_name="Admin Product Seller",
            created_by=self.admin,
        )
        self.product = Product.objects.create(
            shop=self.shop,
            name="Admin Product",
            slug="admin-product",
            sku="ADMIN-SKU-1",
            price=Decimal("12.00"),
            stock_quantity=5,
        )
        self.client.force_login(self.admin)

    @patch("cloudinary.uploader.upload")
    def test_django_admin_main_image_uses_shared_cloudinary_service(self, upload):
        upload.return_value = {
            "public_id": "guidewisey/products/ADMIN-SKU-1/main",
            "secure_url": "https://res.cloudinary.com/test-cloud/image/upload/admin-product.webp",
        }

        response = self.client.post(
            reverse("admin:marketplace_product_change", args=[self.product.pk]),
            {
                "shop": self.shop.pk,
                "category": "",
                "name": self.product.name,
                "slug": self.product.slug,
                "description": "",
                "ingredients": "",
                "allergens": "",
                "price": "12.00",
                "compare_at_price": "",
                "stock_quantity": "5",
                "sku": self.product.sku,
                "image": image_upload(),
                "external_image_url": "",
                "is_active": "on",
                "preparation_time_minutes": "0",
                "weight_grams": "",
                "images-TOTAL_FORMS": "0",
                "images-INITIAL_FORMS": "0",
                "images-MIN_NUM_FORMS": "0",
                "images-MAX_NUM_FORMS": "1000",
                "_save": "Save",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.product.refresh_from_db()
        self.assertEqual(self.product.image.name, "")
        self.assertEqual(self.product.image_public_id, upload.return_value["public_id"])
        self.assertEqual(self.product.image_url, upload.return_value["secure_url"])
        self.assertEqual(upload.call_args.kwargs["public_id"], "guidewisey/products/ADMIN-SKU-1/main")

        change_page = self.client.get(reverse("admin:marketplace_product_change", args=[self.product.pk]))
        self.assertContains(change_page, self.product.image_url)

    @patch("cloudinary.uploader.upload")
    def test_django_admin_gallery_image_uses_shared_cloudinary_service(self, upload):
        upload.return_value = {
            "public_id": "guidewisey/products/ADMIN-SKU-1/gallery/2",
            "secure_url": "https://res.cloudinary.com/test-cloud/image/upload/admin-gallery.webp",
        }

        response = self.client.post(
            reverse("admin:marketplace_productimage_add"),
            {
                "product": self.product.pk,
                "image": image_upload(),
                "alt_text": "Admin gallery image",
                "sort_order": "2",
                "_save": "Save",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        gallery_image = ProductImage.objects.get(product=self.product, sort_order=2)
        self.assertEqual(gallery_image.image.name, "")
        self.assertEqual(gallery_image.image_public_id, upload.return_value["public_id"])
        self.assertEqual(gallery_image.image_url, upload.return_value["secure_url"])
