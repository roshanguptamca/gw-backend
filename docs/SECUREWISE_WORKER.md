# SecureWise scanner worker

## Why it is separate

Django remains the control plane. Scan APIs persist `queued` work and return
without running repository code. A dedicated `securewise_worker` process
registers its capabilities, claims jobs from the shared database, runs the
existing scanner service, and updates engine progress and findings. AutoPentest
jobs use the same worker process and database queue.

This queue uses the existing database and does not require Redis or Celery.
Claiming is an atomic status transition. A worker refreshes its status and
active job lease every 15 seconds; claims without heartbeats for 30 minutes
are recoverable after a worker crash. Each worker process runs one job at a
time. Recovered scans reset per-engine progress and re-run idempotently.

## Local Docker development

1. Start Docker Desktop or Docker Engine and confirm both client and daemon:

   ```sh
   docker version
   ```

   `docker version` must show both Client and Server sections. A Docker CLI
   without a reachable daemon is not ready.

2. Configure the Compose `.env` with the same Django/database configuration
   used by the web service. For local Compose, the database host must be the
   Compose service name `db`. Keep Git provider credentials and the SecureWise
   encryption key available only to the control plane and worker; they are not
   forwarded to scan containers. Runtime execution is fail-closed unless
   `SECUREWISE_TRUSTED_RUNTIME_CONTENT` contains exact reviewed content digests;
   a repository UUID by itself never authorizes a build. See the private-beta
   threat model below.

3. Start the database and apply migrations:

   ```sh
   docker compose up -d db
   docker compose run --rm web python manage.py migrate
   ```

4. Build and start Django, then start one independent worker process:

   ```sh
   docker compose up --build -d web
   docker compose --profile securewise-worker up --build -d --scale securewise-worker=1 securewise-worker
   docker compose logs -f securewise-worker
   ```

   The worker image pins Docker CLI 27.5.1 and Trivy 0.72.0. Its startup log
   lists detected capabilities. The scan progress API reports worker
   heartbeat, Docker, Trivy, and ZAP readiness. Runtime health checks run from
   a short-lived, resource-limited probe container attached to the per-scan
   internal network; Docker Desktop does not expose published ports from an
   internal network back to the host. ZAP uses the digest-pinned image declared
   in `apps/securewise/scanners/dast.py`; it is pulled on first use and runs
   with CPU, memory, PID, and capability limits. Do not scale the worker
   service above one process per worker instance unless deliberately deploying
   multiple independent workers.

5. Build the pinned Playwright runner image on the Docker host before
   scheduling browser journeys:

   ```sh
   docker build -f Dockerfile.securewise-playwright \
     -t securewise-playwright:1.57.0 .
   docker image inspect securewise-playwright:1.57.0
   ```

   The worker reports the `playwright` capability only when Docker is
   reachable and this image is present. Browser containers share only the
   per-scan internal runtime network; they have no Docker socket or host
   mounts and are removed after execution.

6. The Docker-capable end-to-end test checks out the controlled local fixture,
   allows its repository ID for runtime execution, starts the worker claim
   path, runs Trivy and ZAP, verifies database results, and checks cleanup:

   ```sh
   SECUREWISE_RUN_DOCKER_INTEGRATION=1 \
     ./venv/bin/python -m pytest tests/securewise/test_docker_integration.py -s -q
   ```

   The test skips with a diagnostic if Docker or the pinned ZAP image is
   unavailable. It never targets a public service.

On Linux set `DOCKER_GID` to the Docker socket's group ID before starting the
Compose worker; on macOS, Docker Desktop may require no extra group. The worker
container runs as UID 10001 with a read-only application filesystem, dropped
capabilities, a private temporary directory, and process/memory/CPU limits.
The Docker socket is still powerful: use only a disposable development host.

Repository build scripts can execute arbitrary code during `docker build`.
Until a stronger sandbox is deployed, Docker builds and runtime launches are
blocked by default. Static scanners may still run for unreviewed repositories.
Runtime builds additionally require `SECUREWISE_RUNTIME_BUILDS_ENABLED=true`;
keep it unset until the dedicated worker host, rootless Docker daemon,
resource quotas, and outbound network restrictions have been verified.
An administrator must review the exact tree and set
`SECUREWISE_TRUSTED_RUNTIME_CONTENT` to comma-separated
`<repository-uuid>=<sha256>` entries. Compute a digest from the reviewed
checkout with:

```sh
./venv/bin/python manage.py securewise_runtime_digest /path/to/reviewed/checkout
```

The digest covers file paths, file content, and executable mode; it ignores
`.git`, dependency/vendor directories and caches, rejects symlinks, and is
bounded to 100,000 files / 2 GiB. Any content or executable-mode change stops
runtime execution until reviewed and re-approved. The old
`SECUREWISE_TRUSTED_RUNTIME_REPOSITORIES` variable is not an authorization
mechanism. The Docker build stage still executes on the daemon host with
network access; content pinning is not a sandbox. Until worker host isolation
and egress controls are independently verified, only reviewed repositories
may be enabled.

The worker service alone receives the Docker socket. Never mount it into
Django web, a scanner, browser, or customer application container. The target
runtime receives no worker environment secrets, socket mounts, or host mounts;
it runs resource-limited with dropped capabilities, a read-only root
filesystem and temporary `/tmp`, on an internal network. Its host port is
bound to loopback only; ZAP joins the same per-scan network by container alias.

The controlled fixture in `tests/fixtures/securewise-autopentest-api/` is
intentionally vulnerable and uses synthetic data. It can be built and bound to
loopback only:

```sh
docker build -t securewise-autopentest-fixture tests/fixtures/securewise-autopentest-api
docker run --rm -p 127.0.0.1:3000:3000 securewise-autopentest-fixture
```

Never deploy that fixture to a public or production environment.

## Authenticated API AutoPentest (controlled fixture only)

Authenticated API mode accepts bearer credentials for at least two synthetic
identities. Credentials are encrypted in the session record and omitted from
session API responses. The mode is restricted to an explicitly authorized
loopback scope, an exact reviewed repository digest with runtime builds
explicitly enabled, and the discovered application port.
The worker starts that repository as an isolated runtime and sends only
documented GET/HEAD operations from temporary bounded request containers on
the runtime's internal Docker network. Redirects and secret-bearing OpenAPI
parameters are not followed/sent. Other methods and unsupported parameterized
routes are recorded as not executed.

The controlled test creates a session through the API and executes the
database queue entry point against Docker:

```sh
SECUREWISE_RUN_DOCKER_INTEGRATION=1 \
  ./venv/bin/python -m pytest \
  tests/securewise/test_autopentest_worker.py::test_authenticated_api_scans_real_isolated_fixture_and_cleans_up \
  -s -q
```

The test verifies one evidence-backed `CWE-639` fixture finding, passing
authorization controls, unified finding persistence, and removal of runtime,
request containers, network, and image. It uses pytest's transactional test
database and invokes `process_next_job()` synchronously; it does **not** prove
that a separately running `securewise_worker` process claims the API-created
job. The sanitized results and scan identifiers are recorded in
[`SECUREWISE_PHASE3_EXECUTION_EVIDENCE.md`](SECUREWISE_PHASE3_EXECUTION_EVIDENCE.md).

## Authenticated browser AutoPentest (controlled fixture only)

Browser mode runs declarative journeys from the repository's
`x-securewise-browser-journeys` OpenAPI extension. The deterministic adapter
supports protected-page access, cross-user resource checks, role boundaries,
logout, server-side session expiration, and cookie flags. The worker builds
and starts the reviewed application, then runs Chromium in the pinned
Playwright image against the internal runtime alias. Only relative paths,
supported selectors, and synthetic identities are accepted; external browser
requests are aborted. Credentials are encrypted on the session and omitted
from API responses. Screenshots blur form fields and declared sensitive
elements, and traces store only curated step outcomes.

Build the runner image, then run its Docker integration test:

```sh
docker build -f Dockerfile.securewise-playwright \
  -t securewise-playwright:1.57.0 .
SECUREWISE_RUN_DOCKER_INTEGRATION=1 \
  ./venv/bin/python -m pytest \
  tests/securewise/test_autopentest_worker.py::test_authenticated_browser_scans_real_fixture_and_cleans_up \
  -s -q
```

That opt-in test runs the browser adapter synchronously inside pytest to cover
real Docker execution; it does not substitute for independent worker-process
verification. Phase 4's separate API and worker processes, persisted browser
evidence, queue restart, cancellation, expired-lease recovery, and cleanup are
recorded in
[`SECUREWISE_PHASE4_EXECUTION_EVIDENCE.md`](SECUREWISE_PHASE4_EXECUTION_EVIDENCE.md).

Browser route planning currently requires the reviewed OpenAPI extension; it
does not infer routes from arbitrary frontend source or generate AI-authored
executable journeys. Session-expiration testing runs only when the reviewed
fixture declares a safe endpoint that invalidates a synthetic session.

## Dedicated Linux deployment

- Deploy `python manage.py securewise_worker` as a separate supervised process
  on a dedicated Linux VM/runner. Give it the same database settings as the
  control plane, Git credentials/encryption key required for cloning, and
  scanner binaries (Semgrep, Trivy, Gitleaks, and Docker CLI for Docker-based
  ZAP). Use the pinned worker image or install compatible versions explicitly.
- Install and configure Docker Engine on the worker host and verify the daemon
  is reachable by the worker's operating-system user. Prefer a rootless Docker
  daemon owned by the dedicated worker account; do not add that account to the
  rootful `docker` group, which is equivalent to root. Docker CLI installation
  by itself is not sufficient. The Render Django web service must not receive
  a Docker socket or execute repository code.
- Limit worker egress to Git and scanner registries; runtime target containers
  use internal per-scan networks and do not receive worker credentials. Use a
  dedicated host and host firewall rules.
- Configure only exact reviewed repository digests in
  `SECUREWISE_TRUSTED_RUNTIME_CONTENT`. Never enable builds for arbitrary
  user-submitted repositories on a shared worker.
- Keep worker timeouts, memory/CPU limits, filesystem quotas, cleanup
  monitoring, and logs enabled. Alert on old `worker_claimed` jobs, Docker disk
  growth, failed image removal, and workers that stop refreshing
  `SecureWiseWorkerRegistration.last_seen_at`.
- Build and verify `securewise-playwright:1.57.0` on the worker host and
  confirm the worker advertises `playwright` before enabling browser tests.
- ZAP runs baseline/passive checks only. The HTTP fallback is also passive.
  Container and DAST engine failures are reported separately from results
  produced by other engines.

This deployment has not been production-verified. The database queue is a
single shared control-plane queue and is a minimal foundation, not a replacement
for a durable broker with dead-lettering, per-tenant quotas, or high-scale
concurrency management.
The private-beta DAST adapter intentionally skips user-supplied external
targets; it only scans the worker-started application over its per-scan
internal Docker network.

For a dedicated Linux service unit, threat boundaries, required host quotas,
rollback, and explicit private-beta restrictions, see
[`SECUREWISE_PRIVATE_BETA.md`](SECUREWISE_PRIVATE_BETA.md).
