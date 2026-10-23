# SecureWise Phase 4 execution evidence

**Date:** 2026-10-10
**Branch:** `feature/securewise-autopentest-foundation`
**Environment:** local macOS, Docker Desktop 29.2.0, isolated persistent SQLite
database at `/tmp/securewise-phase4.sqlite3`; Playwright 1.57.0 Noble image
pinned by digest
**Production verification:** none

## Independent worker and HTTP API

The Django API (`manage.py runserver --noreload`) and
`manage.py securewise_worker` were started as separate operating-system
processes and used the same isolated persistent database. A synthetic
organization, project, repository association, and user were created in that
database for the controlled fixture only. A session was submitted through
`POST /api/securewise/autopentest/sessions/` after normal HTTP session
authentication. The API returned `201` and `queued`, and did not return the
encrypted credential configuration.

The independent worker registered online with Docker, Trivy, ZAP, and
Playwright capabilities. It claimed the API-created job and persisted
progress, test cases, screenshots/traces, one unified finding, engine status,
and completion. This is independent-process local evidence, not a pytest
`process_next_job()` invocation.

## Real browser assessment

The pinned `securewise-playwright:1.57.0` image was built from the
Playwright 1.57.0 Noble image. The worker built and health-checked the
controlled Express fixture, attached Chromium to the per-scan internal Docker
network, and ran the declared journeys against the runtime alias:

| Outcome | Count | Evidence |
|---|---:|---|
| Confirmed vulnerability | 1 | `CWE-639`, cross-user invoice rendered with the other synthetic user's owner marker |
| Passed | 6 | Protected page, role denial, authorized admin access, logout, server-side session expiration, and session cookie flags |
| Not executed / inconclusive | 0 | The full selected journey set executed |

The API engine result recorded `raw_tool=playwright`, execution mode
`authenticated_browser`, seven executed cases, and the same outcome counts.
The confirmed finding was persisted in the unified SecureWise finding model
with its endpoint, CWE/OWASP mapping, severity, confidence, remediation, and
sanitized browser evidence. Seven screenshot/trace evidence records were
persisted. The synthetic passwords were absent from the API response and
evidence. A separate real browser job exercised the fixture's explicit
synthetic-session invalidation endpoint; the session-expiration journey
passed.

The fixture contains no destructive routes or real user data. Browser
requests to other origins are aborted; the container has no Docker socket,
host mounts, or outbound route, and has CPU, memory, process, and filesystem
limits.

## Queue reliability checks

- With the worker stopped, a second API-submitted job remained `queued` in the
  persistent database. Restarting `securewise_worker` consumed it and
  persisted terminal status and progress.
- An API cancellation of a queued session returned `cancelled`; restarting the
  worker left it cancelled and did not execute it.
- A separate isolated job was marked `running` with a lease 31 minutes old.
  After worker restart, the stale lease was reclaimed and the job completed
  with the expected passive-analysis warnings.
- Worker registration heartbeat timestamps advanced while the independent
  process was running.

## Cleanup and boundaries

After the real browser assessment, there were no active SecureWise runtime or
Playwright containers and no per-scan `securewise-net-*` network. The runtime
image created for the run was removed by the runtime lifecycle; Playwright
containers use `--rm` and were absent after execution. Two stopped runtime
containers and two temporary images with July 2026 timestamps predated this
run; they were not modified or removed.

The development runs used an isolated `/tmp` database rather than the
repository's tracked development database. No production service or public
target was contacted.

## Verification and remaining limits

The worker process, HTTP API queue path, Docker application runtime, Chromium
journeys, evidence persistence, unified finding, queue restart, queued
cancellation, stale-lease recovery, and cleanup were verified locally. The
reusable opt-in browser Docker integration test is
`tests/securewise/test_autopentest_worker.py::test_authenticated_browser_scans_real_fixture_and_cleans_up`.
The SecureWise backend suite passed with 359 tests and 3 opt-in Docker tests
skipped by default; the Playwright Docker integration test passed separately.
Frontend tests passed (188), and the TypeScript production build passed.
Django system checks and migration drift checks passed. Oxlint passed with
warnings confined to existing unrelated files.

Browser journeys are deterministic and require the reviewed OpenAPI
`x-securewise-browser-journeys` extension. The planner does not infer arbitrary
frontend routes, create accounts, or generate executable AI scripts. Session
expiration requires an explicitly declared safe fixture endpoint. Running
build scripts through Docker still executes code on the Docker host; only
reviewed repository IDs should be allowlisted on a dedicated disposable
worker. Linux deployment, production queue/database behavior, production
scanner availability, and production isolation remain unverified.
