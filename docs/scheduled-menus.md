# Scheduled pickup menus

Deploy the backend first and run `python manage.py migrate` (migration 0021), then deploy the companion frontend. No API keys, paid services, cron jobs or additional workers are needed. Existing orders have no menu association and keep the regular checkout flow.

## Seller

Seller Portal → Sales → Scheduled menus. Create a draft or publish a menu with existing active/approved products, a pickup date and same-day time window, an ordering deadline, slot length, total quantity capacity and maximum orders per slot. Enter dates/times in the displayed shop timezone; the menu saves that timezone independently from future shop-setting changes.

Capacity counts ordered selling units: one pack, tray or portion is one unit. Product prices, stock, minimum quantities and preparation lead times still apply. Reports additionally show physical pieces and total weight/volume where product snapshots support them.

After any order is placed, the menu's products, pickup date/time and slot length are immutable. Create a new menu for rescheduling. Capacity cannot be reduced below reservations. Pause stops new menu orders. Records are retained rather than deleted.

Preparation & pickups shows confirmed quantities separately from pending requests, with a customer pickup list and separate CSV exports. Cancelled and rejected orders are excluded. Reports and exports are private to the seller's shop.

## Buyer

Upcoming published menus appear on the shop storefront above regular products. Choose a menu, add products, and choose a menu pickup slot at checkout. Menu context is persisted in the cart and carried through product detail links.

This release supports one menu or one regular order per shop in a cart. Switching requires explicit confirmation and replaces only that shop's items; other shops remain. Menu orders are pickup only. Regular catalogue orders remain available independently: publishing a menu does not make its products globally menu-only.

Deadlines and capacity are checked again at order creation. A closed/full menu or unavailable slot rejects that shop's order without stock changes. The buyer can refresh pickup times or choose another menu.

## API and integrity

- `GET /api/marketplace/shops/{slug}/scheduled-menus/`: upcoming active menus with aggregate availability; no customer data.
- `GET /api/marketplace/shops/{slug}/pickup-slots/?product_ids=1,2&scheduled_menu_id=7`: menu slots with lead time, cutoff and capacity checks.
- Existing `POST /api/marketplace/orders/` accepts optional `scheduled_menu_id` alongside `pickup_slot_start`.
- `GET/POST /api/seller/scheduled-menus/` and `GET/PATCH /api/seller/scheduled-menus/{id}/`: seller-owned menus.
- `GET /api/seller/scheduled-menus/{id}/preparation/`: confirmed quantities, pending quantities and pickup list.

All order creation and menu edits share a shop row lock. Duplicate product lines are aggregated before stock/rule/capacity checks. Status updates re-read orders under the same lock, preventing stale updates from resurrecting released reservations. Pending and all other non-cancelled/non-rejected orders consume batch capacity, including completed orders. A cart is not a reservation.

The order preserves its menu association, title/ID and pickup snapshot. Existing notifications use the pickup snapshot. Reports use item snapshots, not current product names/pack sizes. CSV cells are quoted and formula prefixes are neutralized.

## Validation and scope

Tests cover limits, cutoffs, lead times, duplicate lines, menu membership, seller isolation, immutable schedules, timezone snapshots, reports and stale status transitions. A concurrency test runs only on databases supporting `select_for_update`. Run it against PostgreSQL before production rollout; SQLite cannot validate row-lock behavior. Smoke-test one draft/published menu through real checkout and reporting after deployment.

Not included in this release: delivery menus, recurring menu generation, menu-specific prices, ingredient purchasing plans, B2B quotations or online deposits.
