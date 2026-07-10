# SecureWise — Current State (As-Built Reference)

> Generated: 2026-07-02 · Branch: `feature/securewise-production-scans`
> This document describes the exact state of the SecureWise codebase as it exists today.

---

## 1. System Overview

SecureWise is a multi-tenant Application Security Platform (SASP) implemented as a Django app (`apps/securewise/`) within the broader GuideWisey Django project. It shares GuideWisey's auth/user model, database, WSGI process, and deployment infrastructure.

**Tech Stack:**
- **Backend:** Django 5.x + Django REST Framework, Python 3.12+
- **Frontend:** React 19 + TypeScript 6 + Vite 8 + Tailwind CSS v4
- **Database:** SQLite (dev) / PostgreSQL (production via `dj-database-url`)
- **Task execution:** Python `threading.Thread` (no Celery/Dramatiq)
- **AI integration:** `apps/ai_services/providers.py` (OpenAI, Azure OpenAI, Gemini, Ollama, Dummy)
- **External tools:** Semgrep (SAST), Trivy (SCA/IaC/Container), Gitleaks (Secrets) — all via subprocess
- **Reports:** Django templates + WeasyPrint for PDF
- **Token encryption:** Fernet (from `cryptography` library)

## 2. Backend Modules

### 2.1 Models (`apps/securewise/models.py` — 738 lines)

10 Django models forming the core domain:

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `SecureWiseOrganization` | Multi-tenant root | UUID PK, slug, owner FK |
| `SecureWiseMembership` | Org↔User junction with RBAC | role (owner/admin/security_engineer/developer/auditor), unique_together(org, user) |
| `SecureWiseGitIntegration` | Encrypted Git provider tokens | Fernet-encrypted `_encrypted_access_token`, `token_last_four`, provider/auth_type/base_url |
| `SecureWiseProject` | Grouping unit for scans/findings | org FK, slug, risk_level, tags |
| `SecureWiseRepository` | Git repository reference | org FK, project FK (nullable), integration FK (nullable), access_mode (public/integration) |
| `SecureWiseScanPolicy` | Quality gate thresholds | max_critical/high/medium, fail_on_severity, fail_on_secrets, fail_on_new_findings_only, is_default |
| `SecureWiseScan` | Individual scan run | org/project/repo/policy FKs, scan_type, status (14 states), progress %, selected_engines, quality_gate_passed (tri-state) |
| `SecureWiseScanEngineResult` | Per-engine result within a scan | engine, status, timing, findings_count, raw_summary, error_message |
| `SecureWiseFinding` | Security finding (deduplicated) | fingerprint (indexed), severity/confidence/status, CWE/OWASP, first_seen_scan/scan/last_seen_at/occurrence_count, code_snippet, ai_fix_suggestion, ticket_url, pr_url |
| `SecureWiseReport` | Generated report (JSON blob + rendered) | format (json/html/pdf), status, report_data JSON, quality_gate_passed |
| `SecureWiseIntegration` | External tool config (Jira/Slack/webhook) | integration_type, config JSON |
| `SecureWiseAuditLog` | Immutable audit trail | event (19 types), target_type/id, detail JSON, ip_address |

**Relationships (all plain Django ForeignKey):**
```
Organization ─┬─ Memberships (user + role)
              ├─ Projects ─── Findings
              ├─ Repositories ─── (integration FK)
              ├─ Scans ─── ScanEngineResults
              │           └── Findings
              ├─ ScanPolicies
              ├─ Reports
              ├─ GitIntegrations
              ├─ Integrations
              └─ AuditLogs
```

### 2.2 Views (`apps/securewise/views.py` — 1,147 lines)

11 ViewSets + 1 APIView, all requiring `IsAuthenticated`:

| ViewSet | Key Actions | Auth Pattern |
|---------|-------------|--------------|
| `OrganizationViewSet` | CRUD | `_membership()` + `ADMIN_ROLES` for update/delete |
| `MembershipViewSet` | CRUD | `ADMIN_ROLES` for create |
| `GitIntegrationViewSet` | CRUD + `test` + `list_repositories` | `ADMIN_ROLES` for all mutations |
| `ProjectViewSet` | CRUD | `WRITE_ROLES` for create/update, `ADMIN_ROLES` for delete |
| `RepositoryViewSet` | CRUD + `validate` + `test_access` | `WRITE_ROLES` for create |
| `ScanPolicyViewSet` | CRUD + `set_default` | `WRITE_ROLES` |
| `ScanViewSet` | CRUD + `start` + `cancel` + `retry` + `progress` + `engine_results` | `WRITE_ROLES` for create |
| `FindingViewSet` | CRUD + `ai_suggestion` + `create_ticket` + `create_pr` + `accept_risk` + `mark_false_positive` | Membership check per action |
| `ReportViewSet` | CRUD + `html` + `pdf` | Membership check |
| `IntegrationViewSet` | CRUD | `ADMIN_ROLES` |
| `AuditLogViewSet` | Read-only list | Membership-filtered queryset |
| `DashboardSummaryView` | GET summary | Membership-filtered aggregation |

**Critical architecture note:** `ScanViewSet.start()` and `retry()` both spawn `threading.Thread(target=runner.run_scan, ...)` as daemon threads within the WSGI process. No task queue, no retry/backoff, no crash recovery.

### 2.3 Permissions (`apps/securewise/permissions.py` — 86 lines)

- `WRITE_ROLES = {"owner", "admin", "security_engineer"}`
- `ADMIN_ROLES = {"owner", "admin"}`
- `_membership(user, org)` → `SecureWiseMembership.objects.filter().first()`
- 4 DRF permission classes: `IsSecureWiseMember`, `IsSecureWiseWriteMember`, `IsSecureWiseAdmin`, `IsOrganizationOwnerOrAdmin`
- **Note:** Permission classes exist but ViewSets mostly use inline `_membership()` checks in `perform_*` methods rather than `permission_classes` on the ViewSet — the classes are underutilized.

### 2.4 Serializers (`apps/securewise/serializers.py` — 587 lines)

12 ModelSerializers covering all models. Notable patterns:
- `MinimalUserSerializer` for nested user details
- `SecureWiseGitIntegrationSerializer` — `access_token` is write-only, never serialized back
- `SecureWiseScanSerializer` — has a **duplicate `validate()` method** (lines 356-406 — the second one silently overrides the first, losing scan-type validation logic)
- `SecureWiseFindingSerializer` — `ai_fix_suggestion_parsed` field parses stored JSON string
- All computed fields (counts, aggregates) are `SerializerMethodField` → N+1 risk at scale

### 2.5 URLs (`apps/securewise/urls.py` — 37 lines)

Standard DRF router with 11 registered viewsets + 1 manual path for dashboard. All mounted under `/api/securewise/`.

### 2.6 Admin (`apps/securewise/admin.py`)

Registers all models with Django admin for debugging.

## 3. Scanner Architecture

### 3.1 Base Interface (`scanners/base.py` — 61 lines)

```python
@dataclass
class ScannerFinding:
    title, description, severity, confidence, scanner_type: str
    file_path, line_number, code_snippet, endpoint: optional
    cwe_id, owasp_category, risk, impact, recommendation: str
    bad_code_example, fixed_code_example: str
    evidence: dict
    fingerprint: str  # defaults to uuid4().hex if not set

@dataclass
class ScannerResult:
    success: bool
    findings: List[ScannerFinding]
    error, status, skipped_reason: str
    metadata: dict

class BaseScanner(ABC):
    scanner_type: str = "unknown"
    def is_available(self) -> bool: ...
    @abstractmethod
    def run(self, repo_path: Path, scan_id: str, metadata: dict) -> ScannerResult: ...
```

### 3.2 Orchestrator (`scanners/orchestrator.py` — 230 lines)

`ScannerOrchestrator`:
- `resolve_engines(scan, repo_path)` — determines which engines to run (full scan = sast+sca+secrets+iac + conditional container/api/dast)
- `run(scan, repo_path)` — iterates engines sequentially, persists `ScanEngineResult` per engine, updates scan status/progress, deduplicates findings by fingerprint, runs cross-engine correlation (SAST↔DAST), populates code snippets
- `_dedupe_and_collect()` — in-memory fingerprint dedup, bumps confidence on duplicates
- `_correlate()` — naive keyword/stem matching between SAST and DAST findings to boost confidence
- `_populate_code_snippets()` — path-traversal-safe code window extraction (3 lines before, flagged line, 2 after)

**Hardcoded engine registry:**
```python
_ENGINE_CLASSES = {
    "sast": SastScanner, "sca": ScaScanner, "secrets": SecretsScanner,
    "iac": IacScanner, "container": ContainerScanner, "api": ApiScanner, "dast": DastScanner,
}
```

### 3.3 Individual Scanners

| Scanner | Lines | Real Tool | Fallback | Fingerprint Pattern |
|---------|-------|-----------|----------|---------------------|
| `sast.py` | 196 | Semgrep (bundled offline rules) | Regex rules (eval, pickle, yaml, SQLi, secrets, debug, weak hash) | `fallback-sast-{issue_key}-{file}-{line}` |
| `sca.py` | 184 | Trivy (`trivy fs --scanners vuln`) | Lockfile parser + curated CVE list (5 packages) | `fallback-sca-{cve}-{package}` |
| `secrets.py` | 124 | Gitleaks | Regex (AWS keys, API keys, private keys, Slack/JWT tokens) | `fallback-secret-{rule}-{file}-{line}` |
| `iac.py` | 192 | Trivy (`trivy config`) | Dockerfile/K8s/Terraform/Helm heuristic checks | `fallback-iac-{issue_key}-{file}` |
| `container.py` | 107 | Trivy (`trivy image`) | Skip if no docker_image; optional build+scan if Docker+Trivy present | N/A (uses Trivy parser) |
| `dast.py` | ~330 | OWASP ZAP baseline (`zap-baseline.py` or ZAP Docker image) | Passive HTTP checks (headers, cookies, CORS, disclosure paths) | `zap-{plugin_id}-{endpoint}` or `dast-{check_type}-{target_url}` |
| `api.py` | 188 | N/A | OpenAPI/Swagger spec static analysis | `api-{check_type}-{method}-{path}` |

### 3.4 Parsers (`scanners/parsers/`)

| Parser | Lines | Purpose |
|--------|-------|---------|
| `semgrep_parser.py` | ~55 | Parses Semgrep JSON → `ScannerFinding` list |
| `trivy_parser.py` | ~85 | Parses Trivy vuln + config JSON → `ScannerFinding` list |
| `gitleaks_parser.py` | ~50 | Parses Gitleaks JSON → `ScannerFinding` list (masks secrets) |
| `zap_parser.py` | ~50 | Parses ZAP JSON → `ScannerFinding` list |

### 3.5 Recommendation Engine (`scanners/recommendation.py` — ~418 lines)

`RecommendationEngine.get_recommendation(issue_key, language)` returns structured remediation:
- Language-specific templates for Python, Java, JavaScript, Go
- Generic fallback for unmapped issue keys
- Maps to CWE/OWASP via `cwe_mapping.py`
- Provides what/why/where/how_to_fix/bad_code_example/fixed_code_example

### 3.6 Bundled Semgrep Rules (`scanners/rules/semgrep/`)

4 YAML files: `python.yml`, `javascript.yml`, `java.yml`, `go.yml`
- Curated, version-controlled, offline-capable
- Covers: SQLi, command injection, unsafe deserialization, weak crypto, XXE, prototype pollution, insecure JWT, missing timeouts, weak TLS

## 4. Services Layer

### 4.1 Scanner Runner (`services/scanner.py` — 367 lines)

`ScannerRunner.run_scan(scan_id)`:
1. Loads scan with related objects
2. Clones repository (via `services/repository.py`) into tempdir
3. Delegates to `ScannerOrchestrator.run()`
4. Persists findings with dedup (`_persist_findings`)
5. Auto-resolves stale findings (`_auto_resolve_findings`)
6. Evaluates quality gate (`_evaluate_quality_gate`)
7. Updates final scan status + audit logs
8. Temp directory auto-cleaned

### 4.2 AI Recommendation (`services/ai_recommendation.py` — 111 lines)

`generate_ai_fix_suggestion(finding)`:
- Uses `apps/ai_services/providers.get_ai_provider()`
- System prompt with explicit prompt-injection defense framing
- Strict JSON schema validation (explanation, why_dangerous, fixed_code_example, framework_guidance, confidence)
- Returns `None` if provider unavailable or response invalid

### 4.3 GitHub Actions (`services/github_actions.py` — 336 lines)

- `create_github_issue(finding)` — creates GitHub issue with formatted markdown body
- `create_github_pr(finding)` — clones repo, creates branch, applies exact substring replacement of bad_code→fixed_code, pushes, opens PR via API
- Only supports github.com (validates hostname)
- Token handled via `_get_write_token()` with `del token` cleanup
- All HTTP via `urllib.request` with certifi SSL context

### 4.4 Report Generation (`services/report.py` — 263 lines, `services/report_render.py` — 67 lines)

- `generate_report(scan, report_type)` — builds comprehensive JSON blob with findings, severity counts, OWASP/CWE mapping, quality gate result
- 6 report types: security_summary, executive_summary, developer_remediation, owasp_top10, cwe_top25, quality_gate
- `render_report_html(report)` — Django template rendering
- `render_report_pdf(report)` — WeasyPrint HTML→PDF

### 4.5 Repository Service (`services/repository.py` — ~111 lines)

URL validation, normalization, provider detection, public/private access checking, safe cloning with path-traversal protection.

## 5. AI Services (`apps/ai_services/`)

### 5.1 Provider Abstraction (`providers.py` — 150 lines)

```python
class BaseAIProvider(ABC):
    @abstractmethod
    def generate(self, system_prompt: str, user_prompt: str) -> str: ...

# Implementations: OpenAIProvider, AzureOpenAIProvider, OllamaProvider, GeminiProvider, DummyProvider
# get_ai_provider() — factory from settings.AI_PROVIDER
# get_ai_providers() — fallback chain from settings.AI_PROVIDER_FALLBACKS
```

- Shared across GuideWisey products (not SecureWise-specific)
- Single synchronous `generate(system, user) → str` interface
- No streaming, no function calling, no multi-turn, no agent orchestration

## 6. Frontend Architecture

### 6.1 Stack

- React 19, TypeScript 6, Vite 8, React Router v7
- Tailwind CSS v4 (via Vite plugin)
- Axios for API calls (TanStack Query listed as dep but **unused**)
- Vitest + Testing Library for tests

### 6.2 Pages

| Page | Purpose |
|------|---------|
| `Dashboard.tsx` | Org-wide security posture summary |
| `scans/` | Scan list, detail (with live progress polling), new scan form |
| `findings/` | Finding list with filters, detail with AI suggestion panel |
| `scan-policies/` | Policy CRUD with quality gate configuration |
| `reports/` | Report list, generation, HTML/PDF download |
| `projects/` | Project CRUD |
| `repositories/` | Repository CRUD with validation and access testing |
| `integrations/` | Git integration management |
| `organizations/` | Organization management |
| `settings/` | Settings page |

### 6.3 API Client (`src/api/client.ts` — 262 lines)

- Axios instance with `withCredentials: true` (session cookie auth)
- CSRF token handling with cross-origin workaround (fetches from `/accounts/csrf/` endpoint)
- 403 retry with fresh CSRF token
- 401/403 → redirect to GuideWisey login portal
- `sw` namespace object with typed API methods for all endpoints

### 6.4 Types (`src/types/index.ts` — 368 lines)

Complete TypeScript type definitions mirroring all backend models and API responses.

### 6.5 Auth Context

Uses GuideWisey's existing session-based auth — no separate SecureWise auth system.

## 7. Test Coverage

### Backend Tests (`tests/securewise/` — 8 test files)

| File | Test Count | Coverage |
|------|-----------|----------|
| `test_api.py` | 57 | CRUD for all viewsets, action endpoints, permission checks |
| `test_services.py` | 51 | Scanner runner, finding dedup, quality gate evaluation, auto-resolve |
| `test_scanners.py` | 30 | Individual scanner engines (SAST, SCA, secrets, IaC, container, API, DAST) |
| `test_securewise.py` | 21 | Model validation, serializer behavior |
| `test_orchestrator.py` | 13 | Engine resolution, orchestration flow, dedup, correlation |
| `test_github_actions.py` | 12 | Issue creation, PR creation, error handling |
| `test_engine_progress_api.py` | 5 | Progress/engine-results endpoints |
| `test_seed_command.py` | 3 | Management command idempotency |
| **Total** | **192** | |

### Frontend Tests (`src/__tests__/` — 11 test files)

Client coverage tests, interceptor tests, page-level integration tests (ScanDetail, FindingDetail, ScanPolicies, Scans), component tests (badges, modals, states), auth context tests.

## 8. Migrations

6 migrations tracking schema evolution:
1. Initial models (Organization, Membership, Project, Repository, Scan, Finding, Report, Integration, AuditLog)
2. GitIntegration model with encrypted token
3. Finding dedup fields (first_seen_scan, last_seen_at, occurrence_count, fingerprint index)
4. ScanPolicy model with quality gate fields
5. ScanEngineResult model, scan progress/selected_engines fields
6. Finding ticket/PR fields, scan retry_of, additional scan fields (target_url, api_spec_url, docker_image)

## 9. Configuration

**Django Settings** (`guidewisey/settings.py`):
- `SECUREWISE_ENCRYPTION_KEY` — Fernet key for token encryption (falls back to SECRET_KEY-derived key in dev)
- `SECUREWISE_FRONTEND_URL` — frontend origin for CORS
- `AI_PROVIDER` / `AI_PROVIDER_FALLBACKS` — AI provider selection
- Throttle rates: `sw_repo_validate` (20/hr), `securewise_github_action` (10/hr), `securewise_ai_suggestion` (20/hr)
- No Celery/Redis/queue configuration exists

## 10. ADRs (Architecture Decision Records)

3 retroactive ADRs document key design decisions:
- **ADR-0001:** Bundled offline Semgrep rule pack (determinism + offline capability)
- **ADR-0002:** Fingerprint-based finding deduplication (per-project, not cross-project)
- **ADR-0003:** Quality gate tri-state (True/False/None, not boolean)
