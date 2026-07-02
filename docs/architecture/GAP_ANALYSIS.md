# SecureWise — Gap Analysis, Subsystem Scoring & Industry Comparison

> Generated: 2026-07-02 · Branch: `feature/securewise-production-scans`

---

## 1. Subsystem Scoring (0–100%)

| # | Subsystem | Score | Current State Summary | Key Missing Capabilities | Priority |
|---|-----------|:-----:|----------------------|-------------------------|----------|
| 1 | **Scanner Orchestrator** | 45% | Sequential engine execution, hardcoded registry, per-engine status tracking, cancellation support, auto-resolve on rescan | Plugin system, parallel engine execution, configurable per-scan engine ordering, scan queue management, distributed execution | Critical |
| 2 | **Finding Correlation Engine** | 12% | Naive SAST↔DAST keyword matching in `_correlate()`, fingerprint-based dedup (per-project only) | Cross-project correlation, semantic/AI-based dedup, attack path construction, dependency→finding→endpoint chains, SAST↔SCA↔DAST multi-signal correlation | Critical |
| 3 | **AI Security Brain** | 8% | Single reactive fix-suggestion endpoint, one LLM call, cached results, prompt-injection defense | Multi-agent architecture, proactive analysis, AI triage/prioritization, AI code review, AI-assisted rule synthesis, AI threat modeling, agent orchestration, streaming | Critical |
| 4 | **Security Knowledge Graph** | 0% | Plain FK relations, no graph model, no traversal/reasoning | Graph database, node/edge types, blast-radius queries, attack-path reasoning, cross-entity correlation, AI context enrichment | High |
| 5 | **Workflow Engine** | 15% | GitHub issue + PR creation, finding status lifecycle (open→fixed/accepted_risk/false_positive), scan retry | Configurable workflows, approval chains, escalation rules, SLA tracking, notification routing, integration with Jira/Slack/PagerDuty (model exists but no logic), scheduled scans | High |
| 6 | **Plugin SDK** | 0% | No plugin interface, hardcoded engine classes, no external scanner support | Plugin protocol, registry, configuration-based loading, entry points, marketplace, SARIF import | High |
| 7 | **Threat Modeling** | 0% | No threat modeling capability | STRIDE analysis, data flow diagrams, attack surface enumeration, asset identification, threat library | Medium |
| 8 | **Compliance** | 5% | CWE + OWASP Top 10 mapping on findings, OWASP/CWE report types | SOC2/ISO27001/PCI-DSS/HIPAA framework mapping, control evidence collection, compliance dashboard, audit-ready reports, policy-as-code | Medium |
| 9 | **Developer Productivity Tooling** | 20% | AI fix suggestions, code snippets on findings, bad/fixed code examples, GitHub PR creation | IDE plugins (VS Code/JetBrains), CLI tool, pre-commit hooks, CI/CD pipeline integration (GitHub Actions/GitLab CI), PR comments, inline annotations | High |
| 10 | **Security Learning/Training** | 2% | Recommendation engine provides OWASP references and fix guidance per finding | Interactive tutorials, learning paths, gamification, vulnerability labs, developer skill assessment, contextual education | Low |
| 11 | **AI Auto Remediation** | 10% | AI fix suggestion (single endpoint), GitHub PR creation with exact code replacement | Multi-file fixes, AST-aware patching, automated testing of fixes, confidence-gated auto-merge, remediation plans, rollback capability | High |
| 12 | **AI Test Generation** | 0% | No test generation | Security test scaffolding, regression tests for findings, fuzzing config generation, test coverage analysis | Medium |
| 13 | **AI PR Generation** | 25% | GitHub PR with exact substring replacement, branch creation, commit | Multi-file changes, AST-aware diffs, PR review integration, CI status checks, auto-generated test coverage, fuzzy matching | Medium |
| 14 | **RBAC/Permissions** | 30% | 5 roles via Membership.role, inline `_membership()` checks, DRF permission classes (underutilized) | Fine-grained permissions (per-project, per-resource), policy-as-code (OPA/Rego), attribute-based access control, SSO/SAML integration, permission matrix documentation | High |
| 15 | **Reporting** | 55% | 6 report types, JSON/HTML/PDF, branded templates, OWASP/CWE mapping, quality gate status | Report scheduling, historical trend comparison, report versioning/diffing, custom report builder, export to SARIF/CSV, white-labeling, multi-scan aggregate reports | Medium |
| 16 | **Quality Gates** | 60% | Threshold-based policy (max counts per severity), fail_on_secrets, fail_on_new_findings_only, allow_accepted_risks/false_positives, is_default, bypass with reason, tri-state result | Policy-as-code (OPA/Rego), per-repo path exceptions, gradual rollout/canary gates, composite policies, CI/CD integration (webhook/status check), gate history/trend | Medium |
| 17 | **Repository/Git Integration** | 40% | GitHub PAT auth (encrypted), clone/validate, issue/PR creation, connection testing | GitHub App / OAuth flow, GitLab/Bitbucket/Azure DevOps full support, webhook-triggered scans, branch protection integration, PR status checks, secret rotation, repo discovery | High |
| 18 | **Async Execution/Job Infrastructure** | 5% | Python threading.Thread (daemon), no queue, no retry, no crash recovery | Celery/Dramatiq + Redis/RabbitMQ, job monitoring, retry with backoff, dead letter queue, scan concurrency limits, distributed workers, scan timeout watchdog | Critical |
| 19 | **API Design** | 55% | RESTful DRF ViewSets, consistent patterns, throttling, CSRF protection, audit logging | API versioning, OpenAPI schema generation, webhooks/callbacks, GraphQL (optional), pagination consistency, batch operations, field selection | Medium |
| 20 | **Frontend Architecture** | 50% | React 19 + TypeScript + Vite, complete page coverage, typed API client, CSRF handling, responsive layout | State management (TanStack Query unused), error boundaries, optimistic updates, real-time updates (WebSocket), accessibility audit, E2E tests, dark mode, mobile responsiveness | Medium |
| 21 | **Test Coverage** | 55% | 192 backend tests, 11 frontend test files, good coverage of happy paths and edge cases | Integration tests with real tools, E2E tests, load/performance tests, security tests (OWASP ZAP against own API), mutation testing, coverage reporting | Medium |
| 22 | **Observability/Audit Logging** | 35% | AuditLog model with 19+ event types, IP tracking, JSON detail | Structured logging, metrics (Prometheus/StatsD), distributed tracing (OpenTelemetry), alerting, scan performance dashboards, error tracking (Sentry) | Medium |
| 23 | **Multi-tenancy/Data Isolation** | 50% | Organization-scoped querysets via `_get_user_org_ids()`, all models have org FK, queryset filtering in every viewset | Row-level security (PostgreSQL RLS), tenant-aware middleware, data isolation validation tests, cross-tenant access audit, tenant-scoped rate limiting | High |

## 2. Industry Comparison

### 2.1 GitHub Advanced Security (GHAS)
- ✅ **Strengths:** Deep GitHub integration, CodeQL (semantic SAST), Dependabot (SCA), secret scanning with push protection, native PR annotations
- ✅ **Strengths:** Free for public repos, massive adoption
- ❌ **Weakness:** GitHub-only, no cross-platform support, limited customization, no AI remediation
- 💡 **SecureWise differentiation:** AI-native fix suggestions, multi-provider git support, standalone platform not locked to GitHub

### 2.2 Semgrep
- ✅ **Strengths:** Fast, pattern-based SAST, community rule registry, CI/CD integration, Supply Chain product
- ✅ **Strengths:** OSS core, extensible rules, low false-positive rate
- ❌ **Weakness:** SAST-focused (SCA/secrets are newer/less mature), no DAST, no container scanning, limited AI
- 💡 **SecureWise differentiation:** Full-spectrum scanning (7 engines), AI-powered remediation, quality gate policies, integrated reporting

### 2.3 Snyk
- ✅ **Strengths:** Developer-friendly, excellent SCA, container scanning, IaC scanning, IDE plugins
- ✅ **Strengths:** Fix PRs, license compliance, prioritization
- ❌ **Weakness:** SAST (Code) is newer/weaker, expensive at scale, limited AI beyond priority scoring
- 💡 **SecureWise differentiation:** AI-first architecture (multi-agent potential), bundled offline scanning (no cloud dependency), unified orchestration across all scan types

### 2.4 Checkmarx
- ✅ **Strengths:** Enterprise-grade SAST/SCA/DAST, deep language support, compliance certifications
- ❌ **Weakness:** Slow scans, complex setup, expensive, legacy architecture, limited AI innovation
- 💡 **SecureWise differentiation:** Modern stack (Python/React), AI-native design, faster iteration, lower cost

### 2.5 Veracode
- ✅ **Strengths:** Binary analysis (no source needed), compliance-focused, policy management
- ❌ **Weakness:** Slow turnaround (upload→scan→results), expensive, opaque results, no self-hosted option
- 💡 **SecureWise differentiation:** Instant local scanning, transparent rules, self-hosted capability, AI explanations

### 2.6 SonarQube
- ✅ **Strengths:** Mature code quality platform, quality gates, technical debt tracking, wide language support
- ✅ **Strengths:** Self-hosted, large community, IDE integration
- ❌ **Weakness:** Security scanning is secondary to code quality, no SCA/DAST/container/secrets, limited AI
- 💡 **SecureWise differentiation:** Security-first design, full scan spectrum, AI remediation, knowledge graph vision

### 2.7 Aikido Security
- ✅ **Strengths:** All-in-one platform, developer-friendly, good UI, fast growing
- ❌ **Weakness:** Cloud-only, newer/less proven, limited customization
- 💡 **SecureWise differentiation:** Self-hosted option, offline scanning, plugin architecture for custom scanners

### 2.8 Wiz
- ✅ **Strengths:** Cloud-native security, agentless, graph-based risk visualization, CNAPP
- ❌ **Weakness:** Cloud infrastructure focus (not AppSec), expensive, no SAST/DAST
- 💡 **SecureWise differentiation:** Application-layer security focus, code-level findings, developer workflow integration

### 2.9 Microsoft Defender for DevOps
- ✅ **Strengths:** Azure DevOps integration, multi-pipeline support, centralized visibility
- ❌ **Weakness:** Microsoft ecosystem focus, limited standalone value, basic scanning
- 💡 **SecureWise differentiation:** Provider-agnostic, deeper AI integration, standalone platform value

### 2.10 DefectDojo
- ✅ **Strengths:** Excellent finding aggregation/dedup, multi-tool import, risk-based prioritization, open source
- ❌ **Weakness:** Aggregator only (no scanning engine), UI is dated, limited AI
- 💡 **SecureWise differentiation:** Built-in scanning engines + aggregation, AI-native, modern UI, knowledge graph vision

## 3. Gap Analysis Table

| # | Feature | Current State | Target State | Priority | Effort | Dependencies |
|---|---------|--------------|-------------|----------|--------|-------------|
| 1 | Task queue (Celery/Dramatiq) | threading.Thread | Celery + Redis with retry/backoff | Critical | 2-3 weeks | Redis infrastructure |
| 2 | Plugin SDK/interface | Hardcoded engine registry | Plugin protocol + registry + settings-based loading | Critical | 3-4 weeks | None |
| 3 | Scan state recovery | No crash recovery | Stale scan detector + startup recovery | Critical | 1 week | Task queue |
| 4 | API versioning | No version prefix | `/api/v1/` prefix | High | 1 week | None |
| 5 | Multi-agent AI | Single fix endpoint | Agent base class + orchestrator + 3 initial agents | High | 6-8 weeks | Provider extensions |
| 6 | CI/CD integration | None | GitHub Actions, GitLab CI, webhook-triggered scans | High | 4-6 weeks | Webhook infrastructure |
| 7 | GitHub App / OAuth | PAT-only | GitHub App installation flow + OAuth | High | 3-4 weeks | None |
| 8 | Knowledge graph (initial) | FK relations only | Apache AGE + core node/edge sync | High | 4-6 weeks | PostgreSQL |
| 9 | Cross-project correlation | Per-project fingerprint only | Dependency-level and CWE-level cross-project queries | High | 3-4 weeks | Knowledge graph |
| 10 | Real-time scan updates | Polling `/progress/` | WebSocket/SSE for live scan status | High | 2 weeks | None |
| 11 | IDE plugin (VS Code) | None | VS Code extension showing findings inline | High | 4-6 weeks | API versioning |
| 12 | CLI tool | None | `securewise scan --repo . --type full` | High | 2-3 weeks | API versioning |
| 13 | Declarative permissions | Inline _membership() checks | DRF permission classes + role matrix | High | 2 weeks | None |
| 14 | Scan scheduling | schedule_cron field exists but no scheduler | Celery Beat / django-celery-beat | Medium | 1-2 weeks | Task queue |
| 15 | Compliance frameworks | CWE/OWASP mapping only | SOC2/ISO27001/PCI-DSS control mapping | Medium | 4-6 weeks | Compliance DB |
| 16 | SARIF import/export | None | Import SARIF from any tool, export findings as SARIF | Medium | 2 weeks | Plugin SDK |
| 17 | OSV.dev integration | 5-package hardcoded list | Live OSV API with timeout fallback | Medium | 1 week | None |
| 18 | Webhook notifications | None | Configurable webhooks for scan events | Medium | 2 weeks | None |
| 19 | PR status checks | PR creation only | Set commit/PR status check (pass/fail) from quality gate | Medium | 1-2 weeks | GitHub App |
| 20 | Report scheduling | None | Recurring report generation (daily/weekly) | Medium | 1-2 weeks | Task queue |
| 21 | TanStack Query adoption | Axios+useEffect | Proper query caching, dedup, revalidation | Medium | 2 weeks | None |
| 22 | Structured logging | Default Python logging | JSON structured logs with correlation IDs | Medium | 1 week | None |
| 23 | AI triage agent | None | ML-based false-positive detection + priority scoring | Medium | 4-6 weeks | Multi-agent AI |
| 24 | Security test generation | None | AI-generated security test scaffolding per finding | Medium | 3-4 weeks | Multi-agent AI |
| 25 | Threat modeling | None | STRIDE-based automated threat model from codebase | Medium | 6-8 weeks | Knowledge graph, AI |
| 26 | GitLab/Bitbucket support | Model fields exist, no real implementation | Full GitLab + Bitbucket API integration | Medium | 4-6 weeks | None |
| 27 | ZAP active scanning | Detected but not invoked | Configurable ZAP integration with time limits | Medium | 2-3 weeks | ZAP Docker |
| 28 | Database indexing | Only fingerprint indexed | Composite indexes on (project, status), (project, scanner_type, status) | Medium | 1 day | None |
| 29 | Metrics/observability | None | Prometheus metrics, OpenTelemetry traces | Low | 2-3 weeks | Infrastructure |
| 30 | Secret rotation automation | None | Detect rotation-eligible secrets, initiate rotation workflow | Low | 4-6 weeks | Cloud provider APIs |
| 31 | Multi-scan aggregate reports | Single-scan reports only | Cross-scan trend reports, portfolio dashboards | Low | 2-3 weeks | None |
| 32 | Developer learning paths | OWASP references only | Interactive tutorials, vulnerability labs | Low | 6-8 weeks | Content creation |
