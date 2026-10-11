# SecureWise customer security model

**Status:** implementation guidance and source-level controls; not a production
security certification. No production deployment, tenant boundary, worker host,
egress firewall, object storage, or data region was verified for Phase 7.

## Trust boundaries

| Boundary | Current controls | Remaining risk / required operation |
|---|---|---|
| Customer browser → Django API | Session authentication/CSRF, organization-filtered API querysets, membership role checks, relation validation, single-use GitHub setup state | Complete organization invitation/member/viewer role workflow and run a deployed cross-tenant assessment. |
| Django → database | Organization/repository/scan relations, encrypted legacy Git credentials, hashed short-lived GitHub state, installation metadata without access tokens, webhook delivery replay ledger | Production key rotation, backups, database access separation, retention and restore evidence remain deployment work. |
| Django → GitHub App | App JWT signed from worker/API environment configuration; API host fixed to `api.github.com`; callback state tied to the initiating user and org admin; only read-permission installations accepted | Configure the GitHub App and callback/webhook URLs. App credentials are not configured in this development environment. |
| GitHub App → repository archive | Installation token generated for API access and held only in memory; selected repository IDs verified against that installation; archive resolved to a commit SHA; redirects accepted only to HTTPS `codeload.github.com`; archive paths, symlinks, file count and expanded size checked | Download requires outbound access to GitHub API and codeload. Apply worker-host egress policy and test an operator-owned private repository before beta. |
| Worker → repository source | App scans use a source archive, not `git clone`; code scanners read a temporary directory; GitHub App source never passes the runtime content digest gate | Scanners run in the existing worker trust domain, which has Docker daemon authority. Parser/tool compromise and host-level isolation are not eliminated. Use a dedicated disposable worker, least privilege and firewall restrictions. |
| Worker → customer build/runtime | GitHub App source is static-only; runtime build is blocked for that access mode. Existing runtime builds still need both reviewed exact-content approval and explicit worker opt-in. | A digest is not a sandbox. Do not enable customer runtime builds until ephemeral/rootless isolation, daemon quotas, egress controls and teardown are independently verified. |
| Worker → customer URL | Source-level target ownership challenge, separate time-bound authorization, exact host/port/path scope, pinned HTTPS requests, public-address validation, redirect checks, rate/concurrency limits and passive GET-only checks | No network-layer egress firewall or isolated URL worker has been verified. The capability flag is an operator attestation only; never enable external scans until the host/network policy is independently enforced and checked. No customer URL scan has run. |
| Worker → AI provider | AI planner remains optional and disabled unless configured; source code is not sent by the GitHub App flow. | Provider data processing and retention require explicit customer choice and contractual review. |
| Evidence/reports → customer | Existing organization-scoped findings, evidence and report querysets; reports remain in existing database models | Combined repository+URL reports, signed short-lived object-storage links, configurable retention and customer deletion workflow are incomplete. |

## GitHub App handling

- Do not collect customer personal access tokens for private repository scanning.
- Configure a GitHub App with repository metadata and contents **read-only**
  permissions, and only the installation/repository webhook events needed
  for lifecycle updates. Do not grant write permissions. The callback rejects
  an installation reporting a write permission.
- App ID, PEM private key, webhook secret, App slug and frontend return URL are
  operator-injected environment values. Do not place them in source,
  database metadata, frontend configuration, scan findings or logs.
- Installation access tokens are requested for API/archive operations and are
  not persisted. GitHub App repository rows expose canonical repository
  metadata only; archive download URLs and tokens are not returned to clients.
- Setup state is random, stored only as a SHA-256 digest, bound to the signed-in
  organization admin, expires after ten minutes, and is consumed once.
  Installation IDs are bound to one SecureWise organization. First-time
  registration requires a newly created installation in the active flow.
- Webhooks require `X-Hub-Signature-256`; `X-GitHub-Delivery` is uniquely
  recorded for replay suppression. Webhook bodies are not retained; only
  event type and a payload digest are recorded. Installation suspension and
  removal block subsequent archive downloads.

## Static-only behavior

GitHub App scans resolve the selected branch to a 40-character commit SHA,
download a source archive for that immutable SHA, and run the configured
static scanner engines against extracted source. Archive extraction rejects
path traversal and symbolic links and limits file count and expanded bytes.
The source tree is not passed to a repository build, package installation,
startup hook, or customer runtime. Container analysis is skipped when it would
require an unapproved build. An explicitly configured image scan remains a
separate scanner operation and does not execute the repository Dockerfile.

Static scanning is not host isolation: scanner binaries process adversarial
source files inside the existing worker process/host. The worker must not be
shared with the Django web process, must use an isolated workspace, and must
have constrained database/GitHub/registry egress. The repository currently
does not provide verified per-job VM/microVM isolation or daemonless scanner
execution.

## URL assessment safety

Technical ownership verification and legal authorization are separate
requirements. The source now supports expiring, single-use DNS TXT or HTTPS
well-known challenges and a separate organization-admin approval for exact
host, approved HTTPS port, path allow/exclusions, passive HTTP method and
expiry. Ownership revocation revokes active authorizations. Scan creation,
start and each request/redirect recheck the authorization. Hostnames are
resolved and all results must be globally routable; the connection is pinned
to a validated address while TLS verifies the original hostname. Redirects,
ports, paths, response size and time are bounded. Proxy environment variables
are not used; only GET requests are issued. External ZAP and active tests
remain unavailable.

These are application-level controls, not network isolation. The worker
registration's `url_egress_restricted` capability is derived from
`SECUREWISE_URL_EGRESS_ENFORCED=true`; neither value verifies nftables,
firewall policy, a dedicated host or separate network namespace. This flag was
not enabled here. Before any external URL job can be enabled, deploy a
dedicated URL worker behind network-layer deny rules for private, loopback,
link-local, metadata and other forbidden destinations, restrict outbound
ports/proxies, test redirect and DNS-rebinding cases against the actual host
policy, and capture independent deployment evidence. Until then, the API gate
must remain disabled; do not bypass it by posting `target_url` directly.

## Customer data lifecycle

Repository archive workspaces are temporary and removed when the scan returns.
Findings, report payloads, scan metadata, and AutoPentest evidence are retained
in existing database models. This change adds no object storage or retention
policy, no user-facing project deletion workflow, and no verified backup
deletion process. Establish retention periods, customer export/deletion,
backup expiry and regional processing before private beta. Do not promise
GDPR deletion or a processing region based only on current source behavior.
