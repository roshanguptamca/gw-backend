# Seller pages and menus

Sellers configure their own pages through **Seller Portal → Pages & menus**.
No menus, labels, promotional strips or seller content are seeded. New pages are
private drafts. Only published pages belonging to active, approved shops are public.

## Page configuration

- `title`, per-shop `slug`, `kind` (`menu`, `enquiry`, `information`), plain-text
  description, optional HTTPS cover and fulfilment notes.
- `position` controls the shop navigation order, with ID as a stable tie-breaker.
- `is_published` controls both public API access and navigation visibility.
- `is_featured` enables a shop-home strip for an open published page.
- `order_deadline` is an optional timezone-aware deadline. The editor accepts the
  seller's browser-local time and sends an ISO timestamp. The customer sees their
  local date/time. Closed pages remain readable but their ordering/enquiry UI closes.
- `products` references the existing seller catalogue. Prices, stock, minimum
  quantities, lead times and checkout validation continue to use existing rules.
  A menu deadline closes that page; it does not make those products exclusive to
  the menu or prevent buying them from the ordinary catalogue. Fulfilment notes
  are informational; actual pickup slots are selected and validated at checkout.

## API

- `GET /api/marketplace/shops/{shop_slug}/pages/`
- `GET /api/marketplace/shops/{shop_slug}/pages/{slug}/`
- `POST /api/marketplace/shops/{shop_slug}/pages/{slug}/enquiries/`
- Seller-owned CRUD: `/api/seller/pages/` and `/api/seller/pages/{id}/`
- Seller-only enquiries: `/api/seller/page-enquiries/` (latest 200) and detail by ID.

Quote submissions store customer contact details, event date, guests, selected
product IDs, page title snapshot and message. Consent is required. Requests are
limited to five per hour per client IP, and the server rejects closed, unpublished,
non-enquiry pages and shops that paused orders. The server validates products
against the same page and seller. This is a durable quote request, not an order or
payment. Sellers respond using the contact details in their dashboard; no automatic
email/WhatsApp notification is sent. Deleting a page preserves its enquiries.
Customer details are never returned by public endpoints.

## Release order

Deploy the backend and run `python manage.py migrate` (migration 0024) before
releasing the matching `gw-marketplace-fe` branch `feat/seller-pages-menus`.
Migration is additive and seeds no seller configuration. Older frontends remain
compatible. A new frontend with an older backend leaves the shop catalogue usable
but page management cannot work until the backend is deployed.

## Validation

- API tests cover shop approval, drafts, authentication, cross-seller isolation,
  per-shop URLs, input validation, public product filtering, deadlines, paused
  shops, enquiry persistence, deletion retention and rate limits.
- Frontend component tests cover configuration, basket quantities, expiry,
  missing pages, retry handling, duplicate drafts and failed saves.
- Browser CI covers 320/390/768/1440px, seller CRUD and guest enquiry submission.
- Local full-stack browser verification uses the actual Django API/database,
  authenticated seller session and CSRF protection for create/publish → public
  navigation → basket → enquiry → seller dashboard, with no request stubs.
