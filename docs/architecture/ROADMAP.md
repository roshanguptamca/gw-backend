# SecureWise — Roadmap

> Generated: 2026-07-02 · Branch: `feature/securewise-production-scans`

---

## Phase 1: Production Foundation (Weeks 1–4)

### Goals
Make SecureWise production-ready by eliminating critical architectural risks.

### Deliverables
1. **Task queue:** Replace `threading.Thread` with Celery + Redis. `ScannerRunner.run_scan` becomes a Celery task. Add retry with exponential backoff (max 3 retries), dead letter queue for permanently failed scans.
2. **Scan state recovery:** Startup hook marks orphaned "running" scans as "failed". Periodic beat task detects scans stuck >15min and marks them failed with `error_message="Scan timed out"`.
3. **API versioning:** Mount all SecureWise endpoints under `/api/v1/securewise/`. Add deprecation header middleware.
4. **Fix ScanSerializer duplicate validate:** Merge the two `validate()` methods in `serializers.py`.
5. **Database indexes:** Add composite indexes on `(project_id, status)`, `(project_id, scanner_type, status)`, `(organization_id, created_at)`.
6. **Structured logging:** Switch to JSON structured logging with correlation IDs (scan_id, request_id).
7. **Fix GitLab token header:** Correct the masked placeholder in `views.py:259`.

### Dependencies
- Redis instance (for Celery broker/backend)
- PostgreSQL confirmed for all non-dev environments

### Acceptance Criteria
- [ ] Scans survive gunicorn worker restarts (scan resumes or is correctly marked failed)
- [ ] Concurrent scans do not compete for WSGI worker resources
- [ ] All endpoints accessible under `/api/v1/` prefix
- [ ] No orphaned "running" scans after 24h in any environment

---

## Phase 2: Plugin Architecture & Scanner Extensibility (Weeks 3–7)

### Goals
Enable adding new scanners without modifying core orchestrator code.

### Deliverables
1. **Plugin interface:** `ScannerPlugin` protocol, `ScannerPluginManifest`, `ScanContext` (see `PLUGIN_ARCHITECTURE.md`)
2. **Plugin registry:** Singleton registry with Django settings loading (`SECUREWISE_SCANNER_PLUGINS`)
3. **Adapter wrappers:** Wrap all 7 existing scanners as plugins
4. **Orchestrator refactor:** Use registry instead of `_ENGINE_CLASSES` dict
5. **SARIF import plugin:** Generic plugin that imports SARIF files from any tool
6. **Fingerprint validation:** Post-scan validation that fingerprints are content-stable and properly prefixed

### Dependencies
- None (can start in parallel with Phase 1)

### Acceptance Criteria
- [ ] New scanner can be added by pip-installing a package + adding to `SECUREWISE_SCANNER_PLUGINS`
- [ ] All existing scanner tests still pass with plugin-wrapped scanners
- [ ] SARIF import produces valid `ScannerFinding` objects with stable fingerprints
- [ ] Orchestrator has no direct imports of scanner classes

---

## Phase 3: Git Integration & CI/CD (Weeks 5–10)

### Goals
Enable automated scanning in developer workflows.

### Deliverables
1. **GitHub App:** OAuth-based installation flow (replaces PAT-only auth), webhook event handling
2. **Webhook-triggered scans:** Auto-scan on push/PR events via GitHub webhooks
3. **PR status checks:** Set commit status / check run from quality gate result
4. **PR annotations:** Post finding comments directly on PR diff lines
5. **CLI tool:** `securewise` CLI for local scanning (`securewise scan --repo . --type sast`)
6. **GitHub Actions integration:** `securewise/scan-action` for CI pipelines
7. **GitLab support:** Full GitLab API integration (MR comments, pipeline integration)

### Dependencies
- Phase 1 (task queue for webhook-triggered scans)

### Acceptance Criteria
- [ ] GitHub App can be installed on a repo and auto-scans on PR
- [ ] Quality gate result appears as a GitHub check run (pass/fail/pending)
- [ ] CLI tool can scan a local directory and output JSON/SARIF
- [ ] GitLab MR scanning works end-to-end

---

## Phase 4: AI Architecture v2 (Weeks 8–14)

### Goals
Evolve from single fix endpoint to multi-agent AI system.

### Deliverables
1. **Provider extensions:** `generate_structured()`, `generate_streaming()`, `function_call()` on `BaseAIProvider`
2. **Agent base class:** `SecurityAgent` with system prompt, output schema, safety preamble
3. **AI Orchestrator:** Routes tasks to agents, validates output, manages context
4. **Triage Agent:** Finding prioritization, false-positive probability scoring
5. **Code Review Agent:** Security-focused PR diff analysis
6. **Enhanced Fix Agent:** Multi-file fixes, AST-aware context, streaming responses
7. **Agent result caching:** Cache at `(fingerprint, agent, model_version)` level

### Dependencies
- Phase 1 (task queue for async agent execution)

### Acceptance Criteria
- [ ] Triage agent reduces mean-time-to-triage by >50% on demo scans
- [ ] Code review agent produces actionable comments on PR diffs
- [ ] Fix agent can suggest multi-file fixes with correct imports
- [ ] All agents pass prompt-injection safety test suite

---

## Phase 5: Knowledge Graph (Weeks 12–18)

### Goals
Enable relationship-based reasoning about security posture.

### Deliverables
1. **Apache AGE installation:** PostgreSQL extension setup
2. **Core graph schema:** Organization, Project, Repository, Scan, Finding, CWE, OWASP nodes
3. **Graph sync hooks:** Django signals to sync model changes to graph
4. **Dependency graph:** SCA results populate Dependency→Advisory edges
5. **Cross-project correlation:** "This vulnerable dependency exists in N projects" queries
6. **Blast radius API:** `GET /findings/{id}/blast-radius/` endpoint
7. **Graph-powered dashboard:** Enhanced dashboard with relationship-based analytics

### Dependencies
- Phase 1 (PostgreSQL required)

### Acceptance Criteria
- [ ] "Which projects use log4j < 2.17.1?" query returns correct results across all projects
- [ ] Blast radius endpoint returns connected assets for a given finding
- [ ] Graph data stays in sync with relational data (no stale nodes)

---

## Phase 6: Enterprise Features (Weeks 16–22)

### Goals
Make SecureWise enterprise-ready for large organizations.

### Deliverables
1. **SSO/SAML:** SAML 2.0 and OIDC integration for enterprise identity providers
2. **Fine-grained RBAC:** Per-project permissions, custom roles, permission matrix
3. **Compliance frameworks:** SOC2, ISO 27001, PCI-DSS, HIPAA control mapping
4. **Audit export:** Compliance-ready audit log export (CSV, PDF)
5. **Row-level security:** PostgreSQL RLS for tenant data isolation
6. **Secret rotation workflow:** Detect rotation-eligible secrets, initiate automated rotation
7. **Report scheduling:** Recurring report generation (daily/weekly digest) via Celery Beat

### Dependencies
- Phase 1 (task queue for scheduling)
- Phase 5 (knowledge graph for compliance mapping)

### Acceptance Criteria
- [ ] Enterprise SSO login works with Okta/Azure AD
- [ ] Auditor role cannot see findings from projects they're not assigned to
- [ ] SOC2 compliance report maps findings to relevant controls
- [ ] Row-level security prevents cross-tenant data access at the database level

---

## Phase 7: Developer Experience (Weeks 20–26)

### Goals
Meet developers where they work.

### Deliverables
1. **VS Code extension:** Inline finding display, one-click fix application, scan trigger
2. **JetBrains plugin:** IntelliJ/PyCharm/WebStorm support
3. **Pre-commit hooks:** `securewise-pre-commit` hook for local SAST/secrets scanning
4. **AI Test Generation Agent:** Security test scaffolding per finding (pytest, Jest, JUnit)
5. **Interactive learning:** Contextual security tutorials linked from findings
6. **Notification integrations:** Slack, Teams, PagerDuty notifications on scan events

### Dependencies
- Phase 2 (plugin SDK for CLI/IDE integration)
- Phase 3 (CLI tool as foundation for IDE plugins)
- Phase 4 (AI agents for test generation)

### Acceptance Criteria
- [ ] VS Code extension shows inline squiggles for findings with severity-colored markers
- [ ] Pre-commit hook blocks commits containing secrets (< 3s scan time)
- [ ] Test generation agent produces compilable test code for >70% of findings

---

## Phase 8: Advanced AI & Threat Modeling (Weeks 24–30)

### Goals
Differentiate SecureWise with AI capabilities no legacy scanner can match.

### Deliverables
1. **Threat Model Agent:** Automated STRIDE analysis from codebase + architecture
2. **AI rule synthesis:** LLM generates Semgrep rules from vulnerability descriptions
3. **Attack path visualization:** Graph-powered attack path rendering in UI
4. **Predictive security scoring:** ML-based risk prediction per project/commit
5. **Auto-remediation pipeline:** Confidence-gated automated fix → PR → CI → merge flow
6. **Dependency Agent:** Deep dependency risk analysis (maintenance, typosquatting, license)

### Dependencies
- Phase 4 (multi-agent AI)
- Phase 5 (knowledge graph for attack paths)

### Acceptance Criteria
- [ ] Threat model agent produces STRIDE analysis for a new project in <60s
- [ ] AI-synthesized Semgrep rules have <10% false-positive rate
- [ ] Attack path visualization shows exploitable chains from DAST→SAST→SCA findings

---

## Phase 9: Scale & Performance (Weeks 28–34)

### Goals
Handle enterprise-scale workloads (1000+ repos, 100K+ findings).

### Deliverables
1. **Parallel engine execution:** Concurrent scanner plugin execution within a scan
2. **Scan queue management:** Priority queues, concurrency limits per org/runner
3. **Finding search:** Elasticsearch/Meilisearch for full-text finding search + faceted filtering
4. **Dashboard caching:** Redis-cached dashboard aggregations with smart invalidation
5. **Database optimization:** Read replicas, query optimization, finding archival
6. **Horizontal scaling:** Stateless workers, shared-nothing architecture verification
7. **Performance benchmarks:** Automated load tests, regression detection

### Dependencies
- Phase 1 (task queue)
- Elasticsearch/Meilisearch infrastructure

### Acceptance Criteria
- [ ] Full scan of 10K-file repo completes in <5 minutes
- [ ] Dashboard loads in <500ms with 100K+ findings
- [ ] 50 concurrent scans execute without resource starvation

---

## Phase 10: Platform & Ecosystem (Weeks 32–40)

### Goals
Build SecureWise into a platform others build on.

### Deliverables
1. **Plugin marketplace:** UI for discovering and enabling scanner plugins
2. **Public API documentation:** OpenAPI spec, developer portal, API keys
3. **Webhook system:** Configurable outbound webhooks for all events
4. **Multi-language support:** i18n for UI and reports
5. **White-label reports:** Customizable branding for reports
6. **On-premises deployment guide:** Helm chart, Docker Compose, Kubernetes operator
7. **Customer-facing SDK:** Python SDK for programmatic access

### Dependencies
- Phase 2 (plugin architecture)
- Phase 6 (enterprise features)

### Acceptance Criteria
- [ ] Third-party scanner plugin can be installed from marketplace in 3 clicks
- [ ] Public API has OpenAPI spec with interactive documentation
- [ ] On-premises deployment tested on EKS, GKE, and bare-metal Kubernetes
