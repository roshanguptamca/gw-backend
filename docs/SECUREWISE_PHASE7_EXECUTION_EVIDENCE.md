# SecureWise Phase 7 execution evidence

**Branch:** `feature/securewise-autopentest-foundation`  
**Environment:** local macOS; Phase 7 provider operations are mocked  
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

## Verification performed

| Check | Result |
|---|---|
| `pytest tests/securewise -q` | 390 passed, 4 skipped |
| Django `manage.py check` | Passed; no issues |
| `manage.py makemigrations --check --dry-run` | Passed; no migration drift |
| Frontend `npm test -- --run` | 196 passed across 15 test files |
| Frontend `npm run typecheck` | Passed |
| Frontend `npm run build` | Passed |
| Frontend `npm run lint` | Passed with 8 warnings in existing unrelated files |
| `git diff --check` | Passed in both repositories |

Tests exercise callback state/permissions, installation scoping, repository
selection and immutable GitHub identity, webhook HMAC/replay/suspension
handling, archive extraction, commit pinning, runtime-build exclusion, and Git
credential tenant boundaries. GitHub API responses and archive retrieval are
mocked. These tests do not verify a live GitHub App, private repository
permissions, real webhook delivery, or live remote archive behavior.

The backend suite emitted framework/dependency deprecation and staticfiles
warnings. Oxlint reported existing warnings in scan/findings/auth components;
none target the changed repository page.

## Not verified / not implemented

- No production or customer GitHub App credentials were configured. No external
  GitHub API request, private customer repository scan, deployed callback, or
  webhook delivery was performed.
- Static source is processed in the existing shared worker execution trust
  domain. Repository build scripts are not run by the GitHub App path, but
  per-job VM/microVM isolation and scanner parser containment are not verified.
- Scanner versions/rule-set provenance and all commercial SaaS license
  obligations were not audited for this change.
- URL target registration, ownership challenge, separate legal authorization,
  DNS rebinding/redirect controls, passive external URL scans and active scans
  are not implemented. Existing external DAST blocking remains in effect.
- Organization invitations and the requested owner/admin/member/viewer role
  lifecycle, combined project-level code+URL reports, customer deletion,
  retention, signed object-storage links, data region, and deployed tenant
  isolation evidence remain outstanding.
- Dedicated Linux/rootless worker isolation, egress firewall, filesystem
  quota, production shared database and deployment/rollback verification
  remain unverified. Do not describe SecureWise as production-ready or
  customer-beta ready based on these local checks.

Prior independent worker and controlled Docker/browser fixture evidence is
preserved in the Phase 2–6 execution evidence. No Phase 7 real Docker fixture
or public target scan was run.
