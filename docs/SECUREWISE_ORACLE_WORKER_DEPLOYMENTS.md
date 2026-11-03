# Independent Oracle worker deployments

Status: implementation prepared for local review. Neither VM has been inspected,
provisioned, restarted or deployed by this change. It does not deploy Django on
Render, run migrations, alter databases, install Docker or launch test scans.

| Environment | Oracle host | GitHub environment |
|---|---|---|
| ACC | `158.101.218.17` | `acc` |
| Production | `152.70.53.242` | `production` |

This is an **opt-in managed installation**. Existing `install.sh`, legacy service
units, symlinks, venvs and ACC secret files are unchanged. Managed releases live
under `/opt/securewise/managed/<environment>/<profile>/`; the existing ACC worker
continues running until an operator explicitly approves migration. Do not copy
`worker.env` or `website-worker.env` from ACC to production.

## Profiles and trust boundaries

Each workflow run updates **one** profile. Deploy environments independently.

| Profile | Exact advertised capabilities | Memory cap |
|---|---|---|
| `lightweight` | `sast`, `sca`, `secrets`, `iac`, `api` | 768 MB |
| `website_passive` | `dast`, `url_egress_restricted` | 224 MB, no swap |

Capabilities must match actual discovery and the database registration, not a
workflow input. Lightweight scans use the existing partial-result static
fallbacks; they do not imply Semgrep/Trivy/Gitleaks availability. Website scans
remain authorized, scoped `passive_http` only. No runtime builds, active scans,
Docker, browser or experimental authenticated API capability is enabled.

The managed runtime discards inherited environment variables (including proxies,
`DATABASE_URL`, Python overrides and experimental flags). It injects only the
allowlisted configuration and enforced profile settings. Before Django app
startup/database access it checks effective PostgreSQL connection settings, TLS,
explicit encryption key and Django secret against injected configuration. It
then uses the existing backend settings module. Settings that select another
database, derive another key or override the CA fail closed; this is not silently
worked around. Local policy restrictions prevent inspecting/executing
`guidewisey/settings.py`, so this effective-settings compatibility remains a
required approved VM preflight, not a claimed live result.

Database identity is SHA-256 of compact JSON `[lowercase host, canonical string
port, database name, database role]`. It excludes passwords for rotation. This is
an operator-enrolled connection identity, **not** an independently discovered
database environment label: trusted operators must confirm the host/database/role
against the correct control plane before enrollment. DNS aliases must not be used
to disguise a shared database. Separate database roles alone are not sufficient:
ACC and production must have separate databases and encryption keys.

## Initial provisioning (manual, approval required)

Do this separately on each VM using its own credentials. Nothing below is part of
an automatic first connection or implied approval to change ACC.

1. Inventory the VM, existing services, OS/architecture, RAM/swap, database TLS
   access and trusted SSH host key out of band. Use Ubuntu 24.04 with Python 3.12
   and `python3.12-venv`, Git and CA certificates. Retain the current ACC setup.
   Do not assume both memory caps fit a 1-GB host without measuring headroom.
2. Create the non-login `securewise-worker` user/group if absent. Create
   `/opt/securewise`, `/etc/securewise` and `/etc/securewise/certs`, root-owned and
   not group/world writable. `/opt/securewise` must be traversable (0755);
   `/etc/securewise` can be `root:securewise-worker` 0750.
   Deployments stage dependencies as root; worker services cannot modify code,
   venvs, unit files or configuration.
3. Install that environment's independently verified database CA under
   `/etc/securewise/certs/`, root-owned, readable by the worker, not writable by
   others. Use `DB_SSLMODE=verify-full` and an absolute `DB_SSLROOTCERT` path.
   Do not disable hostname or certificate validation.
4. Populate a protected secret-manager document using the keys in
   `deploy/oracle-worker/production-config.example.json`. The template contains
   names only. Every value must be a nonempty string, including `DB_PORT`.
   Use the environment's actual control-plane database/role and encryption key,
   an explicit valid Fernet key (never the development derived-key fallback),
   and its Django `SECRET_KEY`. Do not print or paste secrets into shell history.
   Separate profile secrets may use least-privilege roles; enroll their identities
   consistently (the current host enrollment expects the same DB role for both).
5. From a reviewed checkout, calculate fingerprints **locally in the trusted
   secret-handling environment**, without printing the underlying configuration:

   ```sh
   # /root/worker-config.json is a protected secret-manager export for this VM.
   # Run separately for each environment; transfer only reviewed fingerprints.
   sudo python3.12 - /path/to/reviewed/backend /root/worker-config.json <<'PY'
   import json, pathlib, sys
   sys.path.insert(0, str(pathlib.Path(sys.argv[1]) / "deploy/oracle-worker"))
   from policy import database_identity, digest
   config = json.loads(pathlib.Path(sys.argv[2]).read_text())
   print("database_sha256:", database_identity(config))
   print("encryption_key_sha256:", digest(config["SECUREWISE_ENCRYPTION_KEY"]))
   PY
   ```

6. Fill `host-identity.example.json` and install as
   `/etc/securewise/oracle-worker.json`, `root:securewise-worker` 0640.
   Set `environment` and `host` to the row above. Set `database_sha256` and
   `encryption_key_sha256` to this environment's verified values.
   Set `other_database_sha256` and `other_encryption_key_sha256` to the independently
   confirmed **other** environment fingerprints, never its credentials/keys.
   Missing, equal or mismatched fingerprints reject deployment and every startup.
   Review enrollment independently of GitHub secrets; never regenerate enrollment
   automatically from whatever secrets a workflow supplies.
7. For passive websites, provision `nftables` through the separately approved
   procedure in [the passive worker guide](SECUREWISE_PASSIVE_WEBSITE_WORKER.md).
   Review/apply `securewise-website-egress.nft.example` with a second SSH session
   and delayed network rollback. It is host-wide deny-by-default; retain required
   database TLS, SSH response, DNS/NTP and public HTTPS connectivity. Do not add a
   broad private/metadata exception for the worker. Validate SSH access and the
   full IPv4/IPv6 ruleset, including rule ordering. The workflow never flushes,
   replaces or relaxes firewall rules.
8. For website enrollment, record the exact reviewed ruleset hash using
   `sudo nft list ruleset | sha256sum` as `egress_ruleset_sha256`. The managed proof
   refresher compares this full hash before delegating to the existing structural
   verifier. The worker also requires this hash in the fresh root-owned proof,
   so a newly generated proof for another ruleset is rejected. Counters or other
   dynamic rules may change full output: resolve this in the reviewed firewall
   configuration, not by accepting arbitrary new hashes during deployment.
9. Install the two `securewise-managed-egress@` templates from
   `deploy/oracle-worker/` into `/etc/systemd/system/`, root-owned 0644. After
   `systemctl daemon-reload`, enable/start
   `securewise-managed-egress@production.timer` (or `@acc.timer`).
   Before the first release its service can fail because `current` is absent;
   the deploy preflight generates proof directly from the candidate release,
   then subsequent ticks use the activated release. Proof expires after five
   minutes and refreshes every minute. ACC may initially retain its existing
   `securewise-egress-proof.timer`; it is not overwritten. The managed worker
   still pins the approved firewall hash.
10. Create a dedicated, environment-specific deployment SSH account/key with
    approved root deployment privilege. Running uploaded Python through sudo is
    effectively root access, **not** a constrained sudo sandbox. Restrict key
    custody, source access, environment approvals and SSH ingress accordingly.
    Never reuse ACC's SSH key for production.

Do not run the legacy installer as a shortcut for managed production installation:
it targets the legacy paths. First approved managed deployment creates only its
own service and release directories.

### GitHub environment setup (separate administrative approval)

Create `acc` and `production` environments **before** dispatching the workflow.
The workflow does not create/configure environment protections.

For production, configure required human reviewers, prevent self-review, restrict
deployment branches to `main`, disallow administrator bypass where supported, and
protect `main`/workflow modifications. A repository plan supporting required
reviewers is necessary; do not deploy production without it. The workflow
additionally refuses non-main production dispatches, requires the selected SHA to
be an ancestor of current `origin/main`, and checks that required reviewers and
prevent-self-review exist through GitHub's environment API. If that read is
denied, deployment fails closed: resolve approved token/repository permissions,
do not remove the check.

Configure these independently in **each GitHub environment**, not repository-wide:

| Type | Name | Value |
|---|---|---|
| Variable | `WORKER_SSH_USER` | Dedicated deployment account |
| Secret | `WORKER_SSH_PRIVATE_KEY` | That VM's deployment key |
| Secret | `WORKER_SSH_KNOWN_HOSTS` | Out-of-band verified host-key entry for the exact IP |
| Secret | `LIGHTWEIGHT_WORKER_CONFIG` | Complete allowlisted JSON secret document |
| Secret | `WEBSITE_WORKER_CONFIG` | Complete allowlisted JSON secret document |

Do not use `ssh-keyscan` at deployment time, disable strict host-key checking,
upload a secret artifact or copy ACC configuration into production. Host IPs are
selected by environment in the workflow, not a free-form SSH host input.

### ACC adoption

Inventory existing in-flight jobs and preserve legacy units, symlinks, secret
files and venvs. Schedule an approved maintenance window; allow legacy work to
finish, then explicitly stop/disable only the legacy profile being migrated.
The new deployer refuses that profile while its legacy service is active.
Do not run legacy and managed workers simultaneously just to bypass this check.
Rollback to the legacy installation is a separate operator action after draining
the managed worker; automation never rewrites or restarts legacy services.

## Subsequent updates

After review, merge/publish the workflow only with approval. Dispatch
**Deploy Oracle workers** with `environment`, one supported `profile`, and the
full reviewed backend commit SHA. Begin with ACC. Production requires its own
environment approval and production-specific secrets.

Updates are serialized per environment, including across profiles; running
deployments are not cancelled by a newer dispatch. A VM-local nonblocking lock
also prevents concurrent manual/workflow updates across that environment's profiles.

The workflow uploads tracked source (excluding dotenv files), allowlisted JSON
and bootstrap code over pinned SSH. No secret is placed in command arguments.
The VM creates a separate root-owned release and Python 3.12 venv, installs the
existing lightweight requirements, and verifies configuration, capabilities and
an **offline-only** registration/heartbeat probe before changing `current`.
Subprocess output stays in root-only `/var/log/securewise-worker-deployments/`;
CI prints only high-level status, failure classes and diagnostic paths.

The running managed worker is drained via a root-owned `/run` flag. It finishes
its current synchronous job, exits between jobs, and marks itself offline.
Deployment waits up to ten minutes, never forcibly killing an in-flight job.
It atomically switches `current`, starts the sandboxed service, and verifies
fresh online registration, **two advancing heartbeat timestamps**, exact profile
and capabilities before enabling boot startup. Successful updates retain
`previous`, including its venv and secret document. No release cleanup is automatic.

Starting a worker resumes processing already-authorized jobs for its profile.
The deployment probes and health checks never enqueue, claim or execute scans.
Use a controlled queue/maintenance window for the first approved rollout.
Dependency versions follow the existing bounded manifest, not a new fully pinned
lockfile; rollback reuses the already-installed old venv rather than reinstalling.

## Health verification (approved VM operations only)

Example for production passive websites; replace both environment and profile
consistently for ACC/lightweight:

```sh
sudo systemctl is-active securewise-managed-production-website_passive.service
sudo systemctl is-active securewise-managed-egress@production.timer
sudo /usr/bin/python3.12 \
  /opt/securewise/managed/production/website_passive/current/code/deploy/oracle-worker/proof.py \
  production
sudo systemd-run --quiet --wait --pipe --collect \
  --property=User=securewise-worker --property=Group=securewise-worker \
  --property=StateDirectory=securewise-managed-production-website_passive \
  --property=StateDirectoryMode=0700 \
  /opt/securewise/managed/production/website_passive/current/venv/bin/python \
  /opt/securewise/managed/production/website_passive/current/code/deploy/oracle-worker/runtime.py \
  health production website_passive
```

`probe` instead of `health` performs an offline-only connectivity write; `health`
only reads registrations. Both connect to the enrolled shared database and
therefore require approval. Never use `securewise_worker --once` as a health
check: it can execute a queued job. Inspect protected service journals and root
deployment logs locally; do not paste secret-bearing diagnostics into CI/issues.

## Rollback

Failures before the switch leave the old release running (a timed-out drain
leaves it draining). Failures after switching drain the candidate, restore the
previous release/config/venv, restart it and verify its heartbeat/capabilities.
The original deployment still fails even if rollback succeeds. First-install
failure leaves the managed worker stopped and disabled. A drain or rollback
health failure is reported as failure, not a successful restoration; operator
intervention is required. Firewall rules are never removed during rollback.

For an approved manual rollback, use the deployed root-owned tool:

```sh
sudo /usr/bin/python3.12 -E -s \
  /opt/securewise/managed/production/website_passive/current/code/deploy/oracle-worker/deploy.py \
  production website_passive \
  --config /opt/securewise/managed/production/website_passive/current/config.json \
  --rollback
```

The same lock, identity checks, preflight, drain, switch and health checks apply.
Rollback is refused if the previous release's database/key no longer matches
enrollment. Coordinate secret rotation, encrypted data compatibility and database
schema compatibility separately; no tool can restore revoked credentials or
reverse backend migrations. Rollback never downgrades the backend/database.

If drain times out, inspect job execution first. Do not clear the flag while
deployment/rollback is still in progress. Once the operation has exited and work
has drained, an operator can retry deployment (which clears the flag safely), or
explicitly remove the exact profile flag and start the known-good current unit.
Do not force-kill work or weaken network controls to make a health check green.
