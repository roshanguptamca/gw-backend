# Rishi Kitchen AI Order Agent — initial backend integration

This first slice adds read-only tools for an ElevenLabs conversational agent. No MCP server is required: ElevenLabs webhook tools can call ordinary HTTPS endpoints.

## Endpoints
- `GET /api/marketplace/ai/shops/<slug>/menu/?search=samosa` returns publicly visible products, DB prices, allergen information, units, order minimums and preparation times.
- `POST /api/marketplace/ai/shops/<slug>/quote/` with `{"items":[{"product_id":123,"quantity":2}]}` returns a non-binding subtotal, validation errors and available pickup slots.

These tools are public and throttled using the existing `marketplace_order` DRF throttle scope. Never return customer/order PII through these endpoints.

## Next steps
1. Configure the ElevenLabs Agent's language handling, system instructions, and two HTTPS webhook tools.
2. Add a website button/widget after checking CORS, CSP, and consent.
3. For final checkout, transfer items to the existing Marketplace cart; require the customer to confirm contact details, pickup slot, order terms and payment using the established checkout UI. Do not let the LLM create orders without an explicit authorization/confirmation flow.
4. Add seller notification through existing order creation, followed by a separate phone connector only if needed.

No secrets or provider credentials belong in the source code.

## Run tests
`python manage.py test tests.marketplace.test_ai_order_agent`

No release or deployment is included in this branch. Review tests and backend response contracts before enabling the agent publicly.

## Guest checkout extension (separate branch from main)

The extension adds an opt-in two-step guest pickup flow. It does **not** change
menu/quote into order-creation endpoints. No account or online payment is created.
Cash at pickup is the only supported payment method. Delivery, coupons, and account
creation are intentionally rejected by this tool contract; use normal checkout for those.

1. `POST /api/marketplace/ai/shops/<slug>/checkout/prepare/` validates customer
   details, selected products and pickup slot. It returns a full `review`, a random
   `confirmation_token` and `expires_at` (15 minutes). It creates no order and
   reserves no inventory. Required body fields: `items`, `customer_name`,
   `customer_phone`, `customer_email` (valid, non-blank). Optional: `customer_note`, `language`
   (`en`, `nl`, `hi`), `pickup_slot_start` (required if the shop schedules pickup).
   `order_type` and `payment_method`, if supplied, must be `pickup` and `cash`.
2. Read back the complete review, share its policy links, and obtain explicit
   customer confirmation **and** policy acceptance. Widget recording consent is
   a separate choice and does not authorize an order. Any changes require a new
   preparation and a fresh confirmation. Missing pickup scheduling means the
   customer must coordinate timing with the seller; no promised time is returned.
3. `POST /api/marketplace/ai/shops/<slug>/checkout/confirm/` takes only
   `{"confirmation_token":"<returned UUID>","confirmed":true,"terms_accepted":true}`.
   It revalidates live prices, stock, seller availability, minimums, selling format,
   product rules and pickup timing. Changed prices/products return `409 QUOTE_CHANGED`;
   expired reviews return `410 CHECKOUT_EXPIRED`. Prepare again and obtain fresh consent.
4. Success returns `201` with a real order number, total, order status, unpaid
   payment status and pickup time. Retrying the **same token** returns `200` with
   that same order and `replayed: true`, without decrementing stock or sending
   notifications again. After an uncertain timeout, never prepare a replacement
   checkout just to retry confirmation. Pending means awaiting seller acceptance.

The ordinary checkout service creates the guest order, invoice, and buyer/seller
notifications. Notifications dispatch only after the confirmation transaction
commits. Hindi conversation requests use the existing English receipt templates;
Dutch requests keep Dutch receipts. The existing invoice is not proof of payment.

Confirmation uses database shop/product/draft row locks; production concurrency
requires PostgreSQL, as used by the deployed backend. SQLite does not implement
`SELECT FOR UPDATE` and may return database-locked errors under concurrent writes.
On such an error retry the same token; no external idempotency cache is used.
The backend validates explicit confirmation flags, but cannot independently prove
the human's conversational intent. The agent must enforce the review/consent
instructions; those flags must never be generated automatically on prepare.

### Deployment and ElevenLabs setup

- Apply migration `0018_agentcheckout` using `python manage.py migrate`.
- Set `MARKETPLACE_AI_GUEST_CHECKOUT_ENABLED=true` and optionally
  `MARKETPLACE_AI_GUEST_CHECKOUT_SHOPS=rishi-kitchen` (comma-separated slugs).
  Checkout stays disabled by default, returning 404; menu and quote are unaffected.
- Schedule `python manage.py cleanup_agent_checkouts` at least hourly to remove
  expired unused reviews and their duplicate customer details. Consumed reviews
  immediately clear payload/review PII; retain consumed tokens for retry safety.
  Confirmation responses contain only a minimal receipt, not customer contact data.
  Review and confirmation responses use `private, no-store`; do not log bodies or tokens.
- On the **existing** agent `agent_1901m50br0w0eg8a1m3karz91wdr`, import the two
  webhook definitions in `docs/elevenlabs/prepare_checkout.json` and
  `docs/elevenlabs/confirm_order.json`. Keep the existing menu/quote tools, but make
  sure `product_id` is an **integer** in their item schema (the API returns numeric IDs).
- Replace the read-only prompt with `docs/elevenlabs/rishi_kitchen_guest_prompt.txt`
  only after backend deployment. Keep English/Hindi/Dutch and the voice/text
  widget, collapsed start, explicit voice-start interaction, and website allowlist.
- Allow clickable policy links on `www.guidewisey.com` alongside the existing shop
  domains. Terms and privacy URLs match the existing marketplace checkout.
- Never put API credentials in tool bodies, source, the widget, or conversation text.
- Test preparation against synthetic data in staging. Test order confirmation only
  against an isolated test shop/database with email delivery stubbed. Do not place
  production test orders. This PR does not deploy or reconfigure the live agent.

Example preparation (synthetic data, substitute a test product ID):

```json
{
  "items": [{"product_id": 123, "quantity": 2}],
  "customer_name": "Test Guest",
  "customer_phone": "+31612345678",
  "customer_email": "guest@example.com",
  "language": "en"
}
```

Validation: `pytest tests/marketplace --migrations --create-db`. New tests cover
review-only behavior, consent rejection, expiry, changed prices, live stock and
seller acceptance, guest/cash restrictions, token replay, invoices, notifications,
feature gating, minimal receipts and expired-draft cleanup.
