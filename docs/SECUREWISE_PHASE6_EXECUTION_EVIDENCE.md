# SecureWise Phase 6 execution evidence

## Environment

- Backend branch: `feature/securewise-autopentest-foundation`
- Frontend branch: `feature/securewise-autopentest-foundation`
- Local worker host: macOS with Docker Desktop 4.59.1 / Docker Engine 29.2.0
- Targets: only the checked-in SecureWise controlled fixture; no public
  application was scanned
- Production Render, shared production database, dedicated Linux worker,
  rootless Docker, egress firewall, and host disk quotas: **not verified**

## Real scanner fixture

Command:

```sh
SECUREWISE_RUN_DOCKER_INTEGRATION=1 \
  ./venv/bin/python -m pytest tests/securewise/test_docker_integration.py -s -q
```

Result: **1 passed**. Sanitized integration output:

```json
{
  "engines": {
    "container": {
      "findings": 268,
      "image_source": "runtime_build",
      "status": "completed",
      "tool": "trivy"
    },
    "dast": {
      "execution_mode": "zap_baseline",
      "findings": 1,
      "runner": "docker-zap-baseline",
      "status": "completed"
    }
  },
  "persisted_findings": 273,
  "runtime_container_removed": true,
  "scan_id": "ad3b1c71-23b7-45a3-8b5b-10c5ce2cbcdf",
  "status": "completed",
  "temporary_image_removed": true
}
```

The worker test path cloned the controlled local fixture, built and started its
runtime, reused the runtime-built image for Trivy, ran ZAP baseline against the
worker-generated isolated Docker network, persisted scanner observations, and
asserted container/image cleanup. The reported finding counts are scanner
observations, not independently confirmed vulnerabilities.

The test process also logged a transient APScheduler SQLite `database table is
locked` error from an unrelated FutureWise background task; the SecureWise
integration completed and passed. This further supports using a persistent
shared database rather than SQLite for deployed workers.

## Regression and configuration checks

- SecureWise backend suite: **375 passed, 4 skipped**.
- Django `manage.py check`: passed.
- `manage.py makemigrations --check --dry-run`: no model/migration drift.
- `docker compose --profile securewise-worker config --quiet`: passed.
- Frontend Vitest: **193 passed**.
- Frontend TypeScript and production Vite build: passed.
- Frontend Oxlint: exit 0, with 9 existing warnings outside the changed
  AutoPentest files.
- `git diff --check`: passed in both repositories.

Focused regressions now cover exact-content trust matching, build-disabled
defaults, ignored legacy repository-ID trust, report/scan association checks,
tenant access to scans/findings/reports/AutoPentest evidence, worker metrics
redaction/scoping, role-limited membership mutation, prohibited user-created
findings, retest comparison, and external DAST target blocking.

## Independent worker and platform boundary

Separate API/worker OS-process evidence using a persistent local database is
recorded in
[`SECUREWISE_PHASE4_EXECUTION_EVIDENCE.md`](SECUREWISE_PHASE4_EXECUTION_EVIDENCE.md).
This Phase 6 Docker integration itself uses the pytest queue-processing path;
it is not a new independent worker-process demonstration. Production worker
execution remains unverified.

The developer environment provides Docker Desktop, not a dedicated Linux
rootless-Docker worker. This run does not establish host-level build isolation,
filesystem quotas, restricted egress, Render behavior, or production tenant
isolation. External/user-supplied DAST targets are now skipped by default in
the limited beta; only worker-created runtimes on the internal per-scan network
are eligible.
