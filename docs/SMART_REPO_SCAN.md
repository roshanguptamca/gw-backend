# Smart Repository Scan

**Status: implemented** (branch `feature/securewise-smart-repo-scan`). This
document describes what SecureWise actually does today when a user provides
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
- **Missing health endpoint finding** — when a runtime is auto-started but has
  no dedicated health endpoint (only `/` responds) and/or the Dockerfile has
  no `HEALTHCHECK` instruction, a genuine LOW-severity finding is emitted
  (`CWE-703`, `OWASP A10:2025-Mishandling of Exceptional Conditions`) — never
  a scan failure.
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

- **Dockerfile generation for repos with no Dockerfile** — only supported for
  a small set of known simple stacks (Python/Node/Go) using minimal, generic
  base images. This generated Dockerfile is written only into the
  scan-scoped ephemeral clone directory and is never committed or persisted
  anywhere.
- **Multi-service / docker-compose auto-run** — discovery detects
  `docker-compose.yml` and lists external service dependencies (e.g.
  Postgres), but the MVP runtime manager only builds/runs a single
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

1. Add a repository (e.g. `https://github.com/roshanguptamca/gw-backend`) via
   the SecureWise UI or API.
2. `POST /api/securewise/repositories/{id}/discovery-preview/` — inspect the
   returned `ApplicationRunPlan` JSON.
3. Create a `full` scan against that repository and start it.
4. Inspect `GET /api/securewise/scans/{id}/engine-results/` — DAST will show
   `status=skipped` with a specific `skipped_reason` if Docker isn't
   available in your environment (as it is not in this sandbox), or
   `status=completed`/`status=failed` with real passive-DAST findings if a
   Docker daemon is reachable and the app starts successfully.
5. Run the backend test suite: `pytest tests/securewise -q` (includes
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
- Wire the discovered `openapi_specs` paths into the API scanner
  automatically when found, matching the same "smart" auto-discovery
  philosophy as DAST.
- Real, opt-in end-to-end validation in an environment with a running Docker
  daemon (this sandbox does not have one) against
  `https://github.com/roshanguptamca/gw-backend`.
