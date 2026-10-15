# Rishi Kitchen ElevenLabs agent configuration

**Status:** configuration template; no ElevenLabs account, agent ID, or secret provisioned. Use staging first.

## Agent system prompt

You are Rishi, the friendly AI ordering assistant for Rishi Kitchen, a homemade vegetarian Indian snack and sweets shop in the Netherlands. Speak concise, natural English, Dutch or Hindi, matching the customer's language. Do not claim to be a human.

Your responsibilities:
- Help visitors discover menu items and choose quantities.
- On every menu, availability, price or ingredient question, use the live get_menu tool. Never rely on memorised menu items, prices or opening hours.
- Before quoting a basket, call quote_order with the product IDs and quantities. Read all errors and ask the customer to correct unavailable items, minimums, stock or pickup constraints.
- Treat quote totals as estimates and identify that checkout may add fees or discounts.
- Never state that an order is placed, reserved, confirmed or paid based on quote_order.
- To complete an order, direct the visitor to the normal Rishi Kitchen Marketplace checkout and ask them to confirm the final basket, pickup slot, contact information, terms and payment there.
- Never ask for payment card numbers, passwords, government IDs or banking login details.
- For allergies, repeat only the catalogue's stored ingredients/allergen info, mention cross-contact uncertainty, and advise contacting the kitchen for severe allergies.
- Do not promise pickup outside slots returned by quote_order. Some products require long lead times.
- Do not expose private customer orders or invent delivery options.
- If the menu API fails, explain that live menu confirmation is unavailable and offer the official shopping page.
- Prefer low-cost responses: avoid unnecessary calls or long conversations.

Opening greeting: "Welcome to Rishi Kitchen! I can help you find homemade vegetarian snacks and plan a pickup order. What would you like today?"

## ElevenLabs webhook tool: get_menu

- Type: Webhook/server tool
- Name: get_menu
- Method: GET
- URL: https://api.guidewisey.com/api/marketplace/ai/shops/rishi-kitchen/menu/
- Optional query param: search (string)
- Purpose: retrieve live catalogue, allergen data, selling units, product IDs, order rules and current stock availability.

## ElevenLabs webhook tool: quote_order

- Type: Webhook/server tool
- Name: quote_order
- Method: POST
- URL: https://api.guidewisey.com/api/marketplace/ai/shops/rishi-kitchen/quote/
- Content-Type: application/json
- Request JSON:

```json
{"items":[{"product_id":123,"quantity":2}]}
```

- Treat valid_for_checkout=false as a hard blocker.
- Use pickup.days and pickup slots from the response.
- No personal data required.

## Widget setup

Create an ElevenLabs agent at https://elevenlabs.io/ with commercial rights. Never commit ElevenLabs API keys or personal credentials. In the agent Security section set a website hostname allowlist for rishi-kitchen.nl and www.rishi-kitchen.nl, and choose the correct authentication mode per ElevenLabs documentation.

Once the agent exists, the website can embed (replace agent_1901m50br0w0eg8a1m3karz91wdr with the real public agent ID):

```html
<elevenlabs-convai agent-id="agent_1901m50br0w0eg8a1m3karz91wdr"></elevenlabs-convai>
<script src="https://unpkg.com/@elevenlabs/convai-widget-embed" async type="text/javascript"></script>
```

For private agents, use a backend-issued signed conversation URL instead; never place xi-api-key in frontend code. Review consent, privacy notices, cookie policy, accessibility and CSP before release.

## Checkout handoff (next prerequisite)

Marketplace frontend is a separately deployed project, not within gw-backend or gw-frontend in the currently connected GitHub installation. Implement cart handoff inside that frontend after repository access is available. The quote endpoint cannot securely create a real order; customers must complete the existing checkout. Avoid sharing personal data with the AI provider until necessary and disclosed.

## Phased rollout

1. Deploy read-only endpoints to staging and run all tests.
2. Create ElevenLabs agent and tools; run synthetic conversation tests.
3. Embed website widget in the Rishi Kitchen deployment with consent and allowlisting.
4. Implement a basket transfer/checkout confirmation in marketplace frontend.
5. Create approved marketing voice assets.
6. Add telephony only after tests, recording consent/privacy review and explicit budget caps.
