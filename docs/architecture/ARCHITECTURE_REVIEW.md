# SecureWise — Architecture Review

> Generated: 2026-07-02 · Branch: `feature/securewise-production-scans`
> Role: Lead Software Architect & Principal Security Engineer

---

## 1. Current State Summary

SecureWise is a multi-tenant Application Security Platform implemented as a Django app (`apps/securewise/`) within the GuideWisey Django monolith. It provides 7 scan engines (SAST, SCA, Secrets, DAST, IaC, Container, API) with real tool integration (Semgrep, Trivy, Gitleaks), fingerprint-based finding deduplication, quality gate policies, AI fix suggestions, branded HTML/PDF reports, and GitHub issue/PR creation.

For a detailed module-by-module description, see [`CURRENT_STATE.md`](./CURRENT_STATE.md).

## 2. Architecture Evaluation

### 2.1 Modularity Assessment

**Strengths:**
- Clean separation between scanner interface (`BaseScanner`), orchestration (`ScannerOrchestrator`), and persistence (`ScannerRunner`)
- `ScannerFinding` and `ScannerResult` are pure dataclasses with no Django dependencies — excellent for testability
- AI provider abstraction (`BaseAIProvider`) is genuinely provider-agnostic
- Service layer (`services/`) separates business logic from views
- Per-engine result tracking (`ScanEngineResult`) enables granular observability

**Weaknesses:**
- **Hardcoded engine registry** (`orchestrator.py:25-33`): `_ENGINE_CLASSES` dict requires code changes to add scanners
- **Inline permission checks** (`views.py`): Every viewset duplicates `_membership()` checks instead of using DRF permission classes
- **Views are too fat**: `views.py` at 1,147 lines handles HTTP, permissions, business logic, and audit logging — classic "fat controller" pattern
- **Two repository modules**: `services/repository.py` (URL validation) and `scanners/repository.py` (cloning) split related concerns across different packages

### 2.2 Plugin-Ability Assessment

**Can Semgrep/Checkmarx/Sonar/internal scanners be plugged in today?** No. Adding any scanner requires:
1. New Python class in `apps/securewise/scanners/`
2. Modifying `_ENGINE_CLASSES` in `orchestrator.py`
3. Modifying `ENGINE_CHOICES`/`SCAN_TYPE_CHOICES` in `models.py`
4. Deploying updated backend

The `BaseScanner` interface is clean but not designed for external consumption — no manifest, no configuration, no entry-point loading, no SARIF interoperability. See [`PLUGIN_ARCHITECTURE.md`](./PLUGIN_ARCHITECTURE.md) for the proposed plugin system.

### 2.3 AI-Everywhere Feasibility

**Can AI be integrated into every step?** Not with current architecture. Today's single `generate(system, user) → str` provider interface supports only one-shot text generation. Multi-agent orchestration, structured output, streaming, function calling, and agent-to-agent communication all require extending the provider abstraction. The existing prompt-injection safety framing in `ai_recommendation.py` is well-designed and should be generalized to all agents. See [`AI_ARCHITECTURE.md`](./AI_ARCHITECTURE.md).

### 2.4 Enterprise-Grade Readiness

**Critical blockers:**
1. **Thread-per-scan**: `threading.Thread` daemon threads in the WSGI process (`views.py:647`) cannot survive process restarts, have no retry/backoff, compete for GIL/resources, and provide no crash recovery. This is the single biggest production risk.
2. **No scan state recovery**: A killed scan stays "running" forever. No watchdog, no timeout, no cleanup.
3. **SQLite default**: The development database cannot handle concurrent writes from multiple workers.
4. **No API versioning**: Breaking changes will affect all clients simultaneously.
5. **Duplicate validate() method**: `SecureWiseScanSerializer` has two `validate()` methods — the first (scan-type validation) is silently overridden by the second (organization derivation), meaning scan-type validation is dead code.

### 2.5 Specific Technical Debt and Code Smells

| Issue | Location | Severity |
|-------|----------|----------|
| Thread-per-scan, no task queue | `views.py:647,708` | 🔴 Critical |
| Duplicate `validate()` silently drops validation | `serializers.py:356-406` | 🔴 Critical |
| No scan state recovery | `services/scanner.py` | 🔴 Critical |
| N+1 queries in serializer computed fields | `serializers.py` (get_scan_count, get_open_findings_count, etc.) | 🟡 High |
| Dashboard fires 10+ separate COUNT queries | `views.py:1067-1146` | 🟡 High |
| Inline permission checks duplicated across all viewsets | `views.py` every `perform_*` method | 🟡 High |
| `urllib.request` + manual SSL alongside `requests` library | `views.py:234-304`, `github_actions.py:70-113` | 🟠 Medium |
| GitLab token header is masked placeholder string | `views.py:259` | 🟠 Medium |
| PR creation uses exact substring replacement | `github_actions.py:297` | 🟠 Medium |
| DummyProvider returns career/resume JSON | `ai_services/providers.py:97-112` | 🟢 Low |
| TanStack Query installed but unused | `securewise-frontend/package.json` | 🟢 Low |
| Audit event choices drift from actual usage | `models.py:146-169` | 🟢 Low |

See [`TECHNICAL_DEBT.md`](./TECHNICAL_DEBT.md) for the complete register with 25 items.

### 2.6 Redesign Recommendations

| Area | Current | Recommended | Reason |
|------|---------|-------------|--------|
| **Architecture** | Django app inside GuideWisey monolith | **Modular monolith** (keep Django, extract SecureWise into its own deployable with shared DB) | Full microservice is premature; modular monolith gives deployment independence without distributed system complexity. SecureWise shares auth/users but nothing else with GuideWisey. |
| **Task execution** | `threading.Thread` | **Celery + Redis** | Django ecosystem standard, mature, battle-tested. Dramatiq is lighter but Celery has broader Django integration (django-celery-beat, django-celery-results, Flower monitoring). |
| **Plugin system** | Hardcoded dict | **Plugin protocol + registry + settings + entry_points** | See `PLUGIN_ARCHITECTURE.md`. Must support both built-in and pip-installable third-party scanners. |
| **Event system** | Direct function calls | **Django signals → event bus (future)** | Start with Django signals for graph sync and notifications. Evolve to event bus (Redis Streams or Kafka) when cross-service communication is needed. |
| **Caching** | None | **Redis** (already needed for Celery) | Dashboard aggregations, AI suggestion caching, rate limit state. Use Django's cache framework with Redis backend. |
| **Search** | `icontains` queries | **Meilisearch** (lightweight) or **Elasticsearch** (enterprise) | Finding search at scale needs full-text search with faceted filtering. Start with Meilisearch (simpler ops). |
| **Real-time updates** | HTTP polling | **Django Channels + WebSocket** (or SSE) | Scan progress polling is inefficient. WebSocket provides instant status updates. |
| **Permissions** | Inline `_membership()` checks | **DRF permission classes + django-guardian or custom RBAC middleware** | Declarative, auditable, testable permission system. |

---

## 3. Final Synthesis

### Maturity Scores (0–100%)

| Dimension | Score | Rationale |
|-----------|:-----:|-----------|
| **Current Maturity** | 32% | Solid MVP with real tool integration and thoughtful dedup/quality-gate design, but critical production gaps (task queue, crash recovery, scan validation). ~6,500 lines of backend code, 192 tests, 7 scanners — good velocity, needs hardening. |
| **Enterprise Readiness** | 15% | Thread-per-scan, no SSO/SAML, no compliance frameworks, simple RBAC, no API versioning, no scan scheduling. Not deployable for enterprise customers without Phase 1+6 work. |
| **Scalability** | 12% | Single-process threading, no caching, N+1 queries in serializers, unbounded dashboard aggregation, sequential engine execution. Would degrade noticeably at >50 concurrent users or >10K findings. |
| **Security** | 55% | Good: encrypted tokens (Fernet), path-traversal protection on clone, prompt-injection defense, CSRF handling, token cleanup, audit logging. Gaps: no RLS, no SSO, rate limiting gaps on scan start, GitLab auth header bug. |
| **Maintainability** | 50% | Good: clean scanner interface, dataclass-based DTOs, service layer separation, ADRs documenting decisions, comprehensive test suite. Bad: fat views.py, inline permissions, duplicate validate method, two repository modules, DummyProvider mismatch. |
| **AI Readiness** | 10% | Single reactive endpoint with good safety framing, but no multi-agent architecture, no structured output, no streaming, no function calling, no proactive AI. Provider abstraction is extensible. |
| **Plugin Readiness** | 5% | `BaseScanner` is a good interface shape but not designed for external consumption. No registry, no configuration-based loading, no SARIF interop, no marketplace. |
| **Architecture Readiness** | 25% | Solid data model, clean FK relationships, good separation in scanner layer. Major gaps: no task queue, no event system, no graph, no caching, embedded in monolith, hardcoded engine registry. |

### Top 20 Missing Capabilities (Ranked)

| Rank | Capability | Impact | Roadmap Phase |
|------|-----------|--------|--------------|
| 1 | Task queue (Celery + Redis) | Production-blocking | Phase 1 |
| 2 | Scan state recovery / watchdog | Production-blocking | Phase 1 |
| 3 | Plugin SDK / scanner interface | Extensibility-blocking | Phase 2 |
| 4 | CI/CD integration (GitHub Actions, webhook scans) | Adoption-blocking | Phase 3 |
| 5 | API versioning | Breaking-change risk | Phase 1 |
| 6 | GitHub App / OAuth (replace PAT-only) | Enterprise requirement | Phase 3 |
| 7 | Multi-agent AI architecture | Differentiation-critical | Phase 4 |
| 8 | Real-time scan updates (WebSocket) | UX improvement | Phase 3 |
| 9 | Knowledge graph (initial) | AI reasoning enabler | Phase 5 |
| 10 | Cross-project finding correlation | Security insight | Phase 5 |
| 11 | Fine-grained RBAC + SSO/SAML | Enterprise requirement | Phase 6 |
| 12 | IDE plugins (VS Code) | Developer adoption | Phase 7 |
| 13 | CLI tool | Developer adoption | Phase 3 |
| 14 | Compliance framework mapping | Enterprise sales | Phase 6 |
| 15 | AI triage agent | Noise reduction | Phase 4 |
| 16 | Scan scheduling (cron) | Automation | Phase 6 |
| 17 | SARIF import/export | Interoperability | Phase 2 |
| 18 | Threat modeling | Differentiation | Phase 8 |
| 19 | Finding full-text search | Scale readiness | Phase 9 |
| 20 | Parallel engine execution | Performance | Phase 9 |

### Recommended Implementation Order

1. **Phase 1** (Production Foundation) — do this NOW, before any new features
2. **Phase 2** (Plugin Architecture) — can overlap with Phase 1
3. **Phase 3** (Git/CI/CD Integration) — highest user-facing value after production readiness
4. **Phase 4** (Multi-Agent AI) — key differentiator, start after Phase 1
5. **Phase 5** (Knowledge Graph) — enables advanced AI and correlation
6. **Phase 6** (Enterprise Features) — unlocks enterprise sales
7. **Phases 7–10** — developer experience, advanced AI, scale, platform

---

## If I Were Building SecureWise as a Company from Scratch Today, What Would I Change Before Writing Another Line of Code?

### 1. Kill the threading.Thread model immediately

This is not a "nice to have" or "do it later" item. Thread-per-scan inside the WSGI process is fundamentally broken for production:
- **No crash recovery:** A gunicorn worker restart mid-scan silently orphans the scan in "running" state. The user sees a spinner that never stops. There is no watchdog, no timeout, no cleanup task.
- **Resource competition:** Each scan spawns 3-7 subprocess calls (git clone, semgrep, trivy, gitleaks). With N concurrent scans, you're running N×7 subprocesses competing with the web server for CPU, memory, and file descriptors — inside the same process.
- **No observability:** You can't monitor, retry, rate-limit, or prioritize scans. There's no dead letter queue. There's no way to tell if a scan is actually running or just a zombie thread.
- **The fix is straightforward:** `ScannerRunner.run_scan(scan_id)` is already a clean function signature that takes a scan ID and does all its own DB lookups. Wrapping it as `@celery.task` is a 10-line change. Do it.

### 2. Extract SecureWise from the GuideWisey monolith

SecureWise shares exactly one thing with GuideWisey: the `User` model for authentication. Everything else — models, views, scanners, AI, reports — is completely independent. But because it's an app inside the GuideWisey Django project, you can't:
- Deploy SecureWise independently (need more workers? scale up the whole monolith)
- Run scan workers on different hardware (maybe GPU-enabled for AI, or high-CPU for scanners)
- Have a different release cadence
- Use a different database (might want PostgreSQL with Apache AGE for the knowledge graph while GuideWisey uses a simpler setup)

The correct architecture is a **modular monolith**: SecureWise as its own Django project that shares the user database (or authenticates via JWT/session against GuideWisey's auth endpoints). Not microservices — you don't have the team or traffic to justify distributed system complexity. Just separate deployables.

### 3. Fix the serializer validation bug

There are two `validate()` methods on `SecureWiseScanSerializer`. Python silently keeps only the last one. The first one — which validates that source-dependent scan types have a repository, DAST has a target URL, and bypass requires a reason — is **dead code**. This means you can create a SAST scan with no repository and it'll be accepted, then fail at scan time with a confusing error. This is a 5-minute fix that should have been caught by a linter (redefined-method).

### 4. Don't build another scanner aggregator — build an AI-native security platform

The honest truth: as a scanner orchestrator, SecureWise is competing with DefectDojo (free, mature, supports 150+ tool imports), Aikido (modern, well-funded), and GitHub Advanced Security (free for public repos, built into the world's largest code platform). You will not win on breadth of scanner support, community size, or distribution.

What you CAN win on:
- **AI-native workflows** that legacy vendors can't easily retrofit. Every finding in SecureWise already has structured context (CWE, OWASP, code snippet, file path) — this is exactly what an AI needs to generate meaningful fixes, tests, threat models, and triage decisions. The existing prompt-injection safety framing is already better than most competitors' AI integrations.
- **Knowledge graph-powered reasoning** that turns isolated findings into connected security insights. "This SQL injection in your API endpoint is reachable via an unauthenticated route and uses a dependency with a known RCE" is a sentence no other scanner can generate today.
- **Developer-first remediation** where the platform doesn't just find problems but fixes them — AI-generated PRs, security tests, and contextual education.

Stop competing on scanner count. Start competing on intelligence.

### 5. Make the plugin SDK the first thing you ship, not the last

Every week you delay the plugin SDK, you're writing bespoke integration code that will need to be rewritten when the SDK exists. The `BaseScanner` interface is 80% there — it just needs a manifest, a registry, and an entry-point loading mechanism. Ship it in Phase 2 and make every subsequent scanner integration use it, including your own.

### 6. Invest in the knowledge graph early

The relational model is a dead end for the kind of reasoning SecureWise needs to be differentiated. "All findings in projects that depend on this compromised library" is a simple graph query but requires N sequential SQL queries with manual JOIN logic today. The knowledge graph is not a nice-to-have — it's the foundation that makes AI agents useful. Without it, your AI agents are operating on individual findings with no context about the broader security posture.

### 7. Accept that DAST is immature and don't oversell it

The DAST scanner checks HTTP headers and cookies. That's it. It doesn't invoke ZAP even when ZAP is available (the code explicitly says "detected but not invoked by default"). Don't call this "DAST scanning" in marketing — call it "passive security header analysis." Real DAST is ZAP/Burp Suite, and integrating those properly (with authentication, session management, scope control, and time limits) is a substantial engineering effort. Either commit to it or be honest about what you have.

### 8. The quality gate system is actually quite good — don't break it

The tri-state quality gate (True/False/None per ADR-0003), the `fail_on_new_findings_only` option, `allow_accepted_risks`, the is_default policy with auto-attach, and the bypass-with-reason audit trail — this is genuinely well-designed and competitive with SonarQube's quality gates. The main gaps are CI/CD integration (can't set a GitHub check status from a quality gate result) and policy-as-code (can't express "fail if any critical finding is in a file matching `**/auth/**`"). Build on this strength.
