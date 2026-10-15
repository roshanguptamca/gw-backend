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
