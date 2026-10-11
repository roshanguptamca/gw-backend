# Generic Linux worker deployment

This guide is provider-neutral. The same backend revision and worker command
can run on Oracle Cloud, AWS EC2, Azure Linux, Google Compute Engine, Hetzner,
DigitalOcean, a local Linux VM or an on-premises Linux host. The provider
offers compute/network/disk; SecureWise uses the same Django database queue
and scanner code.

## Sizing and prerequisites

- Ubuntu LTS or compatible Debian; x86-64/AMD64 or ARM64/AArch64.
- Start at 2 vCPU, 8 GB RAM, 40 GB disk for temporary workspaces and one
  concurrent static job. Use 4+ vCPU, 16 GB RAM and additional scratch storage
  for container image scans. Resource needs depend on repository/archive size.
- Python version must match the backend's supported deployment runtime.
- PostgreSQL connectivity to the existing shared production database must use
  TLS and the deployment's approved CA verification.
- Firewall/egress configuration, DNS, NTP, secret injection, backups and
  monitoring are operator responsibilities. Do not open inbound ports for the
  worker unless the infrastructure explicitly requires them; the current
  worker polls the database.

## Install

Deploy the backend source revision on the host, inspect the scripts, then:

```sh
sudo deploy/linux-worker/install.sh --source /path/to/gw-backend
```

The installer supports Ubuntu/Debian, creates the restricted service account,
installs Python requirements, and registers a systemd unit. It does not
install Docker, edit the firewall, set a Docker socket permission, make
credentials, or start the service. Set up `/etc/securewise/worker.env` via a
secret manager, mode `0640`, owner `root:securewise-worker`. Configure Django
settings and database TLS values exactly as the web service. Set
`SECUREWISE_RUNNER_TYPE=linux_worker` and a non-secret
`SECUREWISE_RUNNER_PROVIDER` label if desired.

Run `deploy/linux-worker/verify.sh` as the service user before enabling the
systemd service. It reports architecture, binary availability, Docker CLI vs
daemon, Django check/database health and service status without printing
secrets. Scanner versions are registered dynamically; unsupported tools are
omitted. Review systemd limits in `securewise-worker.service.example` against
host sizing.

## Scanner and architecture matrix

| Scanner/capability | AMD64 | ARM64 | Runtime behavior |
|---|---|---|---|
| SAST fallback rules | Python runtime | Python runtime | Available when Django worker dependencies run |
| Semgrep | Discovered at runtime if installed/executable | Discovered at runtime if installed/executable | Version stored; absent tool uses existing fallback and is not reported as Semgrep |
| SCA / IaC / API | Existing Python scanner adapters | Existing Python scanner adapters | Rule coverage and optional tool availability vary |
| Gitleaks | Discovered at runtime if installed/executable | Discovered at runtime if installed/executable | Version stored; no x86 binary is downloaded by the application |
| Trivy | Discovered at runtime if installed/executable | Discovered at runtime if installed/executable | Docker image scans additionally require a reachable daemon |
| ZAP | Host binary or daemon-capable pinned image | Host binary or compatible image/daemon | Actual CLI, Docker baseline or passive fallback recorded separately |
| Playwright Chromium | Docker daemon plus pinned runner image | Docker daemon plus image manifest for host architecture | Capability only advertised when the image is locally present |

The table describes discovery behavior, not certification of upstream packages
or scanner SaaS licensing. Check upstream release support, signature/hash,
license and architecture before installation. The worker does not silently
download a hardcoded x86 binary. If a tool is missing, its version/capability
is absent and execution uses the scanner's documented fallback or skipped
status.

## Network, data and security

Use outbound allowlists appropriate to the actual control plane: shared
database endpoint/port, GitHub API and archive endpoints for approved
repositories, approved scanner update sources and registries only when
necessary. Do not allow access to cloud metadata services. Block private,
loopback, link-local and metadata destinations for URL scanning and validate
the rule at the host/network layer. SecureWise source-level URL filtering is
defense in depth, not the firewall. See
[`SECUREWISE_RUNNER_SECURITY.md`](SECUREWISE_RUNNER_SECURITY.md).

Do not share `/var/lib/securewise-worker` across tenants or hosts. It is mode
0700 and used for temporary workspaces. Keep application and system logs
sanitized and configure bounded journald retention. Credentials belong in the
host secret manager/environment file, not Docker build arguments, URLs,
workflow artifacts or customer scanner containers. Static GitHub App scanning
does not run repository build scripts. Runtime build capability remains
disabled until ephemeral isolation has independent evidence.

## Update, recovery and provider migration

The database queue lease and heartbeat are provider-neutral. A worker
processes one job at a time; run multiple independent worker instances only
when each has a unique worker identity and its own capacity. Stale job leases
are recoverable after heartbeat loss. Check failed/partial engine diagnostics
before retrying, and inspect temporary workspaces after host interruption.

For update/rollback, deploy a pinned backend revision and compatible virtual
environment, run migrations once through the control-plane release process,
then restart workers. Keep old code and database backups according to the
organization's rollback policy. `uninstall.sh` removes only the systemd unit;
it preserves code, environment, account, state, virtualenv and firewall.

To migrate providers, provision a new VM, attach required encrypted
connectivity, inject the same environment configuration, install the same
code/scanner versions, verify health, then retire the old VM. No
provider-specific application code or database migration is needed. Do not
claim portability has been operationally verified until both old/new
environments execute an authorized controlled fixture job.
