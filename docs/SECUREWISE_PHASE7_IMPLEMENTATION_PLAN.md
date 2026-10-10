# SecureWise Phase 7 implementation plan

**Branch:** `feature/securewise-autopentest-foundation`  
**Baseline:** backend `a064175`; frontend `ef6b0c2`  
**Reviewed:** Phase 2–6 execution evidence, readiness audit, private-beta and
worker deployment docs, SecureWise models/API/serializers/services/scanners,
worker/runtime controls, and frontend dashboard, repositories, scans, reports,
AutoPentest and API client.

## Existing capability inventory

| Feature | Classification | Existing implementation to reuse | Phase 7 work / limits |
|---|---|---|---|
| Organizations and projects | Implemented, incomplete | `SecureWiseOrganization`, `SecureWiseMembership`, `SecureWiseProject`; organization-filtered ViewSets | A repository-to-integration cross-organization reference is now rejected and Git credential tests require an org admin. Customer invitation flow and requested member/viewer role model remain incomplete. |
| Repository records and private Git credentials | Reusable, incomplete | `SecureWiseRepository`, `SecureWiseGitIntegration`; existing encrypted credentials and clone helper | New GitHub App-linked repository mode coexists with legacy PAT/OAuth for existing integrations; the legacy mode is not presented as the App flow. |
| GitHub App flow | Partially implemented | New organization-bound installation/state/webhook models and API service | Manual App installation, state validation, read-only permission check, selected-repository synchronization, short-lived token use, webhook signature/replay handling are implemented with mocked-provider tests. No live App credentials, installation, webhook endpoint or customer repository was tested. |
| Static source scanning | Reusable, partially implemented | Existing worker queue, scanner adapters and findings; GitHub App archive ingestion added | App scans resolve and record a commit SHA and extract a bounded archive without running build scripts. Worker-host isolation and scanner license/version provenance remain unverified. |
| URL verification and customer target scope | Missing | Existing scan target URL and AutoPentest `PentestScope` are not ownership proof or target authorization records | Add target and challenge records, public-DNS and redirect validation, explicit separate legal authorization, expiration/revocation and passive-only first release. Enforce URL safety at request time and document required network egress controls. |
| Passive URL scanner | Incomplete / unsafe for SaaS | Existing DAST supports passive requests/ZAP, but Phase 6 blocks non-runtime targets | Reuse passive DAST only after target ownership, authorization, DNS/address and path scope checks; active tests stay disabled. |
| AutoPentest and evidence | Reusable, incomplete | `PentestSession`, scope, test cases/executions/evidence, approval workflow, Playwright and authenticated API adapters | Reuse for explicit synthetic-account assessments; do not broaden external testing until every request/redirect can enforce approved scope. |
| Findings and combined reports | Implemented, incomplete | `SecureWiseFinding`, scan histories, deduplication, report JSON/HTML/PDF | Add repository/commit/target linkage through existing scan metadata and report projection where safe; preserve engine/source and confirmed/suspected distinction. |
| Tenant API authorization | Partially implemented | Organization-scoped querysets, membership role helpers, cross-tenant tests | New installation/repository endpoints are organization-scoped, with admin-only selection; repository integration mismatch is rejected. URL target, invitation, deletion, evidence and full export review remains incomplete. |
| Frontend onboarding/dashboard | Partially implemented | Existing pages and API client; GitHub App connection and repository selection panel added to Repositories | Customer URL verification/authorization, combined assessment and complete guided dashboard are not implemented. |
| Customer data protection | Partially implemented | Encrypted credentials, redaction, temporary worker workspaces, report APIs | Add retention/deletion policy and project artifact deletion behavior; storage-region/backup/deletion guarantees require deployment decisions. |
| Worker isolation | Incomplete | Separate database-backed worker, exact-content digest gate, opt-in runtime switch, resource-limited scanner containers | Static-only customer jobs must not build or execute repository code. Production rootless/ephemeral pool, filesystem quotas and network egress are not verified; leave runtime builds disabled. |
| SAST/SCA engine licensing and rule provenance | Incomplete | Semgrep, Trivy, Gitleaks and local parsers are wired in the worker image | Verify exact engine versions, licenses, rule-set update strategy, and commercial SaaS obligations before customer launch; record versions and coverage per execution. |

## Delivery sequence and classification

1. **Tenant and lifecycle foundation — reusable/incomplete.** Reuse current
   organization/project/repository/scan/finding/report entities. Close and test
   cross-tenant and cross-project references, least-privilege roles, safe
   deletion, and artifact access.
2. **GitHub App private-repository slice — partially implemented.** Installation
   state, read-only callback validation, selected-repository sync, App-token
   archive retrieval and signed/idempotent webhook intake are implemented.
   Tests mock GitHub; live installation and private-repository scans require
   operator credentials and a reachable configured endpoint.
3. **Static-only immutable commit scan — partially implemented.** App archive
   scans capture the exact SHA and reject unsafe ZIP paths/symlinks/oversized
   archives. They never pass through the runtime-build gate. Actual scanner
   isolation and tool license/version audit remain required.
4. **Target ownership and legal authorization — missing.** Add HTTPS/DNS
   challenges with expiration and replay protection, and separately store
   explicit authorized host/port/path/method/time bounds. Ownership is not
   blanket authorization for subdomains or third-party services.
5. **Passive URL assessment — incomplete.** Reuse ZAP baseline only after
   authorization and per-request DNS/address/redirect/scope checks. Network
   egress restrictions are a deployment prerequisite. Active mode is disabled.
6. **Unified reports and retention — reusable/incomplete.** Keep the existing
   findings/report models and present code and URL scans side-by-side with
   honest skipped/unsupported coverage. Add customer deletion and documented
   retention; object storage/signing/region controls need deployment work.
7. **Customer dashboard — reusable/incomplete.** Extend existing screens and
   client contracts; show explicit status/coverage and never convert missing
   worker/scanner capability into success.
8. **Private-beta operation — incomplete.** No production app credentials,
   callback URL, dedicated production worker, rootless daemon, egress policy,
   production database, retention backend or data-processing region is
   available in this environment. Runtime builds and external active testing
   remain off.

## Acceptance gates

- Automated tests establish cross-organization denial for all introduced
  objects, scoped repositories and exports.
- GitHub App flow/webhook tests use mocked GitHub responses and cryptographic
  signature fixtures; they do not substitute for a deployed App installation.
- Static private-repository test asserts pinned commit, no token in URL/log,
  and no build/install/start hooks executed. Real private-repository testing
  requires operator-owned App credentials and installation.
- URL tests use only loopback or an owned local fixture; public target scans
  are not run. Authorization, public-address filtering, DNS revalidation,
  redirect rejection and safe passive behavior are tested.
- Reports preserve scanner observations versus verified findings and make
  skipped engines/coverage limitations explicit.
- Backend and frontend suites, Django checks, migration drift, lint/build and
  Docker fixture tests are run as available. Production behavior remains
  unverified absent deployment evidence.

## Phase 7 implementation update

The first vertical slice now covers GitHub App setup and repository selection,
commit-pinned archive retrieval, explicit static-only worker handling,
webhook signature/replay controls, and an organization integration-reference
fix. URL target authorization/scanning, complete membership onboarding,
combined reports, retention controls, production isolation and real GitHub
operations remain blockers; see the execution evidence and customer security
model for exact verification limits.
