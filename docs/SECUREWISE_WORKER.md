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
   forwarded to scan containers. Set
   `SECUREWISE_TRUSTED_RUNTIME_REPOSITORIES` to a comma-separated list of
   reviewed repository UUIDs only when their Dockerfiles and package install
   scripts have been approved for execution.

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

5. The Docker-capable end-to-end test checks out the controlled local fixture,
   allows its repository ID for runtime execution, starts the worker claim
   path, runs Trivy and ZAP, verifies database results, and checks cleanup:

   ```sh
   SECUREWISE_RUN_DOCKER_INTEGRATION=1 \
     ./venv/bin/python -m pytest tests/securewise/test_docker_integration.py -s -q
   ```

   The test skips with a diagnostic if Docker or the pinned ZAP image is
   unavailable. It never targets a public service.

The `securewise-worker` service alone receives `/var/run/docker.sock`. Do not
mount the host Docker socket into Django web or any application container.
Docker socket access is effectively host-root access: use a disposable local
machine and never run untrusted builds on a shared workstation with sensitive
host data.

Repository build scripts can execute arbitrary code during `docker build`.
Until a stronger sandbox is deployed, Docker builds and runtime launches are
blocked by default. Only reviewed repository UUIDs explicitly listed in
`SECUREWISE_TRUSTED_RUNTIME_REPOSITORIES` may be built or auto-started. Static
scanners may still run for non-allowlisted repositories. The runtime gets no
environment secrets or socket mounts, is resource-limited, drops Linux
capabilities, runs with a read-only root filesystem and temporary `/tmp`, and
is attached to an internal network with no outbound routing. Its host port is
bound to loopback only; ZAP joins that same per-scan network and addresses the
runtime by its container alias. The Docker build stage still runs on the
daemon host and is not a hardened sandbox; approve only trusted sources and
use a dedicated disposable worker host.

The controlled fixture in `tests/fixtures/securewise-autopentest-api/` is
intentionally vulnerable and uses synthetic data. It can be built and bound to
loopback only:

```sh
docker build -t securewise-autopentest-fixture tests/fixtures/securewise-autopentest-api
docker run --rm -p 127.0.0.1:3000:3000 securewise-autopentest-fixture
```

Never deploy that fixture to a public or production environment.

## Dedicated Linux deployment

- Deploy `python manage.py securewise_worker` as a separate supervised process
  on a dedicated Linux VM/runner. Give it the same database settings as the
  control plane, Git credentials/encryption key required for cloning, and
  scanner binaries (Semgrep, Trivy, Gitleaks, and Docker CLI for Docker-based
  ZAP). Use the pinned worker image or install compatible versions explicitly.
- Install and configure Docker Engine on the worker host and verify the daemon
  is reachable by the worker's operating-system user. Docker CLI installation
  by itself is not sufficient. The Render Django web service must not receive
  a Docker socket or execute repository code.
- Limit worker egress to Git and scanner registries; runtime target containers
  use internal per-scan networks and do not receive worker credentials. Use a
  dedicated host and host firewall rules.
- Configure only reviewed repository UUIDs in
  `SECUREWISE_TRUSTED_RUNTIME_REPOSITORIES`. Never enable builds for arbitrary
  user-submitted repositories on a shared worker.
- Keep worker timeouts, memory/CPU limits, filesystem quotas, cleanup
  monitoring, and logs enabled. Alert on old `worker_claimed` jobs, Docker disk
  growth, failed image removal, and workers that stop refreshing
  `SecureWiseWorkerRegistration.last_seen_at`.
- ZAP runs baseline/passive checks only. The HTTP fallback is also passive.
  Container and DAST engine failures are reported separately from results
  produced by other engines.

This deployment has not been production-verified. The database queue is a
single shared control-plane queue and is a minimal foundation, not a replacement
for a durable broker with dead-lettering, per-tenant quotas, or high-scale
concurrency management.
