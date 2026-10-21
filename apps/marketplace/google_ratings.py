"""Fetch only live rating metadata; never persist Google Maps content or expose the key."""

import math
import re
from urllib.parse import urlencode, urlsplit

from django.conf import settings

import requests
from rest_framework.throttling import SimpleRateThrottle


class GoogleRatingThrottle(SimpleRateThrottle):
    scope = "google_rating"
    rate = "30/min"

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


def get_google_rating(place_id):
    unavailable = {"rating": None, "review_count": None, "reviews_url": None}
    key = getattr(settings, "GOOGLE_PLACES_API_KEY", "")
    if not key or not place_id or not re.fullmatch(r"[A-Za-z0-9_-]{1,255}", place_id):
        return unavailable
    try:
        result = requests.get(
            f"https://places.googleapis.com/v1/places/{place_id}",
            headers={"X-Goog-Api-Key": key, "X-Goog-FieldMask": "rating,userRatingCount,googleMapsLinks"},
            timeout=(2, 3),
            allow_redirects=False,
        )
        if result.status_code != 200:
            return unavailable
        data = result.json()
        if not isinstance(data, dict):
            return unavailable
        rating = data.get("rating")
        count = data.get("userRatingCount")
        if (
            type(rating) not in (int, float)
            or not math.isfinite(rating)
            or not 1 <= rating <= 5
            or type(count) is not int
            or count < 1
        ):
            return unavailable
        links = data.get("googleMapsLinks")
        review_url = links.get("reviewsUri") if isinstance(links, dict) else None
        if isinstance(review_url, str):
            parsed = urlsplit(review_url)
            if parsed.scheme != "https" or parsed.username or parsed.password:
                review_url = None
        else:
            review_url = None
        return {
            "rating": rating,
            "review_count": count,
            "reviews_url": review_url
            or "https://www.google.com/maps/search/?"
            + urlencode(
                {
                    "api": 1,
                    "query": "Google Maps",
                    "query_place_id": place_id,
                }
            ),
        }
    except (requests.RequestException, ValueError):
        # Do not log upstream exception bodies/URLs, which may contain credentials.
        return unavailable
