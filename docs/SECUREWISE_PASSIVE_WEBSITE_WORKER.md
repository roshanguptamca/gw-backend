# SecureWise passive website worker (`website_passive`)

A separate, opt-in worker profile that runs **authorized passive HTTP checks
only** (the existing `passive_http` DAST path). It has no Docker, no ZAP and no
repository access, and it is not a penetration test. It does not change the
`lightweight` source-scanning worker.

## What it does

- Claims only `dast` scans that have a `target_url`, a testing authorization,
  and no repository, Docker image or API spec.
- Sends read-only HTTPS requests, pinned to the validated IP, and reviews
  security headers, cookies, CORS and verbose headers.
- Follows no redirect outside the authorized host/port/path scope. A redirect
  to another host (for example `guidewisey.com` to `www.guidewisey.com`) is
  reported as skipped: authorize the final host separately.
- Never claims pentest or active-scan coverage. Overall status is
  `completed_partial` because no full external scanner ran; the UI explains it.

## Honest capabilities

The worker advertises `dast` and `url_egress_restricted` **only** while
`SECUREWISE_URL_EGRESS_ENFORCED=true` and a fresh, root-owned egress proof
exists. Otherwise it advertises nothing and claims no jobs.

## Components (examples under `deploy/linux-worker/`)

| File | Purpose |
|---|---|
| `securewise-website-worker.service.example` | Worker unit (`CPUQuota=40%`, `MemoryHigh=160M`, `MemoryMax=224M`, `MemorySwapMax=0`) |
| `securewise-website-egress.nft.example` | Deny-by-default output policy, table `inet securewise_egress` |
| `securewise-egress-proof.service/.timer.example` | Runs `verify.sh --egress-only` every 60 s |
| `verify.sh --egress-only` | Checks the loaded ruleset and writes the proof |

The proof (`/etc/securewise/url-egress-verification.json`) must be a root-owned
regular file, not group/world writable, with matching hostname and
`ruleset_sha256`, and at most 300 s old. The timer keeps it fresh; if the timer
or ruleset disappears the proof expires and the capabilities vanish (fail closed).

The nft policy blocks private, loopback, link-local and metadata ranges and
allows only DNS/NTP/DHCP to the cloud resolver, root-only metadata access for
the cloud agent, and tcp 80/443/5432 (Neon). It is host-wide and is **not
persisted across reboot**, which fails closed.

## Deployment checklist (requires approval)

1. Stage code in a root-owned directory (`/opt/securewise/website-backend`)
   separate from the lightweight worker's tree. Do not copy `.env` files.
2. Apply the nft policy with an auto-revert timer
   (`systemd-run --on-active=240 nft delete table inet securewise_egress`),
   test a **new** SSH session, DNS, the DB, and https, then cancel the timer.
3. Run `verify.sh --egress-only` and confirm the proof file.
4. Create `/etc/securewise/website-worker.env` (`root:securewise-worker`, 0640)
   from the existing worker env plus `SECUREWISE_WORKER_PROFILE=website_passive`,
   `SECUREWISE_URL_EGRESS_ENFORCED=true`,
   `SECUREWISE_URL_EGRESS_PROOF_FILE=/etc/securewise/url-egress-verification.json`.
   The encryption key must match the API (fingerprint is checked).
5. Install the units, `daemon-reload`, enable the proof timer, start the worker.
6. Confirm registration shows only `dast` and `url_egress_restricted` and the
   UI `website_readiness` is `ready`.
7. Apply migrations before the API uses new fields (`0019` is additive).

## Authorization and ownership

Targets are verified by DNS TXT at `_securewise-verification.<host>` or the
well-known HTTPS file. Authorizations are per host/port/path, `passive_http`
only, up to 30 days (use about 1 hour for experiments). Run verification and
authorization through the application flow; do not write records directly.

## Resource usage (observed, ACC 1 OCPU/1 GB VM)

Idle and during a single scan the worker stayed near 100 MB (peak 104 MB, limit
224 MB), about 0.6% CPU, no restarts or OOM. One scan of one page takes under a
second. This is one data point, not a capacity guarantee.

## Rollback

```text
sudo systemctl disable --now securewise-website-worker.service securewise-egress-proof.timer
sudo nft delete table inet securewise_egress
sudo rm -f /etc/securewise/url-egress-verification.json /etc/securewise/website-worker.env
sudo rm -f /etc/systemd/system/securewise-website-worker.service \
  /etc/systemd/system/securewise-egress-proof.{service,timer}
sudo systemctl daemon-reload
```

Revoke open authorizations via the application. Do not touch the lightweight
worker, shared keys or the database. Queued website scans stay queued until a
compatible worker returns.

## Execution audit and readiness notes

- `scanner_metadata["execution"]` records `worker_id`, `claimed_at`, `started_at` and `completed_at` for every scan. `worker_claimed_at` is cleared on completion by design; the execution record is the durable claim history. `scan_started` and `scan_completed` audit entries include `worker_id`. No secrets are logged. (Requires the worker to run this code.)
- The control-plane API judges URL egress from a fresh worker registration advertising `url_egress_restricted`. The worker still requires its local egress proof before claiming a job.
- Passive website readiness does not depend on credential-encryption key parity, since no credentials are decrypted. Credential-bearing flows keep their own key check.
- A retest creates a new scan. Findings are deduplicated per project and fingerprint and stay visible on every scan that first found or re-detected them. A rejected start cancels the just-created scan so no pending orphan remains.
