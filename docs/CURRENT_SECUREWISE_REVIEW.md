# SecureWise — Current State Review

**Reviewed:** 2026-07-08
**Reviewer role:** CTO / Principal Security Engineer / DevSecOps Architect / AI Product Architect (Copilot-assisted audit)
**Scope:** `apps/securewise` (gw-backend) + `securewise-frontend` repo
**Method:** Static code audit with file/line citations. No claims are made without corresponding evidence in the codebase.

---

## 1. Executive summary

SecureWise today is a **real, working MVP security-scanning platform** with genuine multi-tenant data
modeling, RBAC, audit logging, and *conditionally real* scanning (when external tools are present on the
host). It is **not** the "clone → dockerize → run → attack → report" platform described in the vision.
It is closer to **"static analysis SaaS with an honest fallback mode"** than a full DAST/pentest platform.

The single most important fact for planning purposes:

> **SecureWise does not clone-build-run applications today.** There is no dockerization engine, no runtime
> environment manager, and no active DAST/pentest execution. DAST is passive-only (HTTP header/cookie
> checks against a URL the user already has running somewhere). This is the single biggest gap between
> current state and the vision.

---

## 2. What works today (real, evidence-backed)

| Area | Status | Evidence |
|---|---|---|
| Multi-tenant data model (Org/Project/Repo/Scan/Finding/Report/Integration/AuditLog) | **Real** | `apps/securewise/models.py` — 13 models, well-normalized, JSON fields for flexible metadata |
| RBAC / org-scoped access control | **Real** | `apps/securewise/permissions.py:20-86` (`IsSecureWiseMember`, `IsSecureWiseWriteMember`, `IsSecureWiseAdmin`, `IsOrganizationOwnerOrAdmin`); every queryset in `views.py` filters by the user's org memberships |
| Audit logging | **Real** | `SecureWiseAuditLog` model + `_audit()` helper in `views.py:74-87`, called from create/update/scan/finding/report/integration actions |
| SAST via Semgrep | **Real when `semgrep` binary/pip package present** | `scanners/sast.py:89-118` — real `subprocess.run(["semgrep", ...])`; `semgrep==1.168.0` is in `requirements.txt` |
| SCA via Trivy | **Real when `trivy` binary present** | `scanners/sca.py:61-78` — real `subprocess.run(["trivy", "fs", ...])` |
| Secret scanning via Gitleaks | **Real when `gitleaks` binary present** | `scanners/secrets.py:44-80` — real `subprocess.run(["gitleaks", "detect", ...])` |
| IaC scanning via Trivy config | **Real when `trivy` present** | `scanners/iac.py:54-71` |
| Container scanning via Trivy image | **Real when `trivy` present + docker_image supplied**, optional build path | `scanners/container.py:27-106` |
| Fallback scanners (no external tool) | **Real, but heuristic** | Every scanner above has a non-fake, deterministic fallback (regex/lockfile/rule-based), clearly weaker than the real tool but not fabricated data |
| Finding deduplication/fingerprinting | **Real** | `scanners/orchestrator.py:52-158` — fingerprint-based dedupe, DAST↔SAST correlation exists |
| Report generation (JSON/HTML/PDF) | **Real** | `services/report.py:68-285`, `services/report_render.py` (WeasyPrint for PDF), Django templates for HTML |
| AI remediation suggestions | **Real integration, provider-dependent** | `services/ai_recommendation.py:74-110`, `views.py:791-828` (`/findings/{id}/ai-suggestion/`); frontend has an honest "AI recommendations are not configured" fallback message (`FindingDetailPage.tsx:584-590`) |
| Frontend scan progress UX | **Real, polling-based, per-engine** | `securewise-frontend/src/pages/scans/ScanDetailPage.tsx:77-118, 277-330` — polls `/scans/{id}/progress/` every 3s, shows per-engine status/duration/skip-reason |
| Frontend findings/report/AI UX | **Real, richly detailed** | `FindingDetailPage.tsx:364-793` shows CWE, OWASP, evidence, bad/fixed code, AI remediation panel |
| Admin registration | **Real** | `apps/securewise/admin.py:27-130` — all 12 core models registered with list_display/search/filter |

---

## 3. What is fake / mock / stubbed

| Area | Status | Evidence |
|---|---|---|
| **DAST** | **Mock/insufficient — passive only** | `scanners/dast.py:30-78` — just `requests.get(target_url)` and inspects response headers/cookies. No spidering, no active payloads, no ZAP invocation despite ZAP being "detected" in comments (`dast.py:47-52`) |
| **API security scanning** | **Static analysis only, not runtime** | `scanners/api.py:57-99` — parses an OpenAPI/Swagger file for structural issues; never sends a request to a live API |
| **Async job execution** | **MVP-grade, explicitly marked as such** | `views.py:642-643` — `# Run scanner in background thread (MVP — use Celery/RQ in production)` / `# TODO: Replace threading with Celery task for production`; uses raw daemon threads (`views.py:645, 707`), no retry/backoff/dead-letter queue, no persistence across process restarts |
| **Repository cloning/build/execution** | **Does not exist** | No dockerization engine, no build-and-run step anywhere in `apps/securewise`. `ScannerRunner` clones the repo into a tempdir for *static* file analysis only (`services/scanner.py:61-76`) — the application is never started |
| **Playwright / authenticated user-flow testing** | **Does not exist** | No Playwright integration found anywhere in `apps/securewise` |
| **AI-generated pen-test scenarios** | **Does not exist** | No pen-test planning service; AI is only used for post-finding remediation text, not for generating attack scenarios |
| **Demo data seed command** | **Explicitly synthetic** | `management/commands/seed_securewise_demo.py` — creates fabricated org/scan/finding records for demo purposes; correctly not disguised as real scan output |
| **Report "quality gate" / scan status wording** | **Risk of misleading text** | Because DAST/API scanners silently run in passive/static mode, a "Full Scan" can complete and show "completed successfully" even though no real dynamic testing occurred — the UI does show per-engine skip reasons, but there is no explicit "PASSIVE-ONLY / NOT A REAL DAST" label surfaced prominently |

---

## 4. What is incomplete (partially built, needs finishing)

- **Container scanning** requires the caller to supply a `docker_image` name; there's no automatic "build image from this repo" step feeding into it.
- **Correlation engine** exists in a limited form (DAST↔SAST fingerprint matching in the orchestrator) but is not a general-purpose, extensible `FindingCorrelationEngine` — it doesn't correlate SCA (vulnerable dependency) with confirmed runtime exploitability, for example.
- **Recommendation engine** is template-based per scanner (`sast.py:172-197`, `iac.py:102-119`) *in addition to* the AI-based one — there are effectively two separate remediation systems that should be unified.
- **RBAC in frontend UI** — backend enforces org-scoped RBAC correctly, but the frontend does not gate UI elements by role (`Sidebar.tsx:4-33` shows the same nav to all authenticated users); a `developer` role can currently see write-action buttons that the backend will then correctly reject, which is a confusing UX rather than a security hole.
- **i18n** — SecureWise frontend has zero internationalization (unlike the rest of GuideWisey, which supports NL/EN); English-only.
- **Mobile design** — partial responsive support (`Layout.tsx:47-61`, media queries in `index.css`) but tables/detail pages are desktop-oriented.

---

## 5. What is production-ready

- Data model, migrations, admin.
- Org/RBAC/audit-log security posture for a **multi-tenant SaaS control plane** (not the scanning execution itself).
- Report generation pipeline (HTML/PDF/JSON) and its frontend consumption.
- SAST/SCA/Secrets/IaC scanners **when the underlying tool is installed in the runtime image** — the moment `semgrep`/`trivy`/`gitleaks` are missing, results silently degrade to weaker heuristics. This degradation is not fake, but the two modes ("real tool" vs "fallback") are not clearly surfaced to the end user in the report.

## 6. What is NOT production-ready

- Scan execution model (raw daemon threads, no queue, no worker autoscaling, no crash recovery, no retry).
- DAST (passive-only; would fail any credible security audit if labeled "DAST").
- API security testing (static-only).
- No dockerization / runtime execution of the target application at all.
- No pen-test capability, AI-planned or otherwise.
- No Playwright-based authenticated flow testing.
- Container scanning depends on the user manually supplying an already-built image reference.
- Tool availability (gitleaks/trivy) is **not guaranteed by the Dockerfile** — `Dockerfile` installs system libs but not gitleaks/trivy binaries (per audit), meaning **production deployment may silently run in fallback/heuristic mode for SCA/secrets/IaC without operators realizing it**.

---

## 7. Top risks

1. **Silent scanner degradation.** If `trivy`/`gitleaks`/`semgrep` binaries are absent in the deployed container, scans "complete successfully" using much weaker heuristics, and nothing in the UI/report loudly says "ran in fallback mode." This is a **trust/credibility risk**: customers may believe they received a real SCA/secrets scan when they received a curated-lockfile check instead.
2. **DAST/API scanning name vs reality mismatch.** Calling passive HTTP-header inspection "DAST" and OpenAPI static parsing "API scanning" is a **product-honesty risk** and, if marketed externally, a potential legal/compliance risk (customers may rely on a report that says "DAST: passed" when no dynamic testing occurred).
3. **Thread-based async execution has no durability.** A process restart/deploy during a running scan silently loses that scan's progress with no automatic recovery or alerting.
4. **No authorization gate for "run this against a live target."** Because there's no runtime environment manager yet, this isn't exploitable today, but the design must bake in "only scan targets the user owns/has explicitly authorized" *before* dynamic/pentest features are added — this is a hard requirement in the vision and needs to be enforced at the data-model level (e.g., a `target_ownership_confirmed` field + admin approval flow for external URLs), not just a policy document.
5. **Two divergent remediation systems** (template-based per-scanner vs AI-based) increases maintenance burden and can produce inconsistent guidance for the same finding type.

---

## 8. Technical debt

- Raw `threading.Thread(daemon=True)` for scan execution (`views.py:645,707`) — explicitly marked as MVP-only in code comments; must be replaced before real concurrent multi-tenant load.
- Duplicate remediation logic (scanner-level templates + `ai_recommendation.py`).
- No data migration seeding scan policies/rule packs — every org must configure `SecureWiseScanPolicy` from scratch.
- Container scanner requires manual image reference; no build step, so it's rarely used in practice.
- Frontend has no role-based UI gating (cosmetic-only issue today, but will need addressing as roles diverge more, e.g., `auditor` role is defined but not special-cased anywhere).

---

## 9. Missing architecture (relative to the vision)

Entirely absent, need to be designed and built from scratch:

- **CodeUnderstandingEngine** (language/framework/build/run detection, `ApplicationRunPlan` model)
- **DockerizationEngine** (validate existing Dockerfile / generate one / build image)
- **RuntimeEnvironmentManager** (isolated network, start app, health-check, collect logs, teardown)
- **FullScanOrchestrator** that sequences pre-runtime (SAST/SCA/secrets/IaC) → build/runtime (container scan, start app) → runtime testing (real DAST via ZAP, API testing against the live app, Playwright flows, AI pen-test scenarios) → post-processing (correlate, score, remediate, report)
- **AI Pen-Test Planner** (structured `PenTestPlan` JSON generation from code/routes/OpenAPI/auth flow understanding)
- **PlaywrightEngine** (AI-generated authenticated flow tests, evidence capture)
- **Real ZAP-based DAST engine** (automation YAML, passive+spider+optional active, normalized findings — not an attached HTML report)
- **Unified finding model extensions** (exploitability, cvss, correlation_group, retest_status — some fields already exist, some don't)
- **FindingCorrelationEngine** (generalized, not just DAST↔SAST fingerprint matching)
- Proper async job execution (Celery/RQ + broker) to replace daemon threads

---

## 10. Honest maturity scoring (see also `IMPLEMENTATION_ROADMAP.md` for detail)

| Dimension | Score (0-10) | Rationale |
|---|---|---|
| Data model / multi-tenancy | 8/10 | Solid, normalized, extensible |
| RBAC / audit / permissions | 8/10 | Real org-scoped enforcement + audit trail |
| Static scanning (SAST/SCA/Secrets/IaC) | 5/10 | Real when tools installed, silent fallback otherwise, no visibility into which mode ran |
| Dynamic scanning (DAST/API) | 2/10 | Passive-only; not credible as "DAST" |
| Runtime/dockerization/execution of target app | 0/10 | Does not exist |
| Pen-test planning & execution | 0/10 | Does not exist |
| Playwright / authenticated flow testing | 0/10 | Does not exist |
| Correlation | 3/10 | Limited DAST↔SAST fingerprint matching only |
| AI remediation | 6/10 | Real, provider-dependent, honest fallback messaging |
| Reporting | 7/10 | Real, multi-format, but assumes upstream findings are trustworthy |
| Async/job durability | 2/10 | Thread-based MVP only |
| Frontend UX | 6/10 | Real, functional, good finding/report detail; no RBAC gating, no i18n, limited mobile |

**Overall current maturity: ~35-40%** of the platform described in the vision document exists today, concentrated almost entirely in the "static analysis SaaS" layer. The "dynamic/runtime/pentest" half of the vision (roughly steps 5-9 of the user's described flow) has **0% implementation**.
