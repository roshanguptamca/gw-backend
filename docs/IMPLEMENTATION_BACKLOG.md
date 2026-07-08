# Implementation Backlog — SecureWise Evolution

Actionable backlog items, grouped by roadmap phase (`IMPLEMENTATION_ROADMAP.md`). IDs are stable references
for tracking (e.g., in issues/PRs).

---

## Phase 1 — Honesty fixes

**SW-101** — Add `mode` field to `SecureWiseScanEngineResult` and `SecureWiseFinding`
- Description: New `CharField` with choices `real_tool|fallback_heuristic|passive_only|ai_generated|skipped`, populated by each scanner based on whether it used a real external tool or its fallback path.
- Priority: P0
- Dependencies: none
- Acceptance criteria: every engine result and finding has a non-null `mode`; frontend engine row and finding row display a badge reflecting it.
- Estimated effort: 3 days
- Affected files/modules: `apps/securewise/models.py`, `apps/securewise/scanners/*.py`, migration, `serializers.py`, frontend `ScanDetailPage.tsx`, `FindingsPage.tsx`

**SW-102** — Install `trivy` and `gitleaks` binaries in the deployment Dockerfile
- Description: Currently only `semgrep` is a Python dependency; `trivy`/`gitleaks` are not installed by the Dockerfile per the audit, meaning production likely runs in fallback mode silently.
- Priority: P0
- Dependencies: none
- Acceptance criteria: `shutil.which("trivy")` and `shutil.which("gitleaks")` return non-empty in the deployed container; a full scan in production shows `mode=real_tool` for SCA/secrets/IaC.
- Estimated effort: 2 days
- Affected files/modules: `Dockerfile`

**SW-103** — Introduce `completed_partial` scan status
- Description: A scan cannot report `completed` if every applicable engine ran in fallback/skipped mode; introduce a distinct status with a clear UI banner.
- Priority: P0
- Dependencies: SW-101
- Acceptance criteria: a scan where all engines ran in fallback mode shows status `completed_partial` with explanatory text, not `completed`.
- Estimated effort: 2 days
- Affected files/modules: `models.py` (`SecureWiseScan.status` choices), `services/scanner.py`, frontend `ScanDetailPage.tsx`

**SW-104** — Fix stale `ai_fix_suggestion` docstring
- Description: Remove "TODO: integrate LLM" comment since `ai_recommendation.py` already integrates one.
- Priority: P2
- Dependencies: none
- Acceptance criteria: docstring accurately reflects current behavior.
- Estimated effort: 15 minutes
- Affected files/modules: `apps/securewise/models.py`

**SW-105** — Add explicit `skip_reason` text to every skipped engine
- Description: Container scan (no docker_image), DAST (no target_url), API scan (no spec found) should all populate a human-readable reason.
- Priority: P1
- Dependencies: none
- Acceptance criteria: every `SecureWiseScanEngineResult` with `status=skipped` has a non-blank reason string surfaced in the UI.
- Estimated effort: 2 days
- Affected files/modules: `scanners/*.py`, `services/scanner.py`, frontend `ScanDetailPage.tsx`

---

## Phase 2 — Code Understanding Engine

**SW-201** — Build deterministic stack detector
- Description: File-signature-based detection for Python/Django/FastAPI, Node/React/Next/Express, Java/Spring, Go, PHP/Laravel, Ruby/Rails per `CODE_UNDERSTANDING_ENGINE.md`.
- Priority: P0
- Dependencies: none
- Acceptance criteria: given a sample repo of each supported stack, detector correctly identifies language/framework/package manager with `confidence=high`.
- Estimated effort: 8 days
- Affected files/modules: new `apps/securewise/services/code_understanding.py`, new `SecureWiseApplicationRunPlan` model + migration

**SW-202** — AI-assisted fallback detection
- Description: For unrecognized/ambiguous stacks, feed directory listing + key files to the existing AI provider abstraction for structured JSON detection.
- Priority: P1
- Dependencies: SW-201
- Acceptance criteria: an intentionally obscure/monorepo test fixture produces a usable (if lower-confidence) run plan instead of failing outright.
- Estimated effort: 4 days
- Affected files/modules: `services/code_understanding.py`, reuses `services/ai_recommendation.py::get_ai_provider()`

**SW-203** — Scan plan preview UI
- Description: Frontend surfaces the detected `ApplicationRunPlan` before a full scan proceeds, with an explicit confirm action.
- Priority: P0
- Dependencies: SW-201
- Acceptance criteria: user sees detected language/framework/build/start commands and must click "Confirm & Run" before dockerization/runtime stages begin.
- Estimated effort: 5 days
- Affected files/modules: `securewise-frontend/src/pages/scans/ScansPage.tsx`, new API endpoint `GET /scans/{id}/run-plan/`

---

## Phase 3 — Dockerization + Runtime Environment

**SW-301** — DockerizationEngine: validate + build existing Dockerfile
- Priority: P0 | Dependencies: SW-201 | Effort: 6 days
- Acceptance criteria: given a repo with a valid Dockerfile, engine builds an image, tags it with scan_id, and passes it to the existing Trivy image scanner.
- Affected files/modules: new `apps/securewise/services/dockerization.py`

**SW-302** — DockerizationEngine: generate temporary Dockerfile from template
- Priority: P1 | Dependencies: SW-301 | Effort: 8 days
- Acceptance criteria: for each of the 6 supported stack templates, a generated Dockerfile builds successfully for a representative sample app.
- Affected files/modules: `services/dockerization.py`, new template files

**SW-303** — RuntimeEnvironmentManager: isolated start/stop lifecycle
- Priority: P0 | Dependencies: SW-301 | Effort: 10 days
- Acceptance criteria: app container starts on an isolated per-scan network, health check passes within timeout, teardown removes container+network+tempdir unconditionally (including on error paths, verified by fault-injection tests).
- Affected files/modules: new `apps/securewise/services/runtime_environment.py`, new `SecureWiseRuntimeEnvironment` model + migration

**SW-304** — Replace thread-based scan execution with Celery + Redis
- Priority: P0 | Dependencies: none (can start in parallel with SW-301-303) | Effort: 10 days
- Acceptance criteria: scan execution survives a worker process restart mid-scan (job resumes/retries rather than being silently lost); existing `/scans/{id}/progress/` API contract unchanged.
- Affected files/modules: `apps/securewise/views.py`, new Celery app config, `requirements.txt`, deployment config (Redis service)

**SW-305** — Stale-environment reaper management command
- Priority: P1 | Dependencies: SW-303 | Effort: 3 days
- Acceptance criteria: a management command run on a schedule removes any scan container/network/tempdir whose scan is no longer active, regardless of how it was orphaned.
- Affected files/modules: new `apps/securewise/management/commands/cleanup_stale_scan_environments.py`

---

## Phase 4 — ZAP DAST Engine

**SW-401** — ZAP automation YAML generator + container runner
- Priority: P0 | Dependencies: SW-303 | Effort: 8 days
- Acceptance criteria: given a healthy runtime environment, ZAP runs passive scan + spider against it and produces a JSON report.
- Affected files/modules: rewrite `apps/securewise/scanners/dast.py` (or new `zap_dast.py` + orchestrator registration update)

**SW-402** — Normalize ZAP alerts into `SecureWiseFinding`
- Priority: P0 | Dependencies: SW-401 | Effort: 4 days
- Acceptance criteria: every ZAP alert produces one finding with correctly mapped severity/CWE/OWASP/evidence fields; no raw HTML report is used as the deliverable.
- Affected files/modules: `scanners/zap_dast.py`, `scanners/cwe_mapping.py` (extend)

**SW-403** — Safe active-scan policy + opt-in flag
- Priority: P1 | Dependencies: SW-401 | Effort: 4 days
- Acceptance criteria: active scan never runs unless `SecureWiseScan.allow_active_scan=True`; when enabled, uses the custom safe policy excluding destructive rules.
- Affected files/modules: `scanners/zap_policies/securewise-safe-active-policy.policy`, `models.py`

---

## Phase 5 — Playwright Engine

**SW-501** — Structured step interpreter (whitelisted vocabulary)
- Priority: P0 | Dependencies: SW-303 | Effort: 8 days
- Acceptance criteria: interpreter executes `goto/fill/click/expect_status/expect_text/expect_url/extract_cookie/assert_response_contains` steps against a sample app reliably.
- Affected files/modules: new `apps/securewise/services/playwright_engine.py`, new `SecureWisePlaywrightRun` model + migration

**SW-502** — Evidence capture (screenshots/trace) via shared Cloudinary core
- Priority: P0 | Dependencies: SW-501 | Effort: 4 days
- Acceptance criteria: each step captures a screenshot uploaded via `apps.common.cloudinary_service`; full trace zip stored and linked.
- Affected files/modules: new `apps/securewise/services/evidence_storage.py` (mirrors `apps/speaking_buddy/services/cloudinary_service.py` pattern)

**SW-503** — AI-generated structured scenario scripts
- Priority: P1 | Dependencies: SW-501 | Effort: 6 days
- Acceptance criteria: given route/form data, AI produces a structured step list (not raw executable code) that the interpreter can run.
- Affected files/modules: `services/playwright_engine.py`

---

## Phase 6 — AI Pen-Test Planner

**SW-601** — `PenTestPlan` schema + generation prompt
- Priority: P0 | Dependencies: none (can start immediately, no runtime dependency) | Effort: 6 days
- Acceptance criteria: given code-understanding artifacts, AI produces a list of `PenTestPlan` JSON objects matching the schema in `AI_PENTEST_PLANNER.md`.
- Affected files/modules: new `apps/securewise/services/ai_pentest_planner.py`, new `SecureWisePenTestPlan` model + migration

**SW-602** — Programmatic safety validator
- Priority: P0 | Dependencies: SW-601 | Effort: 4 days
- Acceptance criteria: a test suite of intentionally unsafe LLM outputs (destructive flags, credential-attack keywords, external-domain targets) are all rejected; rejections are logged and surfaced, not silently dropped.
- Affected files/modules: `services/ai_pentest_planner.py`

**SW-603** — Executor wiring (Playwright/HTTP-client/ZAP dispatch)
- Priority: P0 | Dependencies: SW-501, SW-401, SW-602 | Effort: 6 days
- Acceptance criteria: an approved `PenTestPlan` is dispatched to the correct engine based on `tools_required` and produces a finding when `unsafe_behavior` is confirmed.
- Affected files/modules: `services/ai_pentest_planner.py`, `services/full_scan_orchestrator.py`

---

## Phase 7 — Finding Correlation

**SW-701** — Generalize `FindingCorrelationEngine`
- Priority: P0 | Dependencies: SW-402, SW-603 | Effort: 6 days
- Acceptance criteria: the SQLi example scenario (SAST theoretical + DAST confirmed + SCA vulnerable driver) produces one `correlation_group` with escalated combined severity.
- Affected files/modules: new `apps/securewise/services/correlation_engine.py`, `UNIFIED_FINDING_MODEL.md` fields migration

**SW-702** — Correlated-incident UI card
- Priority: P1 | Dependencies: SW-701 | Effort: 5 days
- Acceptance criteria: findings page groups correlated findings into one primary incident card with nested supporting findings.
- Affected files/modules: `securewise-frontend/src/pages/findings/FindingsPage.tsx`

---

## Phase 8 — AI Remediation + PR Generation

**SW-801** — Extend AI recommendation response schema
- Priority: P0 | Dependencies: none | Effort: 5 days
- Acceptance criteria: `/findings/{id}/ai-suggestion/` returns the full extended schema (exploit scenario, verification tests, PR patch, learning note) while remaining backward compatible with existing frontend fields.
- Affected files/modules: `services/ai_recommendation.py`, `views.py`, `FindingDetailPage.tsx`

**SW-802** — Correlated-incident single explanation call
- Priority: P1 | Dependencies: SW-701, SW-801 | Effort: 3 days
- Acceptance criteria: a correlation group triggers exactly one AI call producing a unified narrative, not N per-finding calls.
- Affected files/modules: `services/ai_recommendation.py`

**SW-803** — Advisory PR patch generation
- Priority: P2 | Dependencies: SW-801 | Effort: 5 days
- Acceptance criteria: for narrow single-line findings, a unified diff is generated and shown for manual review; never auto-applied/auto-committed.
- Affected files/modules: `services/ai_recommendation.py`, `views.py` (existing `create PR` action, `830-899`)

---

## Phase 9 — Compliance & Executive Reporting

**SW-901** — Runtime evidence sections in reports
- Priority: P1 | Dependencies: SW-502, SW-402 | Effort: 6 days
- Acceptance criteria: PDF/HTML reports include screenshots/ZAP evidence for runtime-sourced findings.
- Affected files/modules: `services/report.py`, `services/report_render.py`, templates

**SW-902** — Compliance framework cross-references
- Priority: P2 | Dependencies: none | Effort: 8 days
- Acceptance criteria: report can show which SOC2/ISO27001 controls are impacted by open findings (mapping table).
- Affected files/modules: new mapping data file, `services/report.py`

---

## Phase 10 — Enterprise Plugin SDK

**SW-1001** — Define scanner plugin interface contract
- Priority: P2 | Dependencies: all prior phases stabilized | Effort: 10 days
- Acceptance criteria: a third-party scanner implementing the documented interface can register findings through the same pipeline as built-in scanners, with `mode` correctly reported.
- Affected files/modules: new `apps/securewise/scanners/base.py` interface refinement, SDK docs

---

## Backlog summary by priority

- **P0 (must-have for the vision to be credible):** SW-101, SW-102, SW-103, SW-201, SW-203, SW-301, SW-303,
  SW-304, SW-401, SW-402, SW-501, SW-502, SW-601, SW-602, SW-603, SW-701, SW-801
- **P1 (important, can slip slightly):** SW-105, SW-202, SW-302, SW-305, SW-403, SW-503, SW-702, SW-802,
  SW-901
- **P2 (nice-to-have / cleanup):** SW-104, SW-803, SW-902, SW-1001
