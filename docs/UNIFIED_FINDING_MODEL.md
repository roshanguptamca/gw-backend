# Unified Finding Model — Design

## Current state (already real, `apps/securewise/models.py:537-620`, `SecureWiseFinding`)

The existing model already covers most of what a unified finding needs:

`scan`, `first_seen_scan`, `last_seen_at`, `occurrence_count`, `project`, `organization`, `title`,
`description`, `file_path`, `line_number`, `endpoint`, `cwe_id`, `owasp_category`, `scanner_type`,
`severity`, `confidence`, `status`, `risk`, `impact`, `recommendation`, `bad_code_example`,
`fixed_code_example`, `code_snippet`, `ticket_url`/`ticket_created_at`, `pr_url`/`pr_created_at`, `evidence`
(JSON), `fingerprint`, `ai_fix_suggestion`, `reviewed_by`/`reviewed_at`/`review_note`, timestamps.

This is a genuinely well-designed schema already — the additions below are strictly additive (new nullable
fields via a normal migration), not a redesign.

## Fields to add

| Field | Type | Purpose |
|---|---|---|
| `scanner_source` | `CharField` (e.g. `semgrep`, `trivy`, `gitleaks`, `zap`, `playwright`, `ai_pentest`, `manual`) | Distinguish *which tool* produced this finding, separate from `scanner_type` (which is the *category*: sast/sca/secrets/iac/container/dast/api). Needed because multiple tools can produce the same category of finding (e.g., both semgrep and an AI pentest scenario can produce an "sast"-adjacent auth finding). |
| `mode` | `CharField` (`real_tool` \| `fallback_heuristic` \| `passive_only` \| `ai_generated`) | Surfaces scan honesty per finding — mirrors the same field added to `SecureWiseScanEngineResult` in `FULL_SCAN_ORCHESTRATOR.md`, but at the finding level so an individual finding's trustworthiness is visible even if other engines in the same scan ran in `real_tool` mode. |
| `exploitability` | `CharField` (`theoretical` \| `confirmed` \| `actively_exploited_in_scan`) | Distinguishes a static-analysis guess from a finding confirmed by runtime/pentest execution — critical for correlation (see `FINDING_CORRELATION_ENGINE.md`). |
| `cvss` | `FloatField`, nullable | Numeric CVSS score, primarily populated for SCA (dependency) findings where a CVE/CVSS score is available from the vulnerability database (Trivy already reports this in its JSON — currently unused/discarded). |
| `affected_component` | `CharField` | e.g. package name + version (`django==3.2.1`) for SCA, or route/controller name for SAST/DAST. |
| `root_cause` | `TextField` | Distinct from `risk`/`impact` — a short, structured technical explanation of *why* this occurs (populated by `AIRecommendationEngine`). |
| `business_impact` | `TextField` | Plain-English, non-technical impact statement — distinct from the more technical `impact` field, intended for executive report sections. |
| `references` | `JSONField(default=list)` | List of URLs (CWE page, OWASP page, vendor advisory) — currently only implicitly present in `recommendation` text; making this structured supports clickable reference lists in the UI/PDF. |
| `correlation_group` | `CharField`, blank, db_index | Groups multiple findings (e.g., SAST + DAST + SCA) that represent the same underlying vulnerability — set by `FindingCorrelationEngine`. |
| `retest_status` | `CharField` (`not_retested` \| `retest_scheduled` \| `retest_passed` \| `retest_failed`) | Tracks whether a fix has been verified by re-running the originating scenario (especially relevant for Playwright/pentest-sourced findings — see `PLAYWRIGHT_ENGINE_DESIGN.md` "regression testing after fix"). |
| `request` / `response` | `JSONField(default=dict)`, blank | Structured HTTP request/response capture for DAST/API/pentest findings — currently only loosely present inside the generic `evidence` JSON; promoting these to first-class fields makes UI rendering (syntax-highlighted request/response panels) simpler and more consistent than parsing arbitrary `evidence` shapes. |

## Fields explicitly NOT duplicated (already covered, just documented here for completeness)

- `evidence` (JSON) remains the general-purpose bucket for anything not covered by the new structured fields
  above (e.g., ZAP raw alert IDs, Playwright trace URLs, screenshot URLs).
- `ai_fix_suggestion` remains as-is; note its current docstring says `"TODO: integrate LLM"` even though
  `services/ai_recommendation.py` already does integrate an LLM — this is a **stale comment**, flagged as a
  Step 17 small fix (see `IMPLEMENTATION_ROADMAP.md` Phase 1 / small fixes list).

## Full target shape (for reference, combining existing + new)

```
scanner_source, scanner_type, title, description, severity, confidence, exploitability,
file_path, line_number, endpoint, request, response, evidence, cwe_id, owasp_category, cvss,
affected_component, root_cause, business_impact, recommendation, bad_code_example,
fixed_code_example, references, status, fingerprint, correlation_group, retest_status, mode
```
(plus existing bookkeeping fields: `scan`, `first_seen_scan`, `last_seen_at`, `occurrence_count`, `project`,
`organization`, `ticket_url`, `pr_url`, `reviewed_by`, timestamps.)

## Migration approach

Single additive migration (`AddField` for each of the ~11 new fields above, all nullable/blank with sane
defaults) — zero risk to existing data, no changes needed to existing serializers beyond adding the new
fields to `SecureWiseFindingSerializer`'s field list (existing pattern already handles JSON fields like
`evidence` and computed properties like `ai_fix_suggestion_parsed`, so this follows the same convention).

## Backward compatibility

All existing scanners (`sast.py`, `sca.py`, `secrets.py`, `iac.py`, `container.py`, `api.py`) continue to
populate only the fields they already know about; new fields default to blank/`not_retested`/`theoretical`
until specifically populated by the new engines (ZAP, Playwright, AI pentest planner) or by
`FindingCorrelationEngine` — no scanner needs to change to keep working.
