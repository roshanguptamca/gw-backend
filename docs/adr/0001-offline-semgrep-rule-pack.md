# 0001. Bundle an offline curated Semgrep rule pack instead of `--config=auto`

Status: Accepted
Date: 2026-07-02
Deciders: SecureWise backend maintainers

## Context

SecureWise's SAST engine (`apps/securewise/scanners/sast.py`) shells out to
Semgrep OSS when it's available on the host, falling back to a lightweight
regex-based scanner otherwise. The default Semgrep invocation pattern most
teams reach for is `semgrep --config=auto`, which downloads a curated rule
set from Semgrep's cloud registry at scan time.

In practice this had two problems for a production scanning platform:

- **Network dependency**: `--config=auto` requires live access to
  Semgrep's registry. Any registry hiccup, corporate proxy, or offline
  environment breaks SAST scanning entirely — unacceptable for a security
  tool whose core value proposition is "it always runs."
- **Latency and non-determinism**: a real end-to-end test against the
  `gw-backend` repo itself took ~140 seconds with `--config=auto`, most of
  it spent fetching rules over the network, and the exact rule set (and
  therefore findings) could silently change between scans as Semgrep's
  registry content changed upstream — bad for reproducibility and for the
  "full scan must not complete instantly" requirement, but for the wrong
  reason (slow network, not real work).

## Decision

Ship a small, hand-curated, version-controlled Semgrep rule pack at
`apps/securewise/scanners/rules/semgrep/{python,javascript,java,go}.yml`,
covering the highest-signal patterns from the recommendation-engine spec
(SQL injection, command injection, unsafe deserialization/pickle/yaml,
weak crypto, XXE, prototype pollution, insecure JWT usage, missing
timeouts, weak TLS, etc.). `sast.py` uses this bundle by default. Teams
that want the full upstream registry can opt in via the
`SECUREWISE_SEMGREP_CONFIG` environment variable (e.g. set it to `auto`).

Each rule was authored and validated with `semgrep --validate`, and rule
correctness was spot-checked with `focus-metavariable`/`metavariable-regex`
against known-vulnerable and known-safe snippets.

## Alternatives Considered

- **Keep `--config=auto` as the only mode** — rejected: makes SAST results
  non-deterministic and network-dependent, both unacceptable for a
  security gate that CI pipelines depend on.
- **Vendor the entire Semgrep public registry into the repo** — rejected:
  huge maintenance burden, most rules irrelevant to our stack coverage,
  and still requires periodic re-vendoring to stay current.
- **Write our own AST-based SAST engine instead of using Semgrep** —
  rejected for now: Semgrep's pattern-matching engine is mature and
  battle-tested; reinventing it is a multi-month effort better spent
  elsewhere. Revisit if we build a genuinely differentiated SAST approach
  (see `docs/architecture/AI_ARCHITECTURE.md` for how AI-assisted rule
  synthesis could eventually replace/augment this).

## Consequences

- Runtime dropped from ~140s to ~3–78s depending on target size, and SAST
  now works fully offline.
- Findings are now deterministic and reproducible run-to-run, which is a
  prerequisite for reliable dedup (see ADR-0002) and quality gates.
- **New maintenance burden**: the bundled rule pack must be manually kept
  in sync with emerging vulnerability patterns; it will never have the
  breadth of Semgrep's full community registry. This is an explicit
  breadth-vs-reliability trade-off that should be revisited once
  SecureWise has a plugin/rule-marketplace story (see
  `docs/architecture/PLUGIN_ARCHITECTURE.md`).
- Coverage gaps in the bundled pack are a known, tracked limitation — see
  `docs/architecture/GAP_ANALYSIS.md`.

## References

- `apps/securewise/scanners/sast.py`
- `apps/securewise/scanners/rules/semgrep/`
- `docs/architecture/GAP_ANALYSIS.md`
