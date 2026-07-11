# Smart Scan Current State

This document describes the current SecureWise implementation as it exists in this branch.
It is intentionally honest: what works, what is partial, and what still fails closed.

## What currently works

- Repository validation for local paths and attached repositories.
- Repository cloning into a temporary workspace.
- Application discovery for Python, Node, PHP, Ruby, Java, and Go stacks.
- Runtime auto-start for repo-backed scans when SecureWise can infer a safe plan.
- DAST against a discovered local runtime URL when the app can be started.
- Static scans for SAST, SCA, secrets, IaC, container, and API where inputs exist.
- Scan progress reporting, per-engine results, and retry for `completed_partial`.
- Runtime failure diagnostics surfaced in API metadata as sanitized excerpts.
- The SecureWise scan detail page renders `diagnostics.log_excerpt`, failed stage, retryability,
  and partial-coverage banners instead of a generic Docker error.

## What is partial

- DAST is still a baseline/passive implementation when ZAP cannot run.
- Multi-service orchestration is handled conservatively, not as a full compose runner.
- Playwright and AI security journey planning are documented in the roadmap, not fully implemented here.
- Frontend scan pages must render the new diagnostics fields to show logs inline.

## What is fixed in this branch

- Repo-backed DAST scans no longer require a manually entered target URL when SecureWise can start the app.
- Packaged Django repos under `src/.../settings.py` are detected as runnable web apps.
- Docker/runtime failures are no longer collapsed into a generic skip; the scan metadata carries a log excerpt.
- `completed_partial` is retryable and exposed through scan serializers.
- The frontend can now retry failed stages directly from the scan detail page when the API says the
  scan is retryable.

## Remaining honest failure modes

- If the repo cannot be started safely, DAST is skipped and the scan continues with static engines.
- If Docker is unavailable, SecureWise reports that explicitly.
- If the runtime cannot be discovered, the scan explains why instead of pretending DAST ran.
