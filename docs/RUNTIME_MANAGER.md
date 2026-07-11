# Runtime Manager

The runtime manager owns the temporary execution environment for repo-backed scans.

## Responsibilities

- Resolve a safe Dockerfile or use an existing one.
- Build a disposable image.
- Start the application container.
- Wait for readiness.
- Return a localhost URL for DAST.
- Stop and remove all temporary resources.

## Failure handling

Runtime failures must return a structured reason instead of crashing the scan.
Examples:

- Docker not installed
- Docker daemon unreachable
- build failed
- container did not become healthy
- app did not expose a reachable HTTP endpoint

## Log handling

Runtime logs are sanitized before exposure. When startup fails, SecureWise stores a short
excerpt in scan metadata so the user can see what failed.

## Cleanup

Cleanup should happen after:

- success
- failure
- timeout
- cancellation

