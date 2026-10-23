# SecureWise multi-runner design

**Status:** provider-neutral worker foundation and Linux deployment assets are
implemented; cloud and GitHub Actions execution are not verified.

## Current architecture and trust boundaries

```text
Customer browser
    |
Vercel frontend
    |
Render Django control plane ---- PostgreSQL (scan queue, tenancy, findings)
                                      |
                              runner registry / lease
                         +------------+------------+
                         |                         |
                  Linux worker A              Linux worker B
                 (any provider)               (any provider)
                         |                         |
                  scanners/tools              scanners/tools
```

Django continues to own authorization, queue state, progress, findings and
reports. Linux workers poll the existing database queue, register
capabilities/health, claim work with a database lease, run the existing
`ScannerRunner`/`PentestRunner`, and persist through existing services. A
provider is descriptive worker metadata only; no business logic dispatches on
Oracle/AWS/Azure/GCP/Hetzner/DigitalOcean. GitHub Actions execution is a
separate optional future runner and does not currently have a secure
authenticated result-ingestion contract.

The worker capability registry records engine availability, scanner versions,
CPU architecture, available memory, Docker daemon reachability, optional
Playwright/ZAP support and declared network proof. Hostnames and worker IDs
are not exposed in customer scan readiness. Shared-registry selection checks
freshness, idle capacity, architecture and all required engine capabilities.
URL work additionally requires an active authorization and a fresh
host-verified egress proof; a boolean environment flag or capability claim
alone does not enable that work.

## Runner request, selection and result lifecycle

1. The API validates tenant/project/repository or target authorization and
   stores a queued scan. No repository build or scan occurs inside Django.
2. Each generic worker registers as `local` or `linux_worker` with
   dynamically detected details. Infrastructure provider is a free-form
   non-secret label such as `self_hosted`; it is not an execution type.
3. The queue selector chooses only a fresh worker reporting the required
   engine capabilities and a supported `arm64` or `amd64` architecture. A
   persistent active-job slot enforces one job per worker ID; lease recovery
   permits retry after a missed heartbeat.
4. The worker calls the existing scanner service. Engine results preserve
   success, failure and skipped status and existing findings/evidence are
   persisted by the existing pipeline.
5. No secure candidate means a diagnostic blocked result from the selection
   response from scan start/retry; the scan remains unqueued and the worker
   never silently falls back to a weaker runner.

`RunnerCapabilities`, `RunnerSelection`, dynamic discovery, compatibility
checks and fleet summarization live in
`apps/securewise/services/runners.py`. The database-backed runner registry
reuses `SecureWiseWorkerRegistration`; lease fields extend that model.

## Capability and trust rules

- SAST/SCA/secret/IaC capabilities describe supported engine interfaces,
  including repository-independent deterministic fallback behavior; scanner
  binary versions are separately recorded only when executable and version
  query succeeds.
- Docker is advertised only when the CLI can reach a daemon. ZAP/Playwright
  Docker capability depends on daemon/image availability.
- `arm64` and `amd64` are the currently schedulable CPU architectures.
  Unknown architectures are not selected. Individual tool versions are
  discovered on-host; there is no claim that every optional binary is
  available on both architectures.
- There is no `OracleRunner`, AWS/GCP queue, provider database or provider
  storage implementation.
- Worker process identity currently relies on access to the shared Django
  database and the registered worker ID; this is not a cryptographic,
  per-worker workload identity. Do not treat it as hostile-worker
  authentication. GitHub Actions needs a distinct short-lived identity and
  result-ingestion protocol.
- Customer repository builds remain blocked by the existing reviewed-content,
  explicit-opt-in and worker isolation controls. Rootful Docker socket access
  is host authority; rootless Docker alone is not a multi-tenant sandbox.
- URL assessments remain passive-only and blocked unless application checks
  and the network policy proof are both present.

## Implemented, reused and deferred

| Capability | State | Evidence / remaining blocker |
|---|---|---|
| Local scanner and findings pipeline | Reused | Existing scanner/orchestrator and scan-result/finding models; Semgrep ran on a controlled fixture in prior Phase 7.1 evidence |
| Database queue, cancellation, lease recovery | Reused and extended | `SecureWiseWorkerRegistration` now has a one-job slot and lease; unit tests cover selection/slot behavior |
| Multi-provider generic Linux workers | Implemented at source/configuration level | Provider metadata is independent of dispatch. No Linux VM has checked in in this phase |
| Runtime capability/architecture detection | Implemented | Live local capability collection; ARM64 detection is unit-tested, not run on an ARM VM |
| Worker selection | Implemented for scan engines/URL proof | Missing candidates are rejected; resource selection is not yet quota-aware |
| Host deployment | Partially implemented | Ubuntu/Debian systemd scripts/docs; install and service were not run on Linux |
| Network proof | Partially implemented | Required root-owned recent proof file and nftables structural checker; no host rules were verified |
| GitHub Actions runner and ingestion | Missing | No workflow, short-lived runner credential, authenticated ingestion API, idempotency ledger or artifact validation |
| Tenant usage quotas | Missing | No organization concurrency/repository-size/evidence/scan quotas beyond existing URL rate limits |
| Resource scheduling | Partial | One job per registered worker, resource metrics reported; memory/CPU/disk requirements are not yet admission thresholds |
| Oracle/AWS/Azure/GCP/Hetzner/DigitalOcean execution | Unverified | Deployment guides only; no provider credentials/VMs available |
| Runner customer UI | Partial | Scan progress shows aggregate runner type, architecture, scanner versions and fleet counts; no manual runner choice is exposed |

## Portability and migration

Use `docs/SECUREWISE_GENERIC_LINUX_WORKER.md` for any compatible Linux VM and
`docs/SECUREWISE_ORACLE_FREE_WORKER_SETUP.md` as an optional Oracle-specific
provisioning checklist. Migration changes the VM, network policy, secrets,
database connectivity and infrastructure metadata only. It must not change
the Django, React, scanner, queue or finding code. Confirm worker heartbeat,
scanner matrix and a controlled fixture scan after migration.

## Remaining architecture work

Implement a GitHub Actions path only after the result-ingestion contract has
short-lived per-job credentials, server-side job/tenant binding, commit and
workflow-run verification, payload integrity/size checks, replay protection,
idempotent findings persistence and strict no-build static execution. Do not
grant arbitrary customer repository write permissions or trigger arbitrary
workflows. Admission quotas and actual Linux-host integration are required
before calling this a production multi-runner service.
