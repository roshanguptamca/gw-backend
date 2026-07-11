# Smart Scan Architecture

SecureWise smart scan follows this high-level flow:

1. Validate repository input.
2. Clone the repository into an isolated temporary workspace.
3. Discover language, framework, package manager, runtime entrypoint, ports, and services.
4. Resolve engines for the scan type.
5. Build or reuse a runtime strategy.
6. Start the application in isolation when safe.
7. Discover a reachable localhost URL.
8. Run applicable security scanners.
9. Normalize findings and persist scan results.
10. Surface diagnostics, logs, and retryability to the API and CLI.

## Main components

- `apps/securewise/discovery/`
  - Static application discovery and runtime planning.
- `apps/securewise/runtime/`
  - Docker/image/runtime lifecycle management.
- `apps/securewise/scanners/`
  - SAST, SCA, secrets, IaC, container, API, and DAST engines.
- `apps/securewise/services/scanner.py`
  - Scan orchestration for repository-backed scans.
- `apps/securewise/services/local_scan.py`
  - Standalone CLI scanning and report generation.

## Runtime strategy order

1. Existing `docker-compose` or `compose.yaml`.
2. Existing `Dockerfile`.
3. Documented start command from README or project files.
4. Generated temporary Dockerfile.
5. Static-only scan when runtime cannot be created safely.

## Security controls

- Temporary workspace cleanup after success, failure, or cancellation.
- No Docker socket mount into scanned containers.
- No privileged containers.
- Resource limits applied to runtime containers.
- Logs are redacted before being surfaced.

