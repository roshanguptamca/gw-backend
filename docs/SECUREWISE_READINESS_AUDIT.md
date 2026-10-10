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
| Remediation recommendations, CWE/OWASP mapping and retest | Partially implemented | Unified `CWE-639` browser finding and endpoint-specific recommendation were persisted; UI exposes evidence and retest linkage | No | `test_autopentest_worker.py`, frontend `AutoPentestPage.test.tsx` | Framework-specific remediation, retest outcome comparison, and broad browser coverage remain incomplete | P1 |
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
customer build scripts are adequately sandboxed.

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
