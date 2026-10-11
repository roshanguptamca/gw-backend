# SecureWise Phase 7.3 execution evidence

**Branch:** `feature/securewise-autopentest-foundation`
**Environment:** local macOS; prior controlled Semgrep fixture evidence is in
`SECUREWISE_PHASE7_EXECUTION_EVIDENCE.md`.
**Cloud execution:** none.

## Implemented in this phase

- Added provider-neutral `RunnerCapabilities`, dynamic host capability
  discovery, architecture normalization, scanner version collection,
  capability-based runner selection and aggregate fleet status.
- Extended the existing worker registration model with a database-backed
  active-job slot and lease timestamp, enforcing one job per worker identity.
  Existing database queue, scanner runner, findings and engine-result
  persistence are reused.
- Worker scheduling rejects stale/offline workers, busy slots, missing scan
  engines, unknown CPU architecture and URL work without egress verification.
  No selection is based on provider name.
- Worker readiness no longer sends customer APIs a worker ID/hostname. Scan
  progress shows generic runner type, architecture, scanner versions and
  aggregate fleet availability.
- Added an Ubuntu/Debian systemd installer, verifier and non-destructive
  uninstaller plus generic, Oracle-optional, GitHub Actions security/status and
  runner-security documentation.
- URL egress no longer trusts `SECUREWISE_URL_EGRESS_ENFORCED=true` alone. It
  additionally checks a recent root-owned proof file; the Linux verifier
  checks a deny-by-default nftables structure before creating that proof.

## Verification performed

| Check | Result |
|---|---|
| `pytest -q tests/securewise` | 417 passed, 4 skipped |
| Runner/worker/API targeted tests | Passed as part of SecureWise suite; tests cover matching, unsupported capability block, URL proof block, provider-neutral selection, ARM64/AMD64 normalization, single-job lease and stale lease recovery |
| Django `manage.py check` | Passed |
| `manage.py makemigrations --check --dry-run` | Passed; migration `0018_worker_active_job_lease` is current |
| Bash syntax checks | Passed for install, verify and uninstall scripts |
| Frontend `npm test -- --run` | 199 passed across 16 files |
| Frontend typecheck and production build | Passed |
| Frontend lint | Passed with 8 warnings in pre-existing unrelated files |
| Linux installer/service execution | Not run; environment is macOS |
| ARM64 host/scanner execution | Not run; ARM64 detection is unit-tested only |
| AMD64 Linux host execution | Not run; local scanner fixture from Phase 7.1 was not a generic Linux deployment |
| Oracle Always Free VM | Not provisioned or verified |
| AWS/Azure/GCP/Hetzner/DigitalOcean | Not provisioned or verified |
| GitHub Actions dispatch/result ingestion | Not implemented |
| Host nftables egress enforcement | Not configured or verified; missing proof file is tested to fail closed |

## Explicit gaps

- GitHub Actions secure static scanning and authenticated result ingestion are
  design-only; the documented contract is not an active runner.
- CPU/memory/disk/repository/evidence/organization scan quotas are not enforced
  as admission control. Existing URL concurrency/rate limits remain.
- Scanner licensing, signatures/update policy and architecture-specific
  release integrity are not audited. Runtime image scanning and Playwright
  remain contingent on actual host/architecture support.
- The nftables proof mechanism is not an external penetration test of host
  egress. Do not configure its environment flag or claim URL scanning enabled
  until firewall behavior is independently established.
- This change does not claim customer-beta or production readiness.
