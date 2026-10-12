# SecureWise lightweight Oracle Linux worker

This is an optional deployment profile of the existing database-backed
`securewise_worker`, intended for an Ubuntu 24.04 AMD64 VM with 1 OCPU, 1 GB
RAM and 2 GB swap. Oracle is only a VM provider; the worker uses the same
database queue and code as any other Linux host. No Oracle SDK, queue or
application integration is introduced.

## What the profile runs

The current worker import path was traced from Django command startup through
worker registration/queue claiming, repository retrieval, scanner orchestration
and the static adapters. The relevant SecureWise path imports Django, DRF,
PostgreSQL, cryptography/JWT, HTTP/DNS and YAML libraries. Django app startup
also imports the existing APScheduler and DRF schema/CORS apps, including the
schema sidecar app registered in Django settings. The exact
minimal requirements are in
[`requirements-securewise-worker-lightweight.txt`](../requirements-securewise-worker-lightweight.txt).
The profile omits Semgrep, pandas, AI clients, PDF/Office/image processing,
S3/Twilio clients and browser tooling; those are not needed on the worker path.
Git remains an OS-level requirement for existing Git clone integrations.

Only repository-static SAST, SCA, secrets, IaC and local OpenAPI analysis are
eligible. Semgrep, Trivy and Gitleaks are deliberately disabled and are
reported as disabled; if those tools are absent in the standard profile, their
availability is reported as unavailable. Existing fallback checks are labeled
`fallback_heuristic`, and a scan that runs only fallback checks remains
`completed_partial`. Docker/container, ZAP/DAST, application runtime builds,
browser/Playwright, AutoPentest and customer URL scans are not executed or
advertised as capabilities. Full scans explicitly record container and DAST
as skipped. Jobs with URL, Docker image or external OpenAPI path inputs are
not eligible; the regular worker queue and lease protections are reused.

The import trace also includes Django app startup outside SecureWise, notably
APScheduler and schema/CORS apps. Those direct requirements are retained
rather than making a separate micro-app. No Django settings, database URL,
TLS mode, CA validation, authentication, queue lease or firewall policy is
changed. The deployed worker must use the same verified PostgreSQL TLS
configuration as the control plane.

## Oracle VM preparation

Provision a dedicated Ubuntu 24.04 x86_64 VM and an SSH key. Keep inbound
security-list rules limited to operator SSH access; the worker opens no
listening port. Permit only outbound connectivity required for the PostgreSQL
database, repository source, DNS/NTP and approved control-plane dependencies.
Do not grant this worker customer URL egress.

Connect by SSH, then verify the OS and Python:

```sh
uname -m
lsb_release -ds
sudo apt-get update
sudo apt-get install -y python3.12 python3.12-venv git ca-certificates
python3.12 --version
python3 --version
python3 -c 'import sys; assert sys.version_info[:2] == (3, 12)'
free -h
swapon --show
df -h /
```

The installer uses `/usr/bin/python3` by default. On Ubuntu 24.04 this is
Python 3.12; verify it before proceeding.

If the VM does not already have the requested 2 GB swap and the operator
approves a swapfile, create it once:

```sh
if ! swapon --show=NAME --noheadings | grep -qx /swapfile; then
  sudo fallocate -l 2G /swapfile
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile
  sudo swapon /swapfile
  grep -qFx '/swapfile none swap sw 0 0' /etc/fstab ||
    echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
fi
swapon --show
```

Do not run the block again if `/swapfile` already exists but is not active;
inspect it first to avoid overwriting existing data.

## Install without starting the worker

Deploy the reviewed backend branch/commit to the VM using the organization's
approved source checkout process. The installer does not clone source, connect
to a database, create credentials, change firewall rules, install Docker or
start the service. From the checked-out backend directory:

```sh
git status --short --branch
git rev-parse HEAD
sudo deploy/linux-worker/install.sh --source "$PWD" --lightweight
```

Lightweight mode uses the separate `/opt/securewise/venv-lightweight`,
requires Python 3.12, applies the restrictive lightweight systemd template
(100% CPU, 640 MB memory high watermark, 768 MB memory cap, 2 GB swap cap),
and leaves the regular `/opt/securewise/venv` and default installation path
unchanged. Neither template opens a port. The installer leaves
`securewise-worker` stopped.

Install the approved Aiven CA certificate at
`/etc/securewise/certs/aiven-ca.pem`, readable by `securewise-worker` but
writable only by root (for example, root-owned mode `0644` in a root-owned,
non-writable directory). Obtain the CA through the approved trusted channel;
do not substitute an unverified certificate.

Create `/etc/securewise/worker.env` through the approved secret-injection
process, owner `root:securewise-worker` and mode `0640`. Inject the same
PostgreSQL host, port, database, username and password values used by the
control plane, plus the TLS verification settings shown below. Do not copy
credentials into shell history or command-line arguments:

```text
DJANGO_SETTINGS_MODULE=<existing deployment settings module>
SECRET_KEY=<injected secret>
DB_HOST=<PostgreSQL host from secret manager>
DB_PORT=<PostgreSQL port from secret manager>
DB_NAME=<database name from secret manager>
DB_USER=<database username from secret manager>
DB_PASSWORD=<database password from secret manager>
DB_SSLMODE=verify-full
DB_SSLROOTCERT=/etc/securewise/certs/aiven-ca.pem
SECUREWISE_RUNNER_TYPE=linux_worker
SECUREWISE_RUNNER_PROVIDER=oracle
```

`verify-full` validates both the server certificate chain and the database
hostname. Do not downgrade the mode, omit the CA file, or disable certificate
or hostname verification to make a connection work. Never paste or print the
environment file. For the non-Oracle Render deployment, leave these optional
TLS environment variables unset to preserve its existing PostgreSQL behavior.

## Safe verification

Run local checks that do not connect to the database or claim jobs:

```sh
sudo -u securewise-worker \
  deploy/linux-worker/verify.sh --lightweight
```

To prove database registration and heartbeat connectivity, start the
installer-provided one-shot unit. It reads the protected environment file
through systemd rather than exposing values as command arguments:

```sh
sudo systemctl start securewise-worker-connectivity-check.service
```

The command registers with status `offline`, writes its heartbeat, then exits;
it never calls the job-claim path and cannot be selected as an active runner.
It proves Django startup plus database read/write access, not scanner
execution, external network enforcement or an Oracle scan. Inspect the
one-shot unit result:

```sh
sudo systemctl status securewise-worker-connectivity-check.service --no-pager
sudo journalctl -u securewise-worker-connectivity-check.service --no-pager
```

A synthetic controlled scan runs only in the isolated automated test database,
not against the Oracle deployment database:

```sh
python -m pytest tests/securewise/test_lightweight_worker.py -q
```

It creates a synthetic fixture scan without repository credentials, customer
URL or network target. It verifies that the existing queue dispatches a
static-only job and records Docker/DAST as skipped.

Only after reviewing credentials, database TLS, network allowlists, resource
limits and the offline probe result should an operator intentionally start
the long-running service:

```sh
sudo systemctl enable --now securewise-worker.service
sudo systemctl status securewise-worker.service --no-pager
sudo journalctl -u securewise-worker.service -f
```

Installation and verification do not start it automatically.

## Resource monitoring

The profile permits one job per worker (existing single-process queue
behavior). Observe usage during a controlled, approved small-repository scan:

```sh
free -h
swapon --show
df -h / /var/lib/securewise-worker
systemctl show securewise-worker \
  -p ActiveState -p CPUUsageNSec -p MemoryCurrent -p MemoryPeak \
  -p MemoryHigh -p MemoryMax -p MemorySwapMax -p TasksCurrent
sudo journalctl -u securewise-worker --since '1 hour ago' --no-pager
vmstat 5
top -b -n 1 | head -25
```

Do not rely on swap as normal capacity. On a 1 GB machine, Django startup,
repository cloning, Python fallback scanning and the database driver compete
with the OS for RAM; swap pressure can make jobs extremely slow, and the
768 MB service cap can terminate a job. Very large repositories, archives or
individual files are not demonstrated as reliable at this size. Use small
repositories only and monitor disk and memory. The existing clone
implementation does not enforce a per-repository disk quota. Move to the
standard recommended 2 vCPU / 8 GB VM (or larger) for regular scanning. This
profile is not suitable for AutoPentest or full scanner coverage.

## Rollback

To stop/remove the worker and connectivity-check units while preserving code,
environment, virtualenvs, state and logs:

```sh
sudo deploy/linux-worker/uninstall.sh
```

To switch the host back to the standard profile, stop the unit, reinstall the
reviewed source without `--lightweight` (the regular virtualenv is separate),
verify using the standard instructions, and enable only when approved:

```sh
sudo systemctl disable --now securewise-worker.service
sudo deploy/linux-worker/install.sh --source /path/to/gw-backend
sudo -u securewise-worker deploy/linux-worker/verify.sh
```

The standard profile includes considerably heavier optional dependencies and
does not become a safe Docker/browser worker merely by installing them; retain
its existing isolation requirements. Deleting either virtualenv or worker
state is an operator cleanup step and is not part of `uninstall.sh`.

## Dependency footprint and evidence limits

The resolved CPython 3.12 manylinux x86_64 lightweight requirements downloaded
22.23 MiB across 30 wheels in this development environment. The selected
dependencies occupied 74.39 MiB in an isolated Python 3.13 environment here;
installed size varies by OS, Python ABI and package version. For comparison,
the current environment's installed Semgrep files
occupied about 201.8 MiB and pandas about 37.5 MiB; neither is in the
lightweight requirements. The wheel measurement is a download-size estimate,
not an Oracle execution test.

This environment is macOS, not an accessible Oracle/Linux VM. Python 3.12
AMD64 compatibility was checked by resolving platform-specific wheels, but
the lightweight worker has not been installed or run on Oracle, Ubuntu,
Python 3.12, or against production credentials. Database connectivity and
provider behavior remain unverified until an operator runs the manual probe
on the VM.
