# SecureWise readiness audit

**Audit date:** 2026-10-10
**Repositories inspected:** `roshanguptamca/gw-backend` and the local
`roshanguptamca/securewise-frontend` checkout.
**Branch:** `feature/securewise-autopentest-foundation`

## Scope and evidence limits

This audit is based on source, documentation, and tests present in the checked-out
branches. No production account, Render service, live database, deployed worker,
or production telemetry was available to verify behavior. Consequently, no
capability below is marked production-verified. A passing unit test is evidence
for that test case only; it is not proof of deployed scanner availability or
production readiness. Docker-backed scan execution must be verified on the
dedicated worker host.

“Working locally” means the listed focused automated test exercises the behavior.
The Phase 2 execution evidence specifically identifies which Docker-backed
workflows were run against the controlled fixture; it is not production evidence.

## Capability matrix

| Capability | Implementation status | Working locally | Verified in production | Tests available | Blockers | Priority |
|---|---|---|---|---|---|---|
| Organization, membership, project and repository control plane | Implemented | API/model tests exist; no production-like deployment verified | No | `tests/securewise/test_api.py`, `test_securewise.py` | Requires deployed database/auth configuration and tenant-isolation smoke test | P1 |
| Scan/finding/report data model and report generation | Implemented | Unit/API tests available | No | `test_services.py`, `test_api.py` | Report output still needs a real production-data review | P1 |
| Repository cloning and short-lived Git credentials | Implemented | Mock/local-path tests available | No | `test_repository_scanner_helpers.py`, `test_services.py` | Dedicated worker secrets handling and Git provider integration need deployment validation | P1 |
| Application discovery (Python, Node, PHP, Ruby, Java, Go) | Implemented | Detector and Smart Scan tests available | No | `test_smart_repo_scan.py` | Coverage is signature-based; multi-service runtime and environment provisioning remain limited | P1 |
| SAST, SCA, secret and IaC scanners | Implemented, with tool-dependent fallbacks | Scanner tests mock tool availability; a real binary run was not observed | No | `test_scanners.py`, `test_mode_labels.py` | Production tool versions, signatures, and fallback visibility require worker image validation | P1 |
| API security analysis | Partially implemented (static OpenAPI, bounded authenticated GET/HEAD checks, and deterministic browser journeys) | Separate Django API and worker processes ran authenticated browser journeys against the controlled Docker fixture; cross-user IDOR was confirmed and role/session controls passed | No | `test_scanners.py`, `test_autopentest_worker.py`, opt-in browser Docker integration | Browser planning requires reviewed OpenAPI extensions; no general source-route inference or AI-authored executable tests | P0 |
| Container scanning | Implemented for Docker-image vulnerability scanning | Controlled fixture scanned by real Trivy; runtime-built image reused | No | `test_scanners.py`, opt-in `test_docker_integration.py` | Dedicated Linux worker deployment and broader image compatibility remain unverified | P0 |
| Docker runtime build/start/health/cleanup | Implemented for supported single-container apps | Fixture image built, started, health-checked over internal network, and cleaned up | No | `test_smart_repo_scan.py`, opt-in `test_docker_integration.py` | Compose/multi-service apps, required secrets, and a dedicated Linux worker remain unverified | P0 |
| DAST | Partially implemented | Real OWASP ZAP baseline completed against the controlled fixture | No | `test_scanners.py`, opt-in `test_docker_integration.py` | Baseline is passive; no active testing, authenticated crawling, or production execution evidence | P0 |
| Worker scheduling and capability registration | Partially implemented (database-backed queue) | A separate `securewise_worker` OS process claimed an HTTP API-submitted browser job using a persistent isolated SQLite database; heartbeat, restart queue processing, and expired-lease recovery were verified locally | No | `test_autopentest_worker.py`, `test_api.py`, opt-in authenticated API and browser Docker integrations | Local macOS verification only; production Linux worker, durable broker, and deployed database remain unverified | P0 |
| Worker cancellation, timeouts and cleanup | Partially implemented | Queued cancellation survived worker restart; browser assessment completed with runtime/container/network cleanup; timeout and cancellation code paths have unit coverage | No | `test_autopentest_worker.py`, `test_smart_repo_scan.py`, opt-in browser Docker integration | Mid-journey cancellation and forced host/process death cleanup were not demonstrated; hard worker termination can still orphan host Docker resources | P0 |
| AutoPentest authorization and exact host/port scope records | Partially implemented | API tests validate consent, exact loopback scope and encrypted synthetic identities; live requests were limited to the built runtime alias and approved port | No | `test_autopentest_worker.py` | Runtime builds still execute reviewed Dockerfiles on the Docker host; do not allowlist arbitrary repositories | P0 |
| AutoPentest deterministic planner | Partially implemented | Controlled OpenAPI fixture drives API and browser journeys, including two-user ownership, role, logout, explicit session expiration, and cookie checks | No | `test_autopentest_worker.py` | Requires a reviewed OpenAPI extension; arbitrary frontend routes, Django permission/model analysis, CORS and business logic are not inferred | P1 |
| AutoPentest security inventory, proposal review and coverage | Implemented for deterministic OpenAPI/browser metadata planning; broader application analysis remains partial | Worker-backed fixture plan inventories endpoints/auth/roles, persists actionable proposals, enforces safe edits/approval/rejection, executes only approved supported cases, and reports executed/untested coverage | No | `test_autopentest_worker.py`, `AutoPentestPage.test.tsx`, opt-in Docker planner integration | Route/model discovery depends on OpenAPI metadata; unsupported schema-mutation, headers and sensitive-data checks are reported but not executed | P0 |
| Optional AI-assisted proposal ranking | Implemented as a disabled-by-default structured JSON annotation adapter; AI cannot create or execute tests | Deterministic planning works without provider credentials; mocked provider test verifies allowlisted proposal keys, bounded output, token/cost estimates and minimized prompt content | No | `test_autopentest_worker.py` | Real provider and billing behavior are unverified; configure worker-side HTTPS endpoint, API key/model and accurate provider token rates/budget; cost is an estimate, not a provider billing guarantee | P2 |
| AutoPentest execution adapters | Partially implemented | Read-only API checks and real Playwright/Chromium journeys ran against the isolated Docker fixture; a separate worker process processed the browser session submitted through HTTP | No | `test_autopentest_worker.py`, opt-in API and browser Docker integrations | Browser journeys are fixture-declarative; unsupported browser flows are skipped, and no destructive or general state-changing requests are supported | P0 |
| Finding verification and evidence | Partially implemented | The browser fixture IDOR was confirmed only after a second synthetic user rendered the first user's protected invoice marker; role, logout, server-side session expiration, and cookie controls passed; sanitized screenshots/traces and unified finding persisted | No | `test_autopentest_worker.py`, opt-in browser Docker integration | Verification depends on explicit OpenAPI extensions and synthetic fixture expectations; evidence is representative only of those test identities/data | P1 |
| Remediation recommendations, CWE/OWASP mapping and retest | Partially implemented | Unified `CWE-639` browser finding and endpoint-specific recommendation were persisted; retests now summarize fixed, still confirmed, suspected, newly confirmed, and not-retested cases | No | `test_autopentest_worker.py`, frontend `AutoPentestPage.test.tsx` | Framework-specific remediation and broad browser coverage remain incomplete | P1 |
| SecureWise web UI (scans, findings, reports, progress) | Implemented | Existing Vitest page tests available | No | Frontend `ScanDetailPage.test.tsx`, `ScansPage.test.tsx`, `FindingDetailPage.test.tsx` | Frontend production deployment not checked | P1 |
| AutoPentest UI | Partially implemented | Browser mode supports synthetic usernames/passwords, deterministic journey selection, progress, screenshots/traces, findings, and retest linkage; frontend tests/build pass locally | No | Frontend `AutoPentestPage.test.tsx` | Journeys are selected from reviewed OpenAPI metadata; no route discovery editor or production deployment verification | P1 |
| Controlled local vulnerable fixture | Implemented for development | Fixture is local-only; Docker execution requires the worker | No | `tests/fixtures/securewise-autopentest-api/` | Never expose the fixture publicly; fixture findings are synthetic and not production evidence | P2 |

## Findings from code inspection

- The backend already had reusable discovery, runtime, scanner, scan-result,
  progress, report, and finding components. This work extends those surfaces
  rather than replacing the current Smart Scan.
- The original scan API launched daemon threads in Django. The scan and
  AutoPentest APIs now enqueue work for a separate management-command worker.
- Generated runtime Dockerfiles previously ignored dependency failures and
  selected fixed runtime versions. They now use project metadata where present,
  select a detected package manager/lockfile, and fail the image build when
  dependency installation fails.
- Runtime and temporary container images now use unique tags. Runtime-built
  images are supplied to Trivy, and cleanup is owned by the runtime lifecycle.
- Docker CLI detection is distinct from daemon reachability. ZAP baseline
  execution is separately identified from the requests-based passive fallback.
- The API scanner only reads OpenAPI/Swagger specifications. It does not make
  live API requests. Its engine metadata and UI explicitly label it as static
  analysis.
- Taxonomy references are loaded from the versioned
  `security_taxonomy_v1.json` dataset. The fabricated `A10:2025` value on a
  health-check recommendation was removed; a health endpoint recommendation is
  not assigned a security CWE/OWASP category.

## Phase 5 planner scope

The worker can create a security inventory from static discovery and reviewed
OpenAPI metadata, including framework/language labels, endpoint methods,
declared authentication, role/ownership annotations, browser journeys,
existing findings and scanner limitations. It deliberately does not parse or
persist arbitrary source text, inferred ORM models, or OpenAPI descriptions.
Deterministic proposals include executable unauthenticated, ownership, role,
and supported browser checks, plus explicitly unsupported schema/header and
sensitive-data review cases. Users can edit only planner-declared safe query
parameters, approve or reject proposals, and separately queue approved
supported tests. Existing authenticated API and Playwright adapters are reused;
arbitrary AI output is never executable.

AI is optional and disabled by default. The worker accepts an OpenAI-compatible
JSON endpoint through `SECUREWISE_AI_PLANNER_URL`,
`SECUREWISE_AI_PLANNER_API_KEY`, and `SECUREWISE_AI_PLANNER_MODEL`. Before an
AI call, operators must also configure `SECUREWISE_AI_MAX_COST_USD`,
`SECUREWISE_AI_INPUT_COST_PER_1K`, and
`SECUREWISE_AI_OUTPUT_COST_PER_1K`. Optional
`SECUREWISE_AI_MAX_INPUT_TOKENS` (default 8,000, capped at 12,000) and
`SECUREWISE_AI_MAX_OUTPUT_TOKENS` (default 1,200, capped at 2,000) provide
token ceilings. Cost rates and resulting limits are estimates that must match
provider/model pricing; they do not guarantee provider-side billing caps.
Provider redirects/private-address DNS results are rejected. These settings
and any API key belong only in the worker environment, never in the Django web
or customer-runtime container. AI output can annotate only existing
deterministic proposal keys and cannot provide URLs, commands, scripts, or test
parameters.

## Production-readiness conclusion

SecureWise has a substantial control plane and useful static scanning. Real
Docker build/start, health detection, Trivy image scanning, ZAP baseline
execution, findings persistence, and cleanup have now been verified locally
against the controlled fixture (see
[`SECUREWISE_PHASE2_EXECUTION_EVIDENCE.md`](SECUREWISE_PHASE2_EXECUTION_EVIDENCE.md)).
The authenticated API fixture path is also verified locally: an API-created
session was claimed through the existing queue entry point, the fixture was
built and scanned using real Docker requests, the deliberate IDOR and passing
role controls were evidenced, and temporary resources were removed (see
[`SECUREWISE_PHASE3_EXECUTION_EVIDENCE.md`](SECUREWISE_PHASE3_EXECUTION_EVIDENCE.md)).
Phase 4 additionally verified a separately running `securewise_worker`
management-command process against a persistent isolated local database, with
an HTTP API-submitted browser job, a confirmed fixture authorization finding,
passing controls, heartbeat, queued-job restart, queued cancellation, expired
lease recovery, and Docker cleanup (see
[`SECUREWISE_PHASE4_EXECUTION_EVIDENCE.md`](SECUREWISE_PHASE4_EXECUTION_EVIDENCE.md)).
Phase 5 adds worker-generated inventories and reviewable deterministic
proposals, optional AI annotations, safe-parameter edits, explicit
approve/reject actions, and an execution action that queues only supported
approved proposals. The Docker fixture verified a planned two-user ownership
test and role test: only those approved checks ran, the ownership defect was
confirmed, the role control passed, and the unified finding and cleanup were
verified (see
[`SECUREWISE_PHASE5_EXECUTION_EVIDENCE.md`](SECUREWISE_PHASE5_EXECUTION_EVIDENCE.md)).
This does not verify the separately deployed Linux worker, production
database/queue, production scanner readiness, or production behavior; those
remain **unverified**.
This is not a production readiness certification or evidence that untrusted
customer build scripts are adequately sandboxed. Phase 6 adds fail-closed
exact-content approval and additional tenant/worker controls, but it does not
make Docker builds a sandbox or verify the dedicated Linux deployment.

## Phase 6 private-beta controls

| Capability | Implementation status | Working locally | Verified in production | Tests available | Blockers | Priority |
|---|---|---|---|---|---|---|
| Runtime build approval | Implemented as exact repository-content digest gate | Digest match/mismatch and legacy ID-only rejection tested | No | `test_smart_repo_scan.py`, `test_autopentest_worker.py` | Docker build scripts still execute on the daemon host with network access; no production digest process, rootless daemon, or egress controls verified | P0 |
| Repository/project/scan/policy/report association checks | Implemented for serializer input | Cross-project repository scan and cross-tenant report/scan mismatch rejected by API tests | No | `test_api.py` | Full production penetration test and cross-tenant review of every API surface still required | P0 |
| Worker resource/readiness monitoring | Partially implemented | Heartbeats persist best-effort process and disk/load metrics; tenant-scoped queue and engine metrics API tested | No | `test_api.py`, `test_autopentest_worker.py` | No automated alert delivery, cleanup reaper, Docker daemon/container resource metrics, or high-scale queue guarantees | P1 |
| Worker service isolation | Implemented in worker image/Compose/systemd templates | Config and targeted regression checks; host systemd/rootless-Docker deployment not run here | No | `docker-compose.yml`, `Dockerfile.securewise-worker` | Docker socket grants daemon authority; daemon, network egress and disk quotas require dedicated Linux host configuration and verification | P0 |
| DAST target scope | Partially implemented for private beta | Unscoped user-supplied targets are blocked; controlled local runtime integrations remain the only supported dynamic target | No | `test_scanners.py`, opt-in `test_docker_integration.py` | External DAST is intentionally unavailable; host firewall/redirect containment for external targets has not been implemented or verified | P0 |
| Private-beta onboarding | Partially implemented in existing AutoPentest UI | Frontend unit/build verification recorded after the focused UI changes | No | Frontend `AutoPentestPage.test.tsx` | UI cannot attest to production host isolation or repository digest approval; operator review is still required | P1 |

Runtime approval uses `SECUREWISE_TRUSTED_RUNTIME_CONTENT` in the form
`repository-uuid=sha256`, additionally requires the opt-in
`SECUREWISE_RUNTIME_BUILDS_ENABLED=true`, and rejects symlinks and oversized
trees. The repository-ID-only setting
`SECUREWISE_TRUSTED_RUNTIME_REPOSITORIES` no longer authorizes runtime
execution. Hashes are operator-managed and do not replace source review.
External/user-supplied DAST targets are also blocked in the beta; only
worker-generated internal runtime targets may be tested. See
[`SECUREWISE_PRIVATE_BETA.md`](SECUREWISE_PRIVATE_BETA.md) for threat
boundaries, worker deployment and rollback procedures.

Phase 6 execution results and sanitized scanner output are recorded in
[`SECUREWISE_PHASE6_EXECUTION_EVIDENCE.md`](SECUREWISE_PHASE6_EXECUTION_EVIDENCE.md).
The full SecureWise backend suite passed locally (375 passed, 4 skipped),
including one opt-in Docker Desktop fixture run with real Trivy and OWASP ZAP.
The frontend suite passed (193 tests), TypeScript/production build passed, and
lint exited successfully with nine existing warnings. This does not include
production verification or a dedicated Linux/rootless-Docker worker test.

## Phase 7 customer code/URL assessment status

Phase 7 adds a GitHub App static-scanning foundation while preserving the
Phase 6 external DAST block. Source inspection and mocked API tests are not
evidence of a working deployed GitHub App, a customer private-repository scan,
or production tenant isolation.

| Capability | Implementation status | Working locally | Verified in production | Tests available | Blockers | Priority |
|---|---|---|---|---|---|---|
| GitHub App installation and organization binding | Partially implemented: admin-bound expiring state, callback validation, write-permission rejection, non-rebind rule | Mocked provider API tests pass | No | `tests/securewise/test_github_app.py` | App credentials, reachable setup callback, live installation and customer permission verification | P0 |
| Selected GitHub repositories | Partially implemented: installation-scoped listing and explicit selection reuse `SecureWiseRepository` | Mocked list/select API tests pass | No | `test_github_app.py`, frontend `RepositoriesPage.test.tsx` | Live account/private repository sync and removal UX | P0 |
| Private static source scanning | Partially implemented: installation token and bounded commit archive path; exact commit SHA is recorded | Mocked commit/archive and safe extraction tests pass; no real scanner ran against a private repository | No | `test_github_app.py`, existing scanner/worker suites | Live private repository test; per-job scanner isolation; scanner version/license audit; production worker | P0 |
| GitHub webhook security | Partially implemented: HMAC signature validation, payload size limit, delivery replay ledger, suspend/remove state | Local cryptographic fixture test passes | No | `test_github_app.py` | Public webhook endpoint, configured secret, live signed delivery and broader event handling | P1 |
| Repository/integration tenant association | Implemented for submitted repository relations; legacy integration test action is admin-only | Cross-org reference and viewer denial tests pass | No | `test_api.py` | Full deployed endpoint/access/export audit remains outstanding | P0 |
| URL target ownership and authorization | Missing; no customer target registration or legal authorization record | No | No | Existing external target block tests only | TXT/HTTPS challenge, expiry/replay, host/port/path scope, legal approval, DNS rebinding and egress enforcement | P0 |
| Authorized passive URL assessment | Missing for external targets; Phase 6 DAST block remains | No public/customer target requests run | No | Existing DAST tests cover rejection, not authorized customer scanning | Request-level scope/redirect/DNS defenses and network egress controls | P0 |
| Unified code+URL reports and customer dashboard | Partially implemented: existing scan report reused; GitHub App selection added to Repositories | Full frontend regression suite, typecheck and production build pass; reports remain scan-bound | No | Existing report tests; frontend repository tests | URL findings, project-level combined report, full onboarding, downloaded data/retention controls | P1 |
| Tenant roles and invitations | Partially implemented: existing owner/admin/security_engineer/developer/auditor roles reused | Prior API tests plus new cross-reference checks | No | `test_api.py` | Requested member/viewer semantics and secure invitation/removal lifecycle not delivered | P1 |

The Phase 7 GitHub App path is static-only: it does not run repository build,
install or startup scripts, and it cannot use the runtime-build gate. Scanner
processes still share the existing worker trust domain; no per-job VM/microVM
or scanner-host isolation has been demonstrated. App state, archive extraction,
webhook, and selected repository tests mock GitHub; no real GitHub API call or
private customer repository scan took place.

No URL verification/authorization capability was added. Do not bypass the
external DAST restriction by submitting `target_url` directly. Ownership is
not legal authorization, and neither is currently captured for customer URLs.

Phase 7 execution detail is recorded in
[`SECUREWISE_PHASE7_EXECUTION_EVIDENCE.md`](SECUREWISE_PHASE7_EXECUTION_EVIDENCE.md),
with customer constraints in
[`SECUREWISE_CUSTOMER_SECURITY_MODEL.md`](SECUREWISE_CUSTOMER_SECURITY_MODEL.md)
and setup limitations in
[`SECUREWISE_CUSTOMER_ONBOARDING.md`](SECUREWISE_CUSTOMER_ONBOARDING.md).

## Validation performed for this change

- The controlled integration test passed with Docker Desktop 29.2.0: Trivy
  scanned the runtime-built image (268 findings), ZAP baseline completed (1
  finding), 275 findings were persisted across engines, and the runtime image
  and container were removed.
- The complete SecureWise backend suite passed: 350 passed, 1 skipped.
- Django system checks and migration drift checks pass.
- The dedicated worker image built successfully with Docker CLI 27.5.1 and
  Trivy 0.72.0. The Docker CLI and daemon are separately detected.
- Frontend production build/typecheck passed, and all 185 Vitest tests passed.
- The complete backend suite reported 983 passed, 3 skipped, and 15 failed.
  All 15 failures are in marketplace/resume PDF-dependent tests because
  WeasyPrint cannot load native `libgobject-2.0-0` on this macOS host; the
  SecureWise-focused backend tests passed separately.
- Phase 3 SecureWise backend suite passed: 356 passed, 2 Docker integrations
  skipped by default. The opt-in authenticated API Docker integration passed
  separately and recorded one confirmed IDOR finding, three passing
  authorization cases, and cleanup of the runtime, image, network, and
  request containers.
- At Phase 3 completion the complete frontend suite passed (186 tests) and the
  production build/typecheck passed. Independent worker and browser checks
  were still outstanding at that point; Phase 4 results are recorded
  separately below and in the Phase 4 evidence file.
- Phase 4 SecureWise backend regression suite: 359 passed, 3 Docker tests
  skipped by default. The opt-in real Playwright Docker integration passed.
- Phase 4 frontend suite: 188 tests passed; TypeScript/production build passed.
  Oxlint passed with nine warnings in unrelated existing files; no warning
  targeted the changed AutoPentest files.
- Django system checks, migration drift checks, JavaScript syntax check, and
  whitespace validation passed.
- Phase 4 verified a real separate-process worker/API run on an isolated
  persistent local database and real browser execution against the controlled
  fixture. Queue restart, cancellation, expired-lease recovery, and cleanup
  were also exercised locally. Production behavior remains unverified.
- Phase 5 SecureWise regression suite: 365 passed, 4 Docker integrations
  skipped by default. The opt-in planner Docker integration separately passed
  with Docker Desktop 29.2.0: deterministic planning required no AI provider,
  two approved API tests executed, one CWE-639 ownership issue was confirmed,
  one role test passed, an unapproved test did not execute, and temporary
  containers, image and network were cleaned up.
- Phase 5 frontend regression suite: 190 tests passed; TypeScript and
  production build passed. Oxlint completed with nine warnings in unrelated
  existing files. Django checks and migration drift checks passed. Real AI
  provider execution, provider billing behavior and production deployment
  remain unverified.
