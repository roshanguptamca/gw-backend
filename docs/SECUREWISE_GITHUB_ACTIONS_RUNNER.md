# GitHub Actions runner status and security contract

**Status: not implemented.** SecureWise does not currently install, dispatch,
or ingest results from a customer GitHub Actions workflow. The generic
`github_actions` runner type is metadata only; it is not an authenticated
result-ingestion service. Existing GitHub App archive scans run through the
database-backed Linux worker.

## Required design before enabling

A customer-owned, manually invoked workflow is preferred over SecureWise
dispatching arbitrary customer code. It must:

- Use `workflow_dispatch`, pin actions by immutable commit SHA and run against
  an explicitly selected repository/commit; never use `pull_request_target`
  to check out or execute untrusted PR code.
- Confirm the commit SHA with GitHub context and send it through a per-job
  authenticated contract bound server-side to the selected
  organization/repository/scan. Never accept a tenant ID as authority.
- Run static-only scanning on source at the immutable commit. Do not install
  dependencies, execute hooks, run customer build scripts or execute
  repository binaries. Use pinned, supported scanner versions and publish
  their actual versions and exit statuses.
- Use only short-lived GitHub OIDC or job-scoped credentials where an endpoint
  supports them. Never add a long-lived PAT, database credential or GitHub App
  private key to workflow secrets or logs.
- Upload a bounded, schema-validated artifact with signed/checksummed
  integrity and finite artifact retention. Keep source, tokens and sensitive
  evidence out of logs/artifacts. Revoke credentials on job completion.

The future ingestion API must verify a single-use per-scan credential, runner
identity, server-side tenant/repository binding, immutable commit, GitHub run
and attempt IDs, payload/artifact size and schema, permitted engines, actual
engine status, findings and sanitized evidence. It must reject replayed or
conflicting submissions, persist idempotently, enforce tenant isolation and
never let a runner set scan success/status or report against another tenant.
Unauthenticated or customer-chosen webhook payloads are not acceptable.

Do not add a workflow that reports a successful SecureWise scan until this
contract exists and has cross-tenant, replay, commit-integrity, credential
redaction and static-only execution tests. No real GitHub Actions run,
customer workflow permission, or result ingestion has been verified.
