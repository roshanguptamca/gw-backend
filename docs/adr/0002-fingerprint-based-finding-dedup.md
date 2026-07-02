# 0002. Fingerprint-based finding deduplication across scans

Status: Accepted
Date: 2026-07-02
Deciders: SecureWise backend maintainers

## Context

Every scan engine originally created brand-new `SecureWiseFinding` rows on
every run, even when re-scanning unchanged code. A user who ran the same
scan twice in a row would see the same issue duplicated in the Findings
page, with no way to tell "this is the same SQL injection I saw
yesterday" from "this is a new one introduced by today's commit." This
also made "mark as fixed" / "accept risk" meaningless across rescans,
since the next scan would just recreate a fresh, unreviewed row for the
same underlying issue.

All scanner engines (`sast.py`, `secrets.py`, `sca.py`, `iac.py`, `api.py`,
`dast.py`) already computed a `fingerprint` field per finding, derived from
rule-id + file/line or equivalent stable content — not from the scan ID.
This meant fingerprints were already content-stable across independent
scan runs of the same code, which made real deduplication possible without
changing every scanner.

## Decision

Deduplicate findings by `(project, fingerprint)`:

- On persist, if a finding with the same `(project, fingerprint)` already
  exists, update it in place (bump `occurrence_count`, `last_seen_at`,
  advance `scan` to point at the most recent detecting scan) instead of
  inserting a new row.
- `first_seen_scan` is set once at creation and never changes — it answers
  "when did we first see this?" for "new vs. recurring" reporting and for
  quality-gate policies with `fail_on_new_findings_only`.
- `scan` means "most recently detected in this scan" (mutable); a new
  static helper `SecureWiseFinding.for_scan_q(scan_id)` returns
  `Q(scan_id=scan_id) | Q(first_seen_scan_id=scan_id)` so "findings for
  this scan run" correctly includes both newly-discovered issues and
  still-present pre-existing ones, without duplicating rows.
- If a completed engine no longer detects a previously-open finding it
  used to report, that finding is auto-resolved (status → `fixed`,
  reasoning: the engine actually ran and didn't find it, so it's most
  likely genuinely fixed — as opposed to a skipped engine, whose findings
  are left untouched since "we didn't check" is not "it's fixed").
- If an auto-resolved (or manually marked "fixed") finding is re-detected
  by a later scan, it's automatically reopened.

## Alternatives Considered

- **Dedup by title + severity string match** — rejected: too fragile,
  false-collapses genuinely distinct findings with similar titles and
  false-splits the same finding if wording changes slightly between
  scanner versions.
- **No dedup, but hide duplicates in the UI only** — rejected: doesn't
  solve the "mark as fixed persists across rescans" problem, and still
  pollutes the database/API with unbounded duplicate rows over time.
- **Dedup scoped globally instead of per-project** — rejected: two
  unrelated projects could coincidentally produce the same fingerprint
  (e.g. same vulnerable dependency), and collapsing across projects would
  break per-project findings ownership/RBAC.

## Consequences

- Rescanning unchanged code no longer creates duplicate findings — this
  was the most visible pre-launch bug reported during manual testing.
- "Mark as fixed" / "accept risk" / "false positive" now persist
  meaningfully across rescans instead of being silently reset every run.
- Quality gates can now distinguish new vs. recurring findings
  (`fail_on_new_findings_only`).
- **New coupling**: dedup correctness depends entirely on every scanner
  engine computing a *content-stable* fingerprint (not scan-ID-derived).
  Any future scanner/plugin that gets this wrong will silently either
  over-merge (losing genuinely distinct findings) or never-merge (falling
  back to pre-ADR duplicate behavior) — see `PLUGIN_ARCHITECTURE.md` for
  the fingerprinting contract every plugin must honor.
- Dedup is per-project, not per-organization or global — acceptable today,
  revisit if cross-project correlation (e.g. "this vulnerable dependency
  appears in 12 of your projects") becomes a product requirement (tracked
  in `GAP_ANALYSIS.md` under Finding Correlation Engine).

## References

- `apps/securewise/services/scanner.py` (`_persist_findings`,
  `_auto_resolve_findings`)
- `apps/securewise/models.py` (`SecureWiseFinding.for_scan_q`)
- Migration `0003_securewisefinding_first_seen_scan_and_more`
- `docs/architecture/GAP_ANALYSIS.md` (Finding Correlation Engine section)
