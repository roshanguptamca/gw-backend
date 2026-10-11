# Provider-neutral Linux worker deployment

This deployment uses the existing database-backed queue and does not use a
cloud SDK, provider queue, provider database, or provider-specific application
code. It supports Ubuntu/Debian x86-64 and ARM64 hosts when Python and the
installed scanner binaries support that architecture. Oracle, AWS, Azure,
Google Cloud, Hetzner, DigitalOcean, on-premises Linux, and local Linux VMs
are infrastructure choices only.

## Install and configure

1. Provision a dedicated Ubuntu LTS/Debian Linux VM; use at least 2 vCPU, 8 GB
   RAM and 40 GB temporary disk for one static scan at a time. Docker runtime
   and browser tests need more resources and must remain disabled until their
   isolation controls are independently verified.
2. Deploy the same backend revision to the host. Configure outbound network
   access only to the shared Django database, required GitHub API/archive
   endpoints, scanner update sources, and any approved registries. Network
   egress controls must block loopback, private, link-local, metadata and
   unapproved destinations. Do not expose a Docker socket to the web service,
   a scanner process, browser container, or customer runtime.
3. Install Python 3 and venv using the OS's approved provisioning process.
   Inspect `install.sh`, then run:

   ```sh
   sudo deploy/linux-worker/install.sh --source /path/to/gw-backend
   ```

   The script installs project Python dependencies and a systemd unit. It does
   not install Docker, configure firewall rules, make a Docker group member,
   or start the service. It is safe to rerun unless the target backend path is
   a real directory rather than the managed symlink.
4. Create `/etc/securewise/worker.env` via the host secret manager with mode
   `0640`, owner `root:securewise-worker`. Minimum values:

   ```text
   DJANGO_SETTINGS_MODULE=<deployed Django settings module>
   SECRET_KEY=<deployment secret>
   DATABASE_URL=<TLS PostgreSQL URL, injected by secret manager>
   SECUREWISE_RUNNER_TYPE=linux_worker
   SECUREWISE_RUNNER_PROVIDER=self_hosted
   ```

   Use the exact environment names and required database/TLS configuration
   from the deployed Django settings. GitHub App keys and repository
   credentials belong only on the runner that needs them. Never pass values as
   command-line arguments or print the env file.
5. Verify before enabling:

   ```sh
   sudo -u securewise-worker deploy/linux-worker/verify.sh
   sudo systemctl enable --now securewise-worker
   sudo journalctl -u securewise-worker -f
   ```

   `verify.sh` checks installed host tools, Django configuration/database
   connectivity and worker-command availability; it does not process a job.
   The worker registers actual scanner versions, architecture, available
   memory, Docker readiness and generic capabilities. Missing scanners remain
   absent rather than being advertised as installed.

## Docker, isolation and network policy

The base worker service has CPU, memory, task, filesystem and temporary
directory limits. Do not add `securewise-worker` to the rootful Docker group:
that group is effectively host root. If a controlled runtime scanner is
required, configure a dedicated rootless engine/service with per-job policy
and verify it independently. Rootless Docker is not by itself sufficient
multi-tenant isolation. Customer builds remain disabled by default.

The application's `SECUREWISE_URL_EGRESS_ENFORCED=true` declaration alone
does not enable URL work. It additionally requires a fresh, root-owned
`SECUREWISE_URL_EGRESS_PROOF_FILE` record. After an operator installs and
independently reviews a deny-by-default nftables policy in table
`inet securewise_egress`, run:

```sh
sudo deploy/linux-worker/verify.sh --check-url-egress
```

The checker requires an output hook with drop policy, IPv4/IPv6 blocked
address sets containing private, loopback, link-local, metadata and other
reserved ranges, and explicit drop rules. It records host identity and a
ruleset digest in the proof file. Configure the two environment variables in
the secret environment only after the rules have been independently reviewed.
Re-run verification after every firewall change; proof expires after five
minutes. This is a fail-closed deployment assertion and basic structure
check, not a substitute for independent network testing or a guarantee that
custom allow rules are safe. No firewall is installed or modified by these
scripts. Without current proof, URL scan scheduling remains blocked.

## Updates, rollback and provider migration

To update, deploy the same tested commit, install dependencies, run Django
checks and migration checks, then restart the service. Migrations belong to
the control-plane deployment/operator process, not each worker. Roll back by
restoring the previous code revision and restarting the worker; retain
compatible database migrations. `uninstall.sh` only removes/disables the
systemd unit and deliberately preserves data, environment, account, code,
firewall and virtualenv.

Moving to another provider requires a Linux VM, network rules, database
connectivity, secrets injection and the same worker code/configuration. Do not
change Django/Python scanner logic or claim a cloud runner was verified until
it has actually checked in and processed a controlled fixture job.

## Optional 1 GB lightweight profile

For Ubuntu 24.04 AMD64 with Python 3.12, the installer has an explicit opt-in
mode:

```sh
sudo deploy/linux-worker/install.sh --source /path/to/gw-backend --lightweight
```

It installs `requirements-securewise-worker-lightweight.txt` into a separate
`/opt/securewise/venv-lightweight` and selects
`securewise-worker-lightweight.service.example`. The default installation
continues to use the full requirements file, original virtualenv and original
service template.

The lightweight worker can claim repository-static scans (SAST, SCA, secrets,
IaC and local OpenAPI analysis) only. Semgrep, Trivy, Gitleaks, ZAP, Docker,
application runtime builds, browser tests, AutoPentest jobs and customer URL
scans are disabled. Fallback checks remain labeled as fallback coverage and
optional external scanner availability is recorded in the engine metadata.
The database-only connectivity probe registers offline, updates its
heartbeat, and exits without claiming jobs. See
[`SECUREWISE_ORACLE_FREE_LIGHTWEIGHT_WORKER.md`](../../docs/SECUREWISE_ORACLE_FREE_LIGHTWEIGHT_WORKER.md)
for exact commands and resource limitations.
