# SecureWise private-beta threat model and operations

## Deployment status

This guide describes a constrained, explicitly authorized private beta. It is
not evidence that the deployed platform is production-ready. As of this
revision, no production worker host, live shared database, Render service,
egress firewall, filesystem quota, or rootless Docker deployment has been
independently verified. Do not enable repository runtime builds until the
worker host controls below have been established.

## Trust boundaries and threats

| Boundary | Threats | Enforceable controls and remaining risk |
|---|---|---|
| Browser/user → Django API | Forged scope, cross-tenant IDs, unauthorized cancellation or approval | Authenticated endpoints, organization-filtered querysets, role checks, exact target scopes, repository/project/report association validation, and API regression tests. |
| Django API → database | Cross-tenant rows, secrets in API responses, forged scan associations | Organization IDs come from project/session relations; report and scan serializers reject mismatched foreign objects; AutoPentest credentials are encrypted and write-only. Production database policies/backups remain deployment concerns. |
| Django API → worker queue | Duplicate claims, stale work, cancellation and worker outage | Atomic database claims, leases/heartbeats, cancellation state and single-job processing per worker process. The shared DB queue has no dead-letter queue, per-tenant quotas, or scale-out proof. |
| Worker → repository provider | Token leakage, malicious repository contents, clone URL SSRF | Short-lived provider credentials are used only for clone; scanner/runtime logs redact credential patterns; repository URL validation and clone timeouts are applied. Limit worker egress to approved Git endpoints and registries at the host firewall. |
| Repository → Docker build daemon | Dockerfile/package scripts can execute arbitrary code, consume resources, or reach network services | Runtime is blocked unless the repository UUID and exact reviewed tree SHA-256 match `SECUREWISE_TRUSTED_RUNTIME_CONTENT`; static analysis remains available without trust. The digest is not a sandbox. Build scripts still run with the Docker daemon's authority and network access. |
| Worker → Docker daemon | Socket API is effectively host authority for rootful Engine | Never mount the socket in Django, scanners, browser, or target containers. Use a dedicated disposable Linux host and a rootless Docker daemon owned by the dedicated worker account. Rootless Docker is strongly recommended but not independently verified here. |
| Docker target → host / other tenants | Privilege escalation, host filesystem reads, cross-job network access, secrets | Target containers have no socket or host mount, drop capabilities, use resource limits, read-only root filesystem, loopback-published ports, and isolated per-scan networks. Build-time execution remains on the daemon host; approved code can still exploit daemon/kernel vulnerabilities. |
| Scanner/browser → target | SSRF, redirects, out-of-scope requests, destructive actions | External/user-supplied DAST targets are blocked in the beta. DAST runs only on a worker-generated runtime attached to its per-scan internal network; authenticated API tests use bounded read-only operations and browser tests use fixed journeys with synthetic identities. Active testing and arbitrary scripts are not enabled. |
| Worker → AI provider | Source/credential disclosure, prompt injection, uncontrolled execution/cost | AI is optional and disabled by default; planner data is structured/redacted and AI output can annotate deterministic proposal keys only. No AI-generated code, command, URL, or executable test is accepted. |
| Customer credentials → assessment | Secret leakage into logs/evidence or scanner process | Authenticated test credentials are encrypted at rest in AutoPentest config, supplied only to the adapter, and redacted from evidence/log output. Use synthetic test accounts and never production credentials. |

The principal residual beta risk is untrusted build execution. The exact tree
digest prevents a trusted repository ID from silently authorizing changed
content, but it does not make an approved Dockerfile safe. Enable runtime builds
only for personally reviewed source revisions on a disposable, single-purpose
worker host with outbound firewall rules, Docker data-root disk quotas, and
resource limits applied to both the worker and Docker daemon. Otherwise use
static scans only.

## Exact-content runtime approval

Review the source revision and its Dockerfile, dependency declarations,
package lifecycle hooks, and startup scripts. On a clean checkout, calculate
the content digest:

```sh
./venv/bin/python manage.py securewise_runtime_digest /path/to/reviewed/checkout
```

The command includes relative paths, file bytes, and executable mode; it
ignores `.git`, common dependency/vendor folders and caches, rejects symlinks,
and stops above 100,000 files or 2 GiB. Configure the worker environment:

```text
SECUREWISE_TRUSTED_RUNTIME_CONTENT=<repository-uuid>=<sha256>[,<repository-uuid>=<sha256>...]
```

The cloned tree must match byte-for-byte and mode-for-mode. A change requires
new review and a new digest. The legacy repository-ID-only
`SECUREWISE_TRUSTED_RUNTIME_REPOSITORIES` variable grants no runtime
authorization. Exact digest approval is not sufficient by itself:
`SECUREWISE_RUNTIME_BUILDS_ENABLED=true` must also be set on the worker, and it
must remain unset until the rootless daemon, quotas, and egress restrictions
have been verified. The values are operator-managed controls, not a
tenant-facing approval workflow.

## Dedicated Linux worker

1. Provision a disposable Linux host or VM exclusively for SecureWise worker
   jobs. Create a non-login `securewise-worker` account; do not run Django web
   or customer application containers on the host.
2. Install a supported Docker Engine and configure a **rootless** daemon under
   this service account. Verify `docker version` returns both Client and
   Server when run as `securewise-worker`. Do not grant the account the rootful
   `docker` group. Ensure the rootless daemon starts at boot and its socket is
   available as `DOCKER_HOST=unix:///run/user/<uid>/docker.sock`.
3. Put Docker's `data-root` on a dedicated filesystem with a hard capacity
   quota. Apply CPU, memory, and process limits to the rootless daemon's
   systemd service as well as the worker service; build steps execute in the
   daemon, not necessarily in the worker process cgroup. Restrict outbound
   traffic to the database, approved Git hosts, and required image/scanner
   registries. Prevent access to cloud metadata and unrelated private networks.
   For a rootless user service, an operator can use
   `systemctl --user edit docker.service` with explicit `CPUQuota`,
   `MemoryMax`, and `TasksMax` values sized for the host; verify the effective
   unit/cgroup limits rather than assuming they applied.
4. Install the backend branch/revision and dependencies at
   `/opt/securewise/backend`; install/verify Docker CLI, Trivy, ZAP, Semgrep,
   Gitleaks, and the pinned Playwright runner image. Apply migrations through
   the normal release procedure against the shared database before starting
   the worker.
5. Create `/etc/securewise/worker.env`, owned by root and mode `0600`, with the
   shared database connection, Django settings/secret, SecureWise encryption
   key, short-lived Git credentials required for private clones, and reviewed
   runtime digest entries. Do not copy production Django secrets into scan
   containers. Keep AI credentials absent unless explicitly enabled and
   approved.
6. Copy `deploy/systemd/securewise-worker.service` to
   `/etc/systemd/system/securewise-worker.service`. Adjust `WorkingDirectory`,
   venv path, and rootless `DOCKER_HOST` in the unit/environment file. Ensure
   `/var/lib/securewise-worker` is owned by `securewise-worker`, then run:

   ```sh
   sudo systemctl daemon-reload
   sudo systemctl enable --now securewise-worker
   sudo systemctl status securewise-worker
   sudo journalctl -u securewise-worker -f
   ```

7. Confirm `/api/securewise/scans/worker-status/` for an authenticated
   organization member reports a fresh heartbeat, expected capabilities,
   resource telemetry, tenant-scoped queued/stale counts, and engine execution
   counts. Submit only an authorized controlled fixture first. Monitor the
   API heartbeat, systemd health, Docker disk usage, stale jobs, worker logs,
   and cleanup failures before onboarding users.

The included systemd unit applies least-privilege process isolation and CPU,
memory, task, file-descriptor and writable-path restrictions. Host egress
firewall policy, filesystem quotas, Docker daemon limits, rootless mode, and
scanner versions must still be configured and verified by the operator. Do not
enable build execution if any of these controls is absent.

## Onboarding and operational limitations

The existing UI makes authorization/scope review and scan mode explicit and
shows worker readiness only from available backend progress data. It cannot
verify production isolation, repository content approval, or browser capability
before a job is linked to scan progress. Keep the beta restricted to
operator-reviewed repositories and test accounts; tell users that discovery
coverage is not assurance and unsupported/skipped tests were not executed.

The current queue has no separate dead-letter queue, automatic queue-age alert
delivery, tenant rate/quota enforcement, or cleanup-reaper process. Resource
telemetry is best-effort process RSS/high-water mark, temporary filesystem
capacity, and load average; it does not measure Docker daemon or individual
container resource consumption. Configure external alerts and inspect Docker
resources until those gaps are addressed.

## Rollback

1. Stop new scan submissions and disable runtime execution by removing
   `SECUREWISE_TRUSTED_RUNTIME_CONTENT` from worker configuration.
2. Let in-flight jobs finish where safe, or cancel them through the API; stop
   the worker service to prevent new claims.
3. Preserve sanitized logs and database evidence. Remove only named
   `securewise-runtime-*`, `securewise-api-request-*`, `securewise-playwright-*`
   containers and their matching SecureWise per-scan networks/images after
   confirming ownership; do not prune shared Docker resources blindly.
4. Roll the worker code/image back to the last verified revision. Keep database
   migrations backward-compatible; take a database backup before migration
   rollback and do not drop new fields while a newer worker might still run.
5. Re-run worker capability, heartbeat, scope, tenant-isolation, and controlled
   fixture checks before reopening the beta.
