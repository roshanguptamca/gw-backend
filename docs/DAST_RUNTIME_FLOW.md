# DAST Runtime Flow

DAST targets a running application, not a source tree.

## Repository-only flow

1. Clone repository.
2. Discover app type and runtime strategy.
3. Start the app in an isolated local environment when possible.
4. Probe a reachable localhost URL.
5. Run DAST against that URL.

## Existing deployed URL flow

If the user provides a staging or deployed URL, SecureWise should use it only after
authorization is established.

## Skip behavior

If runtime startup is not possible:

- DAST is skipped
- static scanners still run
- the scan can finish as `completed_with_warnings`
- the reason and logs are preserved

