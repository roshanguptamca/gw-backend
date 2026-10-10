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

“Working locally” means the listed focused automated test exercises the behavior
without an external service; it does not mean a real Docker build or scan was
run unless explicitly stated.

## Capability matrix

| Capability | Implementation status | Working locally | Verified in production | Tests available | Blockers | Priority |
|---|---|---|---|---|---|---|
| Organization, membership, project and repository control plane | Implemented | API/model tests exist; no production-like deployment verified | No | `tests/securewise/test_api.py`, `test_securewise.py` | Requires deployed database/auth configuration and tenant-isolation smoke test | P1 |
| Scan/finding/report data model and report generation | Implemented | Unit/API tests available | No | `test_services.py`, `test_api.py` | Report output still needs a real production-data review | P1 |
| Repository cloning and short-lived Git credentials | Implemented | Mock/local-path tests available | No | `test_repository_scanner_helpers.py`, `test_services.py` | Dedicated worker secrets handling and Git provider integration need deployment validation | P1 |
| Application discovery (Python, Node, PHP, Ruby, Java, Go) | Implemented | Detector and Smart Scan tests available | No | `test_smart_repo_scan.py` | Coverage is signature-based; multi-service runtime and environment provisioning remain limited | P1 |
| SAST, SCA, secret and IaC scanners | Implemented, with tool-dependent fallbacks | Scanner tests mock tool availability; a real binary run was not observed | No | `test_scanners.py`, `test_mode_labels.py` | Production tool versions, signatures, and fallback visibility require worker image validation | P1 |
| API security analysis | Partially implemented | OpenAPI parsing tests available | No | `test_scanners.py` | It is static contract analysis, not live API testing; the frontend now labels it accordingly | P1 |
| Container scanning | Partially implemented | Trivy and Docker paths are mocked in tests | No | `test_scanners.py`, runtime regression tests | Requires Docker daemon and Trivy on the dedicated worker; live image scan not verified | P0 |
| Docker runtime build/start/health/cleanup | Partially implemented | Lifecycle tests mock Docker and health probes | No | `test_smart_repo_scan.py`, runtime regression tests | No real worker-host build/start/stop cycle has been run; complex services/env secrets are not supported | P0 |
| DAST | Partially implemented | ZAP CLI/container and passive fallback tests mock external calls | No | `test_scanners.py`, `test_smart_repo_scan.py` | ZAP baseline is passive; no active testing, authenticated crawling, or production execution evidence | P0 |
| Worker scheduling and capability registration | Partially implemented (database-backed queue) | Queue claim and API tests available; worker process not deployed | No | `test_autopentest_worker.py`, `test_api.py` | Requires a separately deployed Linux worker; stale claimed jobs are retried after the lease interval | P0 |
| Worker cancellation, timeouts and cleanup | Partially implemented | Cancellation and cleanup paths are tested with mocks | No | `test_autopentest_worker.py`, `test_smart_repo_scan.py` | Cancellation takes effect between engines/cases; hard worker termination can still orphan host Docker resources | P0 |
| AutoPentest authorization and exact host/port scope records | Partially implemented | Serializer/API tests validate required authorization and exact scope | No | `test_autopentest_worker.py` | Scope records currently authorize a passive contract review; active requests are not implemented | P0 |
| AutoPentest deterministic planner | Partially implemented | Controlled OpenAPI fixture drives the planner | No | `test_autopentest_worker.py` | Current rules inspect OpenAPI security declarations only; routes, Django permissions/models, CORS and business logic are not analyzed | P1 |
| AutoPentest execution adapters | Partially implemented | Static API-contract check runs locally and stores an execution record | No | `test_autopentest_worker.py` | No Playwright, authenticated API client, synthetic users, live route checks, or ZAP-to-session adapter | P0 |
| Finding verification and evidence | Partially implemented | Tests verify evidence/hash and suspected/not-executed outcomes | No | `test_autopentest_worker.py` | Missing OpenAPI auth is reported as suspected; runtime exploitability is unverified and no unified SecureWiseFinding is created yet | P1 |
| Remediation recommendations, CWE/OWASP mapping and retest | Partially implemented | Existing finding/report tests are available | No | `test_services.py`, scanner tests | AutoPentest only offers contract-focused guidance; retest linkage/status and framework-specific remediation are incomplete | P1 |
| SecureWise web UI (scans, findings, reports, progress) | Implemented | Existing Vitest page tests available | No | Frontend `ScanDetailPage.test.tsx`, `ScansPage.test.tsx`, `FindingDetailPage.test.tsx` | Frontend production deployment not checked | P1 |
| AutoPentest UI | Partially implemented | Consent/scope and evidence display tests pass locally | No | Frontend `AutoPentestPage.test.tsx` | Basic consent/scope, session status, evidence and JSON report are present; no route discovery editor or live retest workflow | P1 |
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

SecureWise has a substantial control plane and useful static scanning. It is
**not an end-to-end production pentest platform** yet. The repository includes
a dedicated-worker entry point and a passive AutoPentest API-contract vertical
slice, but neither a production worker nor real Docker/ZAP/Trivy execution has
been verified. The acceptance criterion is therefore **not certified** until
the deployment team runs the controlled fixture through an isolated worker and
retains build, scanner, evidence, cleanup, and report output.

## Validation performed for this change

- SecureWise-focused backend tests pass, including worker/API authorization,
  scanner-mode, runtime, cleanup, and taxonomy coverage regressions.
- Django system checks and migration drift checks pass.
- Frontend typecheck, production build, and Vitest suite pass.
- The complete backend repository suite reports 15 unrelated marketplace and
  resume failures in this macOS environment. Most are associated with
  WeasyPrint failing to load native `libgobject-2.0-0`; no repository-wide
  green run is claimed.
- Trivy is installed locally, but Docker daemon reachability fails and ZAP is
  not installed. No image build, live app launch, Trivy image scan, or real
  ZAP scan was executed.
