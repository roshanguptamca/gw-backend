# Smart Scan Limitations

SecureWise smart scan is intentionally conservative.

## Current limitations

- Runtime discovery is heuristic-based.
- Multi-service repositories are supported conservatively, not with full compose orchestration.
- Some stacks still require manual hints when the repository is unusual.
- DAST is baseline/passive when ZAP cannot be run.
- Playwright and AI-assisted test planning are not full production-grade implementations yet.

## Honest behavior

When SecureWise cannot safely start an app, it should:

- keep static scans running
- mark DAST as skipped
- explain why
- preserve logs
- avoid pretending success

