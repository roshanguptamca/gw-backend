from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

import requests
from rest_framework.test import APIClient

from apps.marketplace.google_ratings import get_google_rating
from apps.marketplace.models import SellerProfile, Shop
from apps.marketplace.serializers import PublicShopSerializer, ShopSerializer


@override_settings(GOOGLE_PLACES_API_KEY="test-key-not-a-secret")
class GoogleRatingServiceTests(SimpleTestCase):
    @patch("apps.marketplace.google_ratings.requests.get")
    def test_returns_actual_rating_and_google_deep_link(self, get):
        get.return_value = Mock(status_code=200)
        get.return_value.json.return_value = {
            "rating": 4.7,
            "userRatingCount": 23,
            "googleMapsLinks": {"reviewsUri": "https://maps.google.com/reviews/test"},
        }
        self.assertEqual(
            get_google_rating("ChIJtest"),
            {
                "rating": 4.7,
                "review_count": 23,
                "reviews_url": "https://maps.google.com/reviews/test",
            },
        )
        args, kwargs = get.call_args
        self.assertEqual(args[0], "https://places.googleapis.com/v1/places/ChIJtest")
        self.assertEqual(kwargs["headers"]["X-Goog-FieldMask"], "rating,userRatingCount,googleMapsLinks")
        self.assertFalse(kwargs["allow_redirects"])
        self.assertEqual(kwargs["timeout"], (2, 3))

    @patch("apps.marketplace.google_ratings.requests.get")
    def test_no_request_for_missing_configuration_or_invalid_place_id(self, get):
        for value in ("", "../other", "https://maps.google.com/test", "a" * 256):
            self.assertIsNone(get_google_rating(value)["rating"])
        with override_settings(GOOGLE_PLACES_API_KEY=""):
            self.assertIsNone(get_google_rating("ChIJtest")["rating"])
        get.assert_not_called()

    @patch("apps.marketplace.google_ratings.requests.get")
    def test_empty_reviews_and_malformed_ratings_are_not_displayed(self, get):
        get.return_value = Mock(status_code=200)
        for data in (
            [],
            {},
            {"rating": 0, "userRatingCount": 5},
            {"rating": 6, "userRatingCount": 5},
            {"rating": True, "userRatingCount": 5},
            {"rating": float("nan"), "userRatingCount": 5},
            {"rating": 4, "userRatingCount": 0},
            {"rating": 4, "userRatingCount": "5"},
        ):
            get.return_value.json.return_value = data
            self.assertIsNone(get_google_rating("ChIJtest")["rating"])

    @patch("apps.marketplace.google_ratings.requests.get")
    def test_timeout_invalid_json_and_upstream_errors_degrade_safely(self, get):
        get.side_effect = requests.Timeout("test")
        self.assertIsNone(get_google_rating("ChIJtest")["rating"])
        get.side_effect = None
        get.return_value = Mock(status_code=403)
        self.assertIsNone(get_google_rating("ChIJtest")["rating"])
        get.return_value = Mock(status_code=200)
        get.return_value.json.side_effect = ValueError("invalid JSON")
        self.assertIsNone(get_google_rating("ChIJtest")["rating"])

    @patch("apps.marketplace.google_ratings.requests.get")
    def test_missing_or_unsafe_deep_link_uses_place_id_link(self, get):
        get.return_value = Mock(status_code=200)
        for link in (None, "javascript:alert(1)", "https://user:password@google.com"):
            get.return_value.json.return_value = {
                "rating": 4,
                "userRatingCount": 2,
                "googleMapsLinks": {"reviewsUri": link},
            }
            self.assertIn("query_place_id=ChIJtest", get_google_rating("ChIJtest")["reviews_url"])


class GoogleRatingAPITests(TestCase):
    def setUp(self):
        cache.clear()
        owner = get_user_model().objects.create_user(username="google-seller", password="test")
        profile = SellerProfile.objects.create(user=owner, business_name="Test shop")
        self.shop = Shop.objects.create(
            owner=owner,
            seller_profile=profile,
            name="Test shop",
            slug="test-google-shop",
            is_active=True,
            is_approved=True,
            google_place_id="ChIJtest",
        )
        self.url = reverse("marketplace-shop-google-rating", kwargs={"slug": self.shop.slug})
        self.client = APIClient()

    def tearDown(self):
        cache.clear()

    @patch("apps.marketplace.views.get_google_rating")
    def test_public_endpoint_returns_only_rating_metadata_without_caching(self, fetch):
        fetch.return_value = {"rating": 4.7, "review_count": 23, "reviews_url": "https://maps.google.com/test"}
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertEqual(response.json(), fetch.return_value)
        fetch.assert_called_once_with("ChIJtest")

    @patch("apps.marketplace.views.get_google_rating")
    def test_unapproved_or_inactive_shop_is_not_exposed(self, fetch):
        for field in ("is_approved", "is_active"):
            setattr(self.shop, field, False)
            self.shop.save(update_fields=[field])
            self.assertEqual(self.client.get(self.url).status_code, 404)
            setattr(self.shop, field, True)
            self.shop.save(update_fields=[field])
        fetch.assert_not_called()

    @patch("apps.marketplace.views.get_google_rating")
    def test_rating_requests_are_throttled(self, fetch):
        fetch.return_value = {"rating": None, "review_count": None, "reviews_url": None}
        for _ in range(30):
            self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertEqual(self.client.get(self.url).status_code, 429)
        self.assertEqual(fetch.call_count, 30)

    def test_place_id_is_saved_validated_and_available_publicly(self):
        serializer = ShopSerializer(self.shop, data={"google_place_id": "ChIJnew"}, partial=True)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        serializer.save()
        self.assertEqual(PublicShopSerializer(self.shop).data["google_place_id"], "ChIJnew")
        invalid = ShopSerializer(self.shop, data={"google_place_id": "https://google.com"}, partial=True)
        self.assertFalse(invalid.is_valid())
        self.assertIn("google_place_id", invalid.errors)
