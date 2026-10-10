# SecureWise scanner worker

## Why it is separate

Django remains the control plane. Scan APIs persist `queued` work and return
without running repository code. A dedicated `securewise_worker` process
registers its capabilities, claims jobs from the shared database, runs the
existing scanner service, and updates engine progress and findings. AutoPentest
jobs use the same worker process and database queue.

This queue uses the existing database and does not require Redis or Celery.
Claiming is an atomic status transition. Claims older than 30 minutes can be
recovered after a worker crash; configure engine timeouts so normal jobs finish
before that lease expires.

## Local Docker development

1. Configure `.env` for the Compose PostgreSQL service and apply migrations:

   ```sh
   docker compose up -d db
   docker compose run --rm web python manage.py migrate
   ```

2. Start the Django control plane and isolated worker:

   ```sh
   docker compose up --build web
   docker compose --profile securewise-worker up --build securewise-worker
   ```

The `securewise-worker` service alone receives `/var/run/docker.sock`. Do not
mount the host Docker socket into the `web` service. Access to this socket is
effectively host-root access; use a disposable development machine and never
run untrusted scans on a shared workstation with sensitive host data.

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
  scanner binaries (Semgrep, Trivy, Gitleaks, and optionally ZAP).
- Install and configure Docker Engine on the worker host and verify the daemon
  is reachable by the worker's operating-system user. Docker CLI installation
  by itself is not sufficient. The Render Django web service must not receive
  a Docker socket or execute repository code.
- Restrict worker egress to required Git/scanner registries and the local
  scanner runtime. Use a dedicated host, no production credentials in target
  containers, and host firewall rules. Repository source is untrusted input.
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
