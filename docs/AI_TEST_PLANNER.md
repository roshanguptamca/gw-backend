# AI Test Planner

The AI planner should convert discovered routes, permissions, serializers, forms, and views
into safe security test scenarios.

## Safe scenario categories

- authentication gaps
- authorization and IDOR
- CSRF
- session misuse
- upload validation
- SSRF
- open redirects
- rate limiting
- sensitive-data exposure
- security headers
- CORS

## Output shape

The planner should emit structured JSON with:

- `scenario_id`
- `title`
- `category`
- `target`
- `preconditions`
- `test_steps`
- `expected_secure_behavior`
- `possible_vulnerable_behavior`
- `evidence_to_collect`
- `safe_for_local_runtime`
- `safe_for_production`
- `requires_active_testing`
- `destructive`

## Safety rules

- no destructive testing
- no brute force
- no credential attacks
- no third-party targets
- no scope expansion

