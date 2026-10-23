# SecureWise Phase 7 execution evidence

**Branch:** `feature/securewise-autopentest-foundation`
**Environment:** local macOS; provider operations are mocked; Semgrep ran on a controlled local fixture
**Production verification:** none

## Implemented vertical slice

- Added organization-scoped GitHub App installation and callback state records,
  a selected-repository linkage on the existing repository model, and a
  webhook replay ledger that stores no raw webhook payload.
- Added GitHub App connect/callback/list/select/webhook API endpoints.
  Callback state is stored as a digest, expires in ten minutes, is user-bound
  and single-use; first-time association requires an installation created
  during that flow. An installation cannot be rebound to another SecureWise
  organization. Installations reporting a write permission are rejected.
- Installation access tokens are minted for GitHub API use and are not
  persisted or returned. Repository selection is checked against the selected
  installation. Webhooks verify `X-Hub-Signature-256` and suppress repeated
  delivery IDs.
- GitHub App repository scanning uses an API archive at a recorded 40-character
  commit SHA rather than embedding a token in a clone URL. Archive redirects
  are limited to HTTPS `codeload.github.com`; ZIP traversal, symbolic links,
  excessive entry counts and excessive expanded sizes are rejected. The
  existing worker scanner engines and findings pipeline are reused, and this
  repository mode cannot enter the runtime build gate.
- Rejected cross-organization repository references to a Git integration and
  restricted Git credential connectivity tests to organization admins.
- Added a Repositories-page flow to connect an App, load installed repositories,
  choose an organization project and explicitly select repositories.

## Phase 7.1 URL authorization and passive assessment

- Added organization/project-scoped application targets, one-time DNS TXT or
  HTTPS well-known challenges (24-hour expiry, stored SHA-256 challenge
  digests), ownership verification/revocation, and separate explicitly
  approved testing authorizations. Authorization is exact-host, port, allowed
  path, excluded path, passive-method and time bound; revocation of ownership
  revokes active authorizations.
- Added a customer workflow for target registration, ownership proof, separate
  approval, revocation and starting a passive assessment. The UI explains that
  ownership is not permission to test and that external scans require protected
  worker egress. Existing project/scan/finding APIs and models are reused.
- URL scan creation and start/retry validate scope and active authorization.
  URL jobs are claimable only by the registered worker ID declaring the
  `url_egress_restricted` capability. The scanner rechecks authorization and
  worker registration before each request/redirect; it permits only HTTPS on
  ports 443/8443, exact authorized hosts and paths, rejects non-global DNS
  answers, pins connections to validated addresses, validates each redirect,
  ignores proxy environment variables, limits redirects/body/time and sends
  only GET requests. Rate and concurrency limits are applied.
- Customer URL DAST uses one scoped passive HTTP request and header/cookie/CORS
  checks. It does **not** invoke external ZAP or active tests. The actual
  execution mode is recorded. Existing ZAP remains for worker-created isolated
  application runtimes.
- The egress env flag and worker capability are operator declarations, not
  evidence of a host firewall. This environment has no verified network-layer
  egress policy, so `SECUREWISE_URL_EGRESS_ENFORCED` was not enabled for a live
  scan. The code path is tested with controlled mocks only; no real URL request
  or customer target was scanned.
- Semgrep `1.168.0` actually scanned the intentionally vulnerable fixture;
  `ScannerRunner` persisted findings from that run. The test confirms fixture
  Docker/package installation scripts did not execute. This is local scanner
  evidence, not a private GitHub repository scan.

## Verification performed

| Check | Result |
|---|---|
| `pytest tests/securewise/test_application_targets.py -q` | 14 passed; includes real Semgrep fixture scan, persistence, scope/tenant/expiry/revocation and mocked network checks |
| Full backend `pytest -q` | 1,035 passed, 6 skipped, 15 failed outside SecureWise. Failures are in marketplace/resume PDF/email tests because local macOS lacks `libgobject-2.0-0`; no SecureWise failures were reported. |
| Django `manage.py check` | Passed; no issues |
| `manage.py makemigrations --check --dry-run` | Passed; no migration drift |
| Python compile check | Passed for SecureWise app and new tests |
| Frontend `npm test -- --run` | 199 passed across 16 test files |
| Frontend `npm run typecheck` | Passed |
| Frontend `npm run build` | Passed |
| Frontend `npm run lint` | Passed with 8 warnings in existing unrelated files |
| Frontend Prettier check | Passed in the frontend commit hook |
| `git diff --check` | Passed for the final backend changes |

Tests exercise callback state/permissions, installation scoping, repository
selection and immutable GitHub identity, webhook HMAC/replay/suspension
handling, archive extraction, commit pinning, runtime-build exclusion, and Git
credential tenant boundaries. GitHub API responses and archive retrieval are
mocked. These tests do not verify a live GitHub App, private repository
permissions, real webhook delivery, or live remote archive behavior.

The SecureWise targeted backend suite emitted framework/dependency
deprecation and staticfiles warnings. The full backend failures are unrelated
to SecureWise and require the missing system `libgobject-2.0-0` library.
Oxlint reported existing warnings in scan/findings/auth components; none target
the new application-target page.

## Not verified / not implemented

- No production or customer GitHub App credentials were configured. No external
  GitHub API request, private customer repository scan, deployed callback, or
  webhook delivery was performed. The Semgrep fixture run does not satisfy the
  live private-repository acceptance criterion.
- Static source is processed in the existing shared worker execution trust
  domain. Repository build scripts are not run by the GitHub App path, but
  per-job VM/microVM isolation and scanner parser containment are not verified.
- Scanner versions/rule-set provenance and all commercial SaaS license
  obligations were not audited for this change.
- URL target registration, DNS TXT/HTTPS challenge flow, separate legal
  authorization, request-level SSRF/scope protections and passive scanner
  integration are implemented and locally tested, but live DNS/HTTPS proofs
  and real target requests were not run. Network-layer egress restrictions and
  the worker's asserted capability are not independently verified; external
  scans must remain disabled until a dedicated worker egress policy is
  installed and verified.
- No live passive assessment against a controlled local HTTPS fixture was
  performed; loopback/private destinations are deliberately rejected. Network
  tests use mocked resolution and transport.
- Organization invitations and the requested owner/admin/member/viewer role
  lifecycle, combined project-level code+URL reports, customer deletion,
  retention, signed object-storage links, data region, and deployed tenant
  isolation evidence remain outstanding.
- Dedicated Linux/rootless worker isolation, verified egress firewall,
  filesystem quota, production shared database and deployment/rollback
  verification remain unverified. Do not describe SecureWise as
  production-ready or customer-beta ready based on these local checks.

Prior independent worker and controlled Docker/browser fixture evidence is
preserved in the Phase 2–6 execution evidence. No Phase 7 real Docker fixture
or public target scan was run.
