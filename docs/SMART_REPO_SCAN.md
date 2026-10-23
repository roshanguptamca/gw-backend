# Smart Repository Scan

**Status: partially implemented.** This document describes what SecureWise
does today when a user provides
only a repository URL and runs a Full Scan — as opposed to
`docs/RUNTIME_TEST_ENVIRONMENT.md` / `docs/DOCKERIZATION_ENGINE.md`, which are
earlier aspirational design notes for a more ambitious future version.

## Problem this solves

Previously, a Full Scan would only include DAST if the user manually supplied
a `target_url`. If they didn't, DAST was silently left out of
`selected_engines` — no "skipped" row, no explanation. Standalone DAST scans
without a `target_url` failed outright with "Target URL is required to run a
DAST scan".

## Flow

```
Repo URL
  ↓
Discovery (ApplicationDiscoveryEngine — static, read-only inspection)
  ↓
Runtime Plan (ApplicationRunPlan: language, framework, build/start commands,
              Dockerfile/compose, ports, health endpoints, confidence)
  ↓
Auto Run if possible (RuntimeEnvironmentManager — isolated Docker container)
  ↓
DAST if reachable (OWASP ZAP baseline when available, passive fallback otherwise)
  ↓
Skip with clear reason if not (Docker unavailable, build failed, unreachable,
                                 unrecognized stack, etc.)
  ↓
Unified Report (per-engine SecureWiseScanEngineResult rows + findings)
```

## What is real

- **`apps/securewise/discovery/`** — `ApplicationDiscoveryEngine.discover(repo_path)`
  performs genuine, read-only, file-based static analysis of a cloned repo:
  - Detects Python (Django via `manage.py`, FastAPI/Flask via import-marker
    scanning), Node (Next.js/NestJS/Express/Vite/CRA via `package.json`
    dependencies + lockfile-based package manager detection), Java (Spring
    Boot via `pom.xml`/`build.gradle` marker scanning), and Go (gin/echo/fiber
    via `go.mod` marker scanning).
  - Detects `Dockerfile`/`docker-compose.yml` and parses `EXPOSE` /
    `ports:` entries for real port numbers.
  - Detects OpenAPI/Swagger spec files, required env var *names* (from
    `.env.example` etc — never values), and external service dependencies
    (postgres/mysql/redis/mongo/... from compose image names).
  - Classifies `project_type` (`web_app` / `api_service` / `frontend_app` /
    `library` / `cli` / `multi_service` / `unknown`) and whether the app
    `can_auto_run`.
  - Verified against the real, on-disk `gw-backend` repository itself: it
    correctly detects Django, the real build/start commands, the real
    Dockerfile (`EXPOSE 8000`), the real docker-compose (`postgres:16-alpine`
    → `external_services: ["postgresql"]`), and required env var names from
    `.env.example`.
- **`apps/securewise/runtime/`** — `RuntimeEnvironmentManager.try_start()`
  genuinely shells out to the real `docker` CLI (`docker version`, `docker
  build`, `docker run`, `docker logs`, `docker stop`/`rm`) with no
  `--privileged`, no host-root mounts, explicit `--memory`/`--cpus` limits,
  and a bounded free host port. It probes the container for health via real
  HTTP requests (`apps/securewise/discovery/health.py`).
  - **`docker version`/`docker ps` availability check is genuinely exercised
    in CI/dev sandboxes where the Docker daemon is not running** — it
    correctly reports "Docker is not available in this environment" rather
    than crashing. This is the actual condition observed in the development
    sandbox used to build this feature.
- **Orchestrator wiring** (`apps/securewise/scanners/orchestrator.py`) — for a
  real, repository-backed Full Scan (`scan.repository_id` set), DAST is always
  included in `selected_engines` (never silently dropped), the orchestrator
  runs discovery + attempts a runtime start *before* the engine loop, mutates
  the shared `metadata` dict with either a discovered `target_url` or a
  specific `dast_skip_reason`, and always stops/removes any started container
  in a `finally` block regardless of success, cancellation, or exceptions.
- **Final scan status** (`apps/securewise/services/scanner.py`) — a Full Scan
  where DAST (or any engine) was skipped for a legitimate reason but other
  engines ran real tools successfully now reports `completed_with_warnings`,
  never a plain `completed` that hides the gap. The pre-existing
  `completed_partial` honesty check (when *no* engine ran a real tool) is
  preserved and takes precedence.
- **Missing health endpoint recommendation** — when a runtime is auto-started
  but has no dedicated health endpoint (only `/` responds) and/or the
  Dockerfile has no `HEALTHCHECK` instruction, a LOW-severity reliability
  recommendation may be emitted. It is not assigned a CWE or OWASP category:
  absence of a health check is not by itself a confirmed security weakness.
- **Discovery preview API** — `POST
  /api/securewise/repositories/{id}/discovery-preview/` clones the repo into
  an ephemeral temp directory, runs `ApplicationDiscoveryEngine`, and returns
  the plan as JSON. No scan is created; used by the frontend wizard to show a
  live preview before the user commits to running a scan.
- **Frontend wizard** — the Run Scan modal now offers a "Runtime Source"
  choice (Auto build & run from repository vs. use an existing
  deployed/staging URL) once a repository is selected for a `full` or `dast`
  scan. In Auto mode, Target URL is hidden and a live discovery preview
  (detected language/framework/project type, Dockerfile presence, whether
  DAST is possible) is fetched and shown, including the exact skip reason if
  DAST cannot run.

## What is fallback / best-effort / skipped by design

- **Dockerfile generation for repos with no Dockerfile** — supported for a
  limited set of detected Python/Node/Go/PHP/Ruby stacks using runtime
  versions and package managers read from project metadata where available.
  Dependency installation fails the build; it is never ignored. This
  generated Dockerfile is written only into the
  scan-scoped ephemeral clone directory and is never committed or persisted
  anywhere.
- **Multi-service / docker-compose auto-run** — discovery detects
  `docker-compose.yml` and lists external service dependencies (e.g.
  Postgres), but   the runtime manager only builds/runs a single
  Dockerfile-based container, not a full compose stack. If the primary
  service genuinely requires those external dependencies at startup, the
  container may fail to become healthy — in which case DAST is skipped with
  a clear "did not become reachable" reason, not a fake pass.
- **Required env vars** — only variable *names* are detected (from
  `.env.example`), never values. The auto-started container currently does
  not inject any application secrets; apps that hard-require unset env vars
  at startup will likely fail health checks and DAST will be skipped with a
  clear reason, exactly as intended (never silently pretend success).
- **Java/Go auto-run** — discovery correctly classifies Spring Boot and
  Go/gin/echo/fiber apps, but the MVP generated-Dockerfile templates and
  build/run flow have only been exercised in unit tests with mocked Docker
  calls, not against a real Java/Go build in this environment.

## Skip reasons a user can see

- `"application does not expose an HTTP runtime to scan"` — `library`/`cli`
  project types.
- `"Application could not be auto-started because required runtime
  dependencies were not available (no Dockerfile/docker-compose and no
  recognized start command was found)."`
- `"Docker is not available in this environment: <reason>"` — daemon
  unreachable or CLI missing.
- `"Application could not be auto-started because the Docker build
  failed."` (with truncated build log).
- `"Application could not be auto-started because the container failed to
  start."` (with truncated container log).
- `"Application could not be auto-started because it did not become
  reachable within 45 seconds."` (with truncated container log).

## How to test locally

1. Start the Docker-capable worker using `docs/SECUREWISE_WORKER.md`.
2. Register the controlled local fixture at
   `tests/fixtures/securewise-autopentest-api/` as a local-path repository.
   The fixture is synthetic, loopback-bound and intentionally vulnerable;
   never point automatic active testing at a public production target.
3. `POST /api/securewise/repositories/{id}/discovery-preview/` — inspect the
   returned `ApplicationRunPlan` JSON.
4. Create and start a `full` scan. The web process only queues it; the worker
   performs cloning, runtime creation and scanner execution.
5. Inspect `GET /api/securewise/scans/{id}/engine-results/` — DAST will show
   `status=skipped` with a specific `skipped_reason` if Docker isn't
   available on the worker, or `status=completed`/`status=failed` if the
   worker can start the app and ZAP/passive fallback completes.
6. Run the backend test suite: `pytest tests/securewise -q` (includes
   `tests/securewise/test_smart_repo_scan.py`, all mocked at the Docker
   subprocess boundary plus one live sanity check against the real on-disk
   `gw-backend` repo).

## Known limitations / honest gaps

- No live end-to-end verification of a real container actually starting and
  serving DAST-scannable traffic was possible in this development sandbox,
  because the Docker daemon is not running here. The Docker-unavailable
  fallback path *was* verified live (it is a real, current condition in this
  environment). Runtime-start success paths are covered only by mocked unit
  tests.
- Multi-service (docker-compose) apps with required external services
  (databases, queues) are not automatically provisioned — only the primary
  app container is started.
- No support yet for injecting discovered `required_env_vars` values (there
  are none to inject safely — by design, only variable *names* are ever
  read).

## Next recommended phase

- Add `docker-compose`-aware runtime start (bring up the full stack,
  including declared external services like Postgres/Redis, with strict
  resource/network isolation) for repositories where a working
  `docker-compose.yml` already exists.
- Extend the Dockerfile generation templates to injected discovered
  `required_env_vars` with safe, non-secret placeholder values where an app
  needs *some* value to boot (e.g. `SECRET_KEY=dev-placeholder`), clearly
  logged as synthetic.
- AutoPentest currently checks OpenAPI authentication declarations and records
  evidence. Missing requirements remain suspected; live authorization,
  synthetic-user, Playwright and API runtime tests are not implemented.
- Real, opt-in end-to-end validation in an isolated environment with a running
  Docker daemon against the controlled local fixture is still required.
