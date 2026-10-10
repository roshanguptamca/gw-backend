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
| API security analysis | Partially implemented (static OpenAPI plus bounded authenticated GET/HEAD checks) | Real requests against the controlled Docker fixture confirmed the deliberate IDOR and passed role controls | No | `test_scanners.py`, `test_autopentest_worker.py` | Live support is limited to reviewed fixture builds and explicit OpenAPI ownership/role metadata; no general schema request generation or Playwright adapter | P0 |
| Container scanning | Implemented for Docker-image vulnerability scanning | Controlled fixture scanned by real Trivy; runtime-built image reused | No | `test_scanners.py`, opt-in `test_docker_integration.py` | Dedicated Linux worker deployment and broader image compatibility remain unverified | P0 |
| Docker runtime build/start/health/cleanup | Implemented for supported single-container apps | Fixture image built, started, health-checked over internal network, and cleaned up | No | `test_smart_repo_scan.py`, opt-in `test_docker_integration.py` | Compose/multi-service apps, required secrets, and a dedicated Linux worker remain unverified | P0 |
| DAST | Partially implemented | Real OWASP ZAP baseline completed against the controlled fixture | No | `test_scanners.py`, opt-in `test_docker_integration.py` | Baseline is passive; no active testing, authenticated crawling, or production execution evidence | P0 |
| Worker scheduling and capability registration | Partially implemented (database-backed queue) | API-submitted fixture job was claimed by `process_next_job()` in the opt-in Docker test; authenticated API capability registered | No | `test_autopentest_worker.py`, `test_api.py`, opt-in authenticated API Docker integration | The worker entry point ran synchronously inside pytest, not as a separate management-command process or Compose/Linux worker; persistent queue recovery and deployment remain unverified | P0 |
| Worker cancellation, timeouts and cleanup | Partially implemented | Cancellation and cleanup paths are tested with mocks | No | `test_autopentest_worker.py`, `test_smart_repo_scan.py` | Cancellation takes effect between engines/cases; hard worker termination can still orphan host Docker resources | P0 |
| AutoPentest authorization and exact host/port scope records | Partially implemented | API tests validate consent, exact loopback scope and encrypted synthetic identities; live requests were limited to the built runtime alias and approved port | No | `test_autopentest_worker.py` | Runtime builds still execute reviewed Dockerfiles on the Docker host; do not allowlist arbitrary repositories | P0 |
| AutoPentest deterministic planner | Partially implemented | Controlled OpenAPI fixture drives the planner | No | `test_autopentest_worker.py` | Current rules inspect OpenAPI security declarations only; routes, Django permissions/models, CORS and business logic are not analyzed | P1 |
| AutoPentest execution adapters | Partially implemented | Real authenticated, read-only API requests ran from isolated temporary containers against the fixture runtime | No | `test_autopentest_worker.py`, opt-in authenticated API Docker integration | No Playwright or session-expiration tests; unsupported operations are skipped, and no state-changing request execution exists | P0 |
| Finding verification and evidence | Partially implemented | One fixture IDOR was confirmed only after protected owner data was returned to a second user; role controls passed; finding and redacted evidence persisted | No | `test_autopentest_worker.py`, opt-in authenticated API Docker integration | Verification depends on explicit OpenAPI extensions; evidence is only as representative as the configured synthetic fixture data | P1 |
| Remediation recommendations, CWE/OWASP mapping and retest | Partially implemented | Unified `CWE-639` API finding and endpoint-specific recommendation were persisted; UI links to unified findings and accepts retest linkage | No | `test_autopentest_worker.py`, frontend `AutoPentestPage.test.tsx` | Framework-specific remediation, retest outcome comparison and Playwright retest coverage remain incomplete | P1 |
| SecureWise web UI (scans, findings, reports, progress) | Implemented | Existing Vitest page tests available | No | Frontend `ScanDetailPage.test.tsx`, `ScansPage.test.tsx`, `FindingDetailPage.test.tsx` | Frontend production deployment not checked | P1 |
| AutoPentest UI | Partially implemented | Consent/scope, synthetic credential submission/clearing, session status and evidence display tests pass locally | No | Frontend `AutoPentestPage.test.tsx` | No route discovery editor or browser/session testing; UI build and frontend deployment remain unverified | P1 |
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
However, the worker command was **not** run as an independent process and the
test database was rolled back. The separately deployed worker service, Linux
worker isolation, production database/queue, production scanner readiness,
and production behavior remain **unverified**.
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
- The complete frontend suite passed (186 tests), and the production
  build/typecheck passed. An independent worker process, Playwright,
  session-expiration testing, and production behavior have not been verified.
