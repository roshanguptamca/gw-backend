# SecureWise Phase 5 execution evidence

**Date:** 2026-10-10  
**Repository branch:** `feature/securewise-autopentest-foundation`  
**Target:** local controlled fixture at `tests/fixtures/securewise-autopentest-api/`  
**Docker Engine:** Docker Desktop 29.2.0

## Deterministic planning and approved execution

The opt-in test
`SECUREWISE_RUN_DOCKER_INTEGRATION=1 pytest tests/securewise/test_autopentest_worker.py -k approved_planner_flow -q -s`
passed against the controlled, intentionally vulnerable local fixture. Its
sanitized result was:

```json
{
  "ai_mode": "disabled",
  "approved_tests_executed": 2,
  "confirmed_ownership_result": "confirmed_vulnerability",
  "passing_role_result": "passed",
  "planning_status": "completed_with_warnings",
  "runtime_cleanup": "verified",
  "unapproved_test_executed": false,
  "unified_findings": 1
}
```

The test created an AutoPentest planning session through the authenticated API
with explicit repository authorization, exact loopback scope, and encrypted
synthetic bearer credentials. The queued job was claimed through the worker
queue entry point; deterministic planning discovered three OpenAPI operations
and emitted both supported and explicitly unsupported proposals. No AI
provider was configured or called.

The user-review API approved only the object-ownership and function-role
proposals. The session was then re-queued for approved execution. The existing
isolated Docker runtime built and started the fixture; the existing
authenticated API adapter issued bounded read-only requests. It confirmed
cross-user access to the deliberately exposed invoice data (CWE-639), passed
the admin-only role control, persisted one unified finding, and did not run the
unapproved unauthenticated-access proposal. The session completed with
warnings because unsupported proposals remain explicitly unexecuted. The test
compared pre/post Docker resource inventories and verified cleanup of runtime
containers, request containers, runtime network, and temporary image.

This Phase 5 integration uses `process_next_job()` within pytest to exercise the
existing queued worker entry point. It is not a separate operating-system
worker-process test for this new planning-and-approval path. Phase 4's evidence
separately verifies the worker management command and browser scan across
independent processes; production worker execution remains unverified.

## AI mode, safety, and budget configuration

Deterministic planning and approved execution work without a paid AI provider.
The optional worker-side ranker can only annotate an existing deterministic
proposal key; it cannot create executable tests, URLs, commands, scripts, or
parameters. It receives sanitized framework/language labels, safe endpoint
paths/methods, and candidate identifiers, not source code, OpenAPI
descriptions, repository URLs, authentication credentials, or finding
evidence. Redirects are disabled and endpoint DNS results must be public.
Provider status, token usage, and estimated cost are audited without logging
the prompt or API key.

Optional worker environment:

- `SECUREWISE_AI_PLANNER_URL`: HTTPS OpenAI-compatible structured-JSON endpoint.
- `SECUREWISE_AI_PLANNER_API_KEY`: worker-only provider key.
- `SECUREWISE_AI_PLANNER_MODEL`: configured model identifier.
- `SECUREWISE_AI_MAX_COST_USD`: per-request estimated budget ceiling.
- `SECUREWISE_AI_INPUT_COST_PER_1K` and
  `SECUREWISE_AI_OUTPUT_COST_PER_1K`: provider/model token rates in USD per
  1,000 tokens.
- `SECUREWISE_AI_MAX_INPUT_TOKENS`: optional input-token ceiling, capped at
  12,000 (default 8,000).
- `SECUREWISE_AI_MAX_OUTPUT_TOKENS`: optional output-token ceiling, capped at
  2,000 (default 1,200).

All cost-rate and budget values are required to enable an AI call. The
pre-request estimate and post-response usage check enforce a configured
estimate; they cannot guarantee a provider-side billing cap if configured
prices are inaccurate. Invalid, missing or over-budget AI configuration leaves
the deterministic plan available and reports the planner status explicitly.

## Regression validation

- SecureWise backend suite: **365 passed, 4 skipped**.
- Opt-in Docker planner flow: **1 passed**.
- Frontend Vitest suite: **190 passed**.
- Frontend TypeScript/production build: **passed**.
- Django checks and migration drift check: **passed**.
- Oxlint completed with nine warnings in unrelated pre-existing files.

No production provider call, production Linux worker deployment, production
database, or production billing behavior was tested. OpenAPI-based discovery
does not infer arbitrary Django models/permissions, client-side routes, CORS,
business logic, or data sensitivity. Header checks, request-schema mutation,
general sensitive-data inspection, and arbitrary application journeys are
identified as unsupported rather than reported as passed or confirmed.
