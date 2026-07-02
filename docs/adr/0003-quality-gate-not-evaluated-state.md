# 0003. Quality gate must distinguish "not evaluated" from "passed"

Status: Accepted
Date: 2026-07-02
Deciders: SecureWise backend maintainers

## Context

`_evaluate_quality_gate()` originally returned `True` unconditionally
whenever a scan had no attached `SecureWiseScanPolicy` — meaning any scan
run without a policy displayed a green "✅ Quality gate: PASSED" badge in
the UI. This is actively misleading: "no gate was configured" and "the
gate was configured and the code met the bar" are completely different
facts, and conflating them gives users false confidence that their code
cleared a security bar that was never actually checked.

This was caught by a user directly asking "how did you decide to pass?"
after seeing a PASSED badge on a scan that had no policy attached at all.

## Decision

`_evaluate_quality_gate()` returns one of three states, not a boolean:

- `True` — a policy was attached and evaluated, and the findings met its
  thresholds.
- `False` — a policy was attached and evaluated, and the findings violated
  it (respecting `allow_accepted_risks`/`allow_false_positives`/
  `fail_on_new_findings_only` exemptions).
- `None` — no policy was attached; the gate was never evaluated at all.

The frontend renders three distinct states accordingly: a green "Passed"
badge, a red "Failed" badge, or a neutral informational banner explaining
that no quality policy is attached to this scan (with a link to attach
one), rather than a false pass/fail badge.

Additionally, evaluation was changed to run against the live, deduplicated
`SecureWiseFinding` rows for the scan (via `for_scan_q`, respecting policy
exemption flags) rather than the raw in-memory list of findings produced
during the scan run — so the gate decision reflects what's actually
tracked/visible to the user afterward, not a snapshot that could disagree
with the persisted findings.

## Alternatives Considered

- **Default to `False` (fail) when no policy is attached** — rejected:
  equally misleading in the other direction (implies "your code failed a
  security check" when no check was configured at all), and would likely
  train users to just always attach a permissive policy to make the red
  badge go away, defeating the purpose.
- **Auto-attach the org's default policy whenever none is explicitly
  chosen, and never allow policy-free scans** — rejected as a full fix by
  itself: still needed during any transition period, and orgs should be
  able to explicitly run policy-free exploratory scans without being
  forced into gate semantics. Auto-attaching a default policy (which
  SecureWise does support via `SecureWiseScanPolicy.is_default`) is a
  complementary decision, not a substitute for making "not evaluated" a
  distinguishable state.

## Consequences

- Removes a real trust-eroding bug: users no longer see false "PASSED"
  claims.
- Any code (frontend or backend, including future report generation)
  that consumes the quality gate result must explicitly handle three
  states, not two — `null`/`None` handling has to be intentional
  everywhere this value flows, including compliance reports.
- Establishes the precedent (see `is_default` scan policy support added
  in the same work) that organizations should generally have a default
  policy so "no policy attached" becomes the exception rather than the
  common case in practice — but the tri-state semantics remain correct
  either way.

## References

- `apps/securewise/services/scanner.py` (`_evaluate_quality_gate`)
- `apps/securewise/models.py` (`SecureWiseScanPolicy.is_default`)
