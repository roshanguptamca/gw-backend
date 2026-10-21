# Google shop ratings

Deploy backend and frontend together (backend first). Run `python manage.py migrate` to add `Shop.google_place_id`.

## Activation

1. In Google Cloud, enable Places API (New) on a billing-enabled project.
2. Create a server key restricted to Places API (New) and your outbound server IP where stable. Set `GOOGLE_PLACES_API_KEY` in the backend deployment environment; never use a VITE variable or commit the key.
3. Set a suitable Google API quota and billing alerts. Every configured storefront visit can make one paid Place Details request; no reviews or rating content is persisted or cached. A per-IP throttle limits requests to 30/minute (shared cache needed across workers for a combined limit).
4. Seller portal → Shop details → Google Place ID. Use Google's Place ID finder to identify the exact business. Existing `g.page` review links are write-review links and cannot substitute for a Place ID. Leave the ID blank to disable live rating requests.
5. Save and open the public shop. The endpoint `GET /api/marketplace/shops/<slug>/google-rating/` returns `rating`, `review_count`, `reviews_url`. Only active, approved shops are available. Do not manually seed a rating.

The endpoint requests only `rating,userRatingCount,googleMapsLinks`. Google supplies the review deep link; a Maps Place-ID link is the fallback. It uses a fixed Google host, strict Place-ID validation, no redirects and bounded timeouts. API keys and upstream error bodies are never returned. The response is `Cache-Control: no-store`.

Without a key, valid Place ID, reviews, or available upstream response, the rating/count are null. Shopping remains functional. The frontend keeps a Google link when one is configured, hides stars until a real valid score is available, and does not load a rating on product lists. A blank ID and blank review URL hide the section.

Google Maps attribution and the review-policy link appear beside the displayed data. Ensure the application's published terms/privacy policy incorporates the Google Maps terms and privacy references before activating this feature:
- https://maps.google.com/help/terms_maps.html
- https://policies.google.com/privacy
- https://developers.google.com/maps/documentation/places/web-service/policies

## Validation

Tests mock Google; no live paid request is made by CI. Set the key through the deployment secret manager, configure one verified shop Place ID, and verify the resulting score/deep link against its Google Maps listing before enabling other shops.
