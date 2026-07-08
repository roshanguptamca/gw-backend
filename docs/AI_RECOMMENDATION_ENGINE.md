# AI Recommendation Engine — Design

## Current state (real, provider-dependent)

`apps/securewise/services/ai_recommendation.py:74-110` already calls `get_ai_provider()` and expects
structured JSON output for a single finding. `views.py:791-828` exposes this as
`POST /findings/{id}/ai-suggestion/`. The frontend already renders this well
(`FindingDetailPage.tsx:520-685`), including an honest "AI recommendations are not configured in this
environment" fallback message when no provider key is set.

There is also a **second, separate remediation system**: each scanner has its own template-based
recommendation text (`scanners/sast.py:172-197`, `scanners/iac.py:102-119`). This duplication is flagged as
technical debt in `CURRENT_SECUREWISE_REVIEW.md` §8 and should be resolved as part of this design (not a new
problem to solve from scratch — a consolidation of what already exists).

## Target unified behavior

For every finding — regardless of which scanner produced it — the engine should be able to produce all of
the following, extending the existing single "fix suggestion" response into a richer structured object:

```json
{
  "plain_english_explanation": "string",
  "technical_root_cause": "string",
  "exploit_scenario": "string",
  "secure_fix_summary": "string",
  "framework_specific_fix": "string",
  "bad_code_example": "string",
  "fixed_code_example": "string",
  "verification_tests": ["string", "..."],
  "suggested_pr_patch": "unified diff string, optional",
  "developer_learning_note": "string",
  "confidence": "low | medium | high"
}
```

This is an **additive extension** of the existing `ai_fix_suggestion` flow, not a rewrite: the current
endpoint's response shape gains fields; existing frontend rendering that only used a subset keeps working.

## Two-tier strategy: template baseline + AI enrichment

Rather than fully replacing the scanner-level templates (real, free, always-available) with AI (better
quality, costs tokens, can fail/be unconfigured), use both, tiered:

1. **Template baseline** (existing `sast.py`/`iac.py` style logic) always populates `recommendation`,
   `bad_code_example`, `fixed_code_example` immediately at scan time, for free, with zero external
   dependency — this guarantees every finding has *some* actionable guidance even if AI is not configured.
2. **AI enrichment** (on-demand, existing "Get AI suggestion" button, or automatically fire-and-forget after
   scan completion for the highest-severity findings only, mirroring the fire-and-forget pattern already
   proven in `speaking_buddy` — see `apps/speaking_buddy/views.py`'s background-thread pattern for post-call
   report generation) enriches with the fuller structured object above, replacing/augmenting the template
   text when available.

This directly resolves the "two divergent remediation systems" debt item: the template system becomes the
guaranteed-available Tier 1 fallback, and the AI system becomes the enrichment Tier 2 — both intentionally
coexist rather than one replacing the other.

## Framework-specific fix generation

The AI prompt should be given `affected_component`/`file_path`/detected framework (from
`ApplicationRunPlan.detected_frameworks`, `CODE_UNDERSTANDING_ENGINE.md`) so the "framework_specific_fix" is
concrete (e.g., "Use Django's `django.utils.html.escape()` here" rather than generic "sanitize your input"
advice).

## Suggested PR patch generation (new capability)

For well-understood, narrow fixes (e.g., a single-line SAST finding with a clear bad/fixed code pair), the
engine can additionally attempt to generate a unified diff patch. This is **advisory only** in MVP — never
auto-applied or auto-committed. It surfaces as a "Suggested patch (review before applying)" block, reusing
the existing `pr_url`/`pr_created_at` fields on `SecureWiseFinding` for the *manual* "create PR" action that
already exists (`views.py:830-899`), with the AI-suggested diff as the PR's proposed content rather than an
empty scaffold.

## Correlated-incident explanations

When `FindingCorrelationEngine` groups multiple findings under one `correlation_group`
(`FINDING_CORRELATION_ENGINE.md`), the AI recommendation engine is called once per group (not once per
finding) to produce a single narrative: "This is one critical SQL injection vulnerability, confirmed
exploitable at runtime, caused by unsanitized input in `views.py:142`, made worse by an outdated DB driver
flagged separately by dependency scanning" — rather than three disconnected AI calls producing three
overlapping explanations.

## Cost/reliability controls

- AI calls remain **opt-in per finding** (existing "Get AI suggestion" button) by default; automatic
  enrichment for top findings after a scan should be config-gated per `SecureWiseScanPolicy` (new boolean,
  e.g. `auto_ai_enrich_critical_findings`) so orgs without an AI provider configured, or who want to control
  token spend, aren't surprised by automatic LLM calls.
- Existing honest-failure UX (frontend's "not configured" message) is preserved and extended to the new
  richer fields — if the provider call fails, the response includes a clear `error` reason, never fabricated
  content standing in for a real AI response.
- Cache AI responses per finding fingerprint (existing `fingerprint` field) so re-scans of unchanged findings
  don't re-spend tokens regenerating identical guidance — only regenerate when the finding's underlying
  evidence actually changed, or the user explicitly clicks "regenerate" (already an existing frontend action,
  per the audit: "regenerate/get suggestion" button).

## Where this fixes an existing inaccurate comment

`models.py`'s `ai_fix_suggestion` field currently has the docstring `"AI-generated fix recommendation.
TODO: integrate LLM."` even though the LLM integration already exists and works
(`services/ai_recommendation.py`) — this stale comment should be corrected as part of implementing this
design (tracked as a Step 17 small fix in `IMPLEMENTATION_ROADMAP.md`).
