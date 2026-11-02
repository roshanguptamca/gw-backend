# SecureWise Phase 7.4 execution evidence

**Date:** 2026-10-11
**Branch:** `feature/securewise-autopentest-foundation`
**Backend baseline:** `612f98e21eea9d39bf273bcb848939ce636a2aa4`
**Frontend baseline:** `173df9d1246df0ecc0546bf5901fde334554f981`
**Production/cloud verification:** none

## Environment and scanner versions

| Component | Observed environment |
|---|---|
| Host | macOS Darwin 25.6, ARM64 |
| Docker engine | Docker Desktop 29.2.0, `linux/aarch64` |
| Trivy | 0.72.0 container image |
| OWASP ZAP | Digest-pinned image `ghcr.io/zaproxy/zaproxy@sha256:7aaa659b0d43078febd82e29bad112285c370727e86ab8340444220e17d9f0d2`; baseline executed. The ZAP version string was not reliably emitted by the image CLI and is not asserted here. |
| Playwright | `securewise-playwright:1.57.0`, image digest `sha256:a91650b780b95586bf6bf8f733d7d8070b11041369b3473f4fab21d81d4864ab`, ARM64 |
| Other detected local tools | Semgrep 1.168.0; Gitleaks 8.30.1. These were not the engines used for the browser assessment. |

Docker-backed scanner execution happened in the local Docker Desktop Linux
engine. The Django test runner and queue service were not running on a Linux VM.
This proves ARM64 image execution on this local engine, not a portable Linux
host deployment.

## Controlled fixture execution

The target was the repository's deliberately vulnerable
`tests/fixtures/securewise-autopentest-api` Express fixture. It contains only
synthetic identities and invoice data, no destructive routes, and must not be
deployed publicly. Its reviewed source digest was allowlisted for the isolated
runtime test. Runtime and scanner containers communicate over a per-run
Docker `--internal` network; the browser container has no host mounts or Docker
socket.

### Authenticated API workflow

`tests/securewise/test_autopentest_worker.py::test_authenticated_api_scans_real_isolated_fixture_and_cleans_up`
submitted the session through the authenticated AutoPentest API, stored
synthetic bearer credentials encrypted, registered a local worker, claimed the
queued job, built and health-checked the fixture, and ran the bounded API
adapter against the isolated runtime.

Observed evidence: session `4b811df2-9c87-4feb-a64a-895bcd6898a6`,
unified scan `7a791b10-409e-4bc3-a6f8-2f70c025c13f`, session and API engine
completed, one confirmed cross-user ownership/IDOR case, three passing
authorization cases, one persisted `CWE-639` finding, credentials absent from
the finding evidence, and runtime/request containers, network, and generated
image removed.

### Authenticated browser workflow, report and retest

The opt-in test
`SECUREWISE_RUN_DOCKER_INTEGRATION=1 pytest -q tests/securewise/test_autopentest_worker.py::test_authenticated_browser_scans_real_fixture_and_cleans_up -s`
passed. It created the assessment through the API, used the existing queue
worker entry point, executed the pinned Playwright/Chromium journeys, read the
existing session report API, created a linked retest, and compared outcomes.

| Result | Evidence |
|---|---|
| Browser session | `b01f4ab4-8899-4e19-b762-9ce1a245cdb5` |
| Unified scan | `05542dc2-42dc-45f8-a905-0acf245ad133` |
| Session status | `completed` |
| Confirmed vulnerability | 1: deliberate cross-user invoice IDOR, `CWE-639` |
| Passed checks | 6: protected page, role denial, authorized admin access, logout, server-side session expiration, and cookie flags |
| Evidence | 7 sanitized screenshot/evidence records; report endpoint returned test cases and evidence |
| Retest session | `c78314ed-e4bd-465e-9428-0d21433736b4` |
| Retest result | IDOR remained `confirmed_vulnerability`; report comparison lists one still-confirmed case and no fixed case |
| Cleanup | Runtime container, Playwright container, isolated network, and generated image cleanup assertions passed |

The current Phase 7.4 browser test calls `process_next_job()` in the pytest
process; it does **not** itself launch a separate operating-system worker
process. A separate `securewise_worker` process was verified against a
persistent isolated local database in
[`SECUREWISE_PHASE4_EXECUTION_EVIDENCE.md`](SECUREWISE_PHASE4_EXECUTION_EVIDENCE.md),
but the full report-and-retest flow was not repeated through that standalone
process in Phase 7.4. Treat standalone worker execution for this exact
Phase 7.4 workflow as still requiring confirmation.

### Trivy and ZAP baseline

The opt-in
`tests/securewise/test_docker_integration.py::test_worker_runs_real_trivy_and_zap_against_controlled_fixture`
passed with actual scanner containers on ARM64. Evidence emitted by the test:

| Engine | Status | Observed result |
|---|---|---|
| Scan ID | — | `9e44cc6d-b9ca-4e19-ac54-93400ab94548` |
| Trivy | `completed` | 268 findings from the runtime-built fixture image; image source recorded as `runtime_build` |
| OWASP ZAP | `completed` | Actual `zap-baseline.py` run using `docker-zap-baseline`; execution recorded as `zap_baseline`, not HTTP fallback. The fixture produced a CSP-related alert. |
| Combined persisted findings | — | 273 |
| Cleanup | — | Runtime container and temporary image were absent after the run |

This is a passive baseline against an internally isolated, locally built
fixture, not a scan of a customer URL. The fixture uses HTTP, so TLS
configuration checks were not applicable and were not executed. ZAP baseline
does not perform active exploitation.

## Authorization, SSRF and network restrictions

- Existing target registration, ownership challenge expiry/single-use,
  authorization approval/revocation, tenant isolation, and scan gating API
  tests passed. Ownership-provider DNS/HTTPS responses are mocked in those
  tests; no live domain ownership challenge was verified.
- Added URL-control regression coverage for loopback, private, carrier-grade
  NAT, link-local/cloud metadata, IPv6 unique-local and link-local addresses,
  DNS rebinding pinning, out-of-scope redirects, and unapproved ports.
  These are application-layer tests with controlled DNS/transport doubles,
  not host firewall tests.
- `url_egress_enforced()` evaluated to `False`. No nftables policy or
  root-owned proof was installed. No external URL scan was submitted or
  enabled. URL scans must remain blocked in this environment.
- No DNS rebinding, redirect, or private-address attempt was sent over a real
  external network. The Docker runtime network is `--internal`, but this
  local network is not evidence of a production host-level egress firewall.

## Verification

| Check | Result |
|---|---|
| `pytest -q tests/securewise` | 428 passed, 4 skipped |
| Opt-in real authenticated API fixture integration | Passed |
| Opt-in real Playwright fixture, report, and retest integration | Passed |
| Opt-in real Trivy/ZAP fixture integration | Passed |
| Frontend Vitest suite | 199 passed across 16 files |
| Frontend typecheck and production build | Passed |
| Frontend lint | Passed with 8 warnings in unrelated pre-existing files |
| Live external URL target, DNS ownership proof, and host firewall | Not run |
| Standalone current-revision worker through the complete retest workflow | Not run; see worker-process limitation above |
| Linux VM/systemd, Oracle, or other cloud provider | Not provisioned or verified |
| Production deployment or tenant workflow | Not verified |

## Linux worker verification steps

For Oracle, AWS, Azure, GCP, Hetzner, DigitalOcean, or another supported Linux
VM, use the same provider-neutral worker code and follow
[`SECUREWISE_GENERIC_LINUX_WORKER.md`](SECUREWISE_GENERIC_LINUX_WORKER.md).
Oracle-specific provisioning is optional:
[`SECUREWISE_ORACLE_FREE_WORKER_SETUP.md`](SECUREWISE_ORACLE_FREE_WORKER_SETUP.md).

After provisioning a dedicated Ubuntu LTS/Debian ARM64 or AMD64 host and
deploying the feature branch:

```sh
sudo deploy/linux-worker/install.sh --source /path/to/gw-backend
# Inject /etc/securewise/worker.env with the deployment's Django settings,
# database TLS credentials, and SECUREWISE_RUNNER_TYPE=linux_worker using
# the host secret manager; do not put credentials on a command line.
sudo -u securewise-worker deploy/linux-worker/verify.sh
sudo systemctl enable --now securewise-worker
sudo journalctl -u securewise-worker -f
```

Confirm registration, current heartbeat, detected architecture, actual
scanner versions and capabilities in the existing runner readiness API. Then
submit the controlled fixture assessment and verify job claim, findings,
evidence, report, retest comparison, restart/recovery, and Docker cleanup
before using any customer target.

Do not enable external URL work merely by setting an environment variable.
First install and independently test host-level deny-by-default egress rules
from the worker's actual network namespace, including private, loopback,
link-local/metadata, DNS rebinding, redirect, host and port cases. Only after
operator review, run the structural verifier as root:

```sh
sudo deploy/linux-worker/verify.sh --check-url-egress
```

The worker environment must then explicitly set
`SECUREWISE_URL_EGRESS_ENFORCED=true` and point
`SECUREWISE_URL_EGRESS_PROOF_FILE` at the generated root-owned proof. The
proof is short-lived and structural only; independent network testing remains
mandatory. Without those controls, keep URL scans disabled.

## Acceptance status

The controlled fixture demonstrated real API, browser, ZAP baseline, and
Trivy execution, persisted findings/evidence, report retrieval, and a retest
that correctly kept the unresolved IDOR finding confirmed. It did not
demonstrate live URL ownership verification, a customer-approved external URL
assessment, a current-revision standalone worker process for the retest
workflow, a Linux VM, or host egress enforcement. The Phase 7.4 full
acceptance criterion and customer-beta readiness are therefore **not
established**.
