# SecureWise — Technical Debt Register

> Generated: 2026-07-02 · Branch: `feature/securewise-production-scans`

---

## Critical Priority (Must fix before production)

### TD-01: Thread-per-scan execution model
- **Location:** `apps/securewise/views.py:647` (`ScanViewSet.start`), `views.py:708` (`retry`)
- **Problem:** Scans run as `threading.Thread(target=runner.run_scan, daemon=True)` inside the WSGI process. Daemon threads are killed on process restart with no crash recovery, no retry/backoff, no distributed execution, and compete with the web server for GIL/CPU/memory.
- **Risk:** A gunicorn worker restart mid-scan silently abandons the scan in "running" state forever. Under load, N concurrent scans each spinning up subprocess calls (semgrep, trivy, gitleaks, git clone) can OOM the worker process.
- **Recommendation:** Replace with Celery + Redis (or Dramatiq). The `ScannerRunner` class is already decoupled from HTTP handling — `run_scan(scan_id)` is a clean task signature.

### TD-02: No scan state recovery
- **Location:** `apps/securewise/services/scanner.py`
- **Problem:** If the process dies mid-scan, the scan remains in `running`/`queued` status forever. No health-check, no timeout watchdog, no stale-scan detector.
- **Recommendation:** Add a periodic task that marks scans stuck in running state for >N minutes as failed, and a startup hook that resets any orphaned running scans.

### TD-03: Duplicate `validate()` method on ScanSerializer
- **Location:** `apps/securewise/serializers.py:356-406`
- **Problem:** `SecureWiseScanSerializer` defines `validate()` twice. Python silently replaces the first with the second, so the first method's scan-type validation logic (lines 356-390: repository requirement for source-dependent types, DAST requires target_url, bypass_reason required for bypass) is **dead code** — it never executes.
- **Risk:** Invalid scans can be created without required fields. The validation error messages reference scan types and bypass_reason but are unreachable.
- **Fix:** Merge both validate methods into one, keeping all validation logic.

### TD-04: SQLite in production
- **Location:** `guidewisey/settings.py` — `dj-database-url` with SQLite fallback
- **Problem:** SQLite cannot handle concurrent writes from multiple gunicorn workers. If production uses the default, scans will deadlock.
- **Recommendation:** Ensure PostgreSQL is configured for all non-dev environments.

## High Priority

### TD-05: N+1 query risk in serializers
- **Location:** `apps/securewise/serializers.py` — `get_scan_count()`, `get_open_findings_count()`, `get_member_count()`, `get_finding_counts()`
- **Problem:** SerializerMethodField with `.count()` / `.values()` queries execute per-object in list views. Listing 50 projects makes 100+ extra DB queries.
- **Recommendation:** Use `annotate()` on the queryset or prefetch aggregates in the viewset.

### TD-06: Dashboard aggregation performance
- **Location:** `apps/securewise/views.py:1067-1146` (`DashboardSummaryView.get`)
- **Problem:** 10+ separate COUNT queries per request, no caching. Severity breakdown loops through 5 severities with individual queries. Will degrade as finding count grows.
- **Recommendation:** Single aggregation query with `Count(Case(When(...)))`, add short-TTL cache (30s).

### TD-07: Permission checks are inline, not declarative
- **Location:** Every `perform_create`/`perform_update`/`perform_destroy` in `views.py`
- **Problem:** Permission logic is copy-pasted across every viewset method. The DRF permission classes in `permissions.py` exist but are mostly unused — viewsets use `permission_classes = [permissions.IsAuthenticated]` and then do inline `_membership()` checks. This is error-prone and makes it hard to audit the permission matrix.
- **Recommendation:** Refactor to use proper DRF `permission_classes` with `has_object_permission`, and centralize role-checking logic.

### TD-08: Hardcoded engine registry in orchestrator
- **Location:** `apps/securewise/scanners/orchestrator.py:25-33` (`_ENGINE_CLASSES`)
- **Problem:** Adding a new scanner requires modifying a dictionary literal in the orchestrator. No plugin interface, no dynamic registration, no configuration-based loading.
- **Recommendation:** Implement plugin registry (see `PLUGIN_ARCHITECTURE.md`).

### TD-09: Synchronous report generation
- **Location:** `apps/securewise/views.py:976` (`ReportViewSet.perform_create`)
- **Problem:** Report generation (including WeasyPrint PDF rendering) runs synchronously in the HTTP request. WeasyPrint can take 5-30 seconds for complex reports.
- **Recommendation:** Move to background task, return report with `status=generating`, let client poll.

### TD-10: No pagination on many endpoints
- **Location:** `views.py` — FindingViewSet, AuditLogViewSet, DashboardSummaryView
- **Problem:** While DRF has `DEFAULT_PAGINATION_CLASS` in settings, some computed/custom endpoints return unbounded querysets.
- **Recommendation:** Ensure cursor/page pagination is enforced on all list endpoints.

## Medium Priority

### TD-11: `urllib.request` instead of `requests` library
- **Location:** `apps/securewise/views.py:234-304` (GitIntegration test), `apps/securewise/services/github_actions.py:70-113`
- **Problem:** Uses raw `urllib.request` with manual SSL context setup. The rest of the codebase uses `requests`. Duplicated SSL/error handling code.
- **Recommendation:** Consolidate on `requests` with a shared session that has certifi CA bundle configured.

### TD-12: Token cleanup relies on `del` statements
- **Location:** `services/github_actions.py:237,267-273,313-314,328-329`, `services/scanner.py` (via repository.py), `views.py:304`
- **Problem:** `del token` in Python doesn't guarantee immediate memory zeroing — the string may remain in memory until garbage collected. In a long-running process, token material could persist.
- **Recommendation:** While `del` is reasonable defense-in-depth, note this is not cryptographic erasure. Consider `ctypes` memory zeroing for high-security environments.

### TD-13: PR creation uses naive string replacement
- **Location:** `apps/securewise/services/github_actions.py:297`
- **Problem:** `original_content.replace(bad_code, finding.fixed_code_example, 1)` does exact substring matching. If the code has been reformatted, the replacement fails. No AST-aware or fuzzy diffing.
- **Recommendation:** Document limitation clearly; long-term, use tree-sitter or similar for AST-aware patching.

### TD-14: SAST regex fallback has limited coverage
- **Location:** `apps/securewise/scanners/sast.py:42-73`
- **Problem:** Only 6 regex rules + hardcoded secrets + weak hash detection. Significant false negative risk compared to Semgrep.
- **Recommendation:** Continue expanding bundled Semgrep rules; consider deprecating regex fallback once Semgrep is a hard requirement.

### TD-15: SCA known-vuln list is minimal
- **Location:** `apps/securewise/scanners/sca.py:23-29`
- **Problem:** Only 5 packages with hardcoded CVE ranges. No live vulnerability database integration (OSV, NVD, GitHub Advisory).
- **Recommendation:** Integrate OSV.dev API with timeout fallback; keep static list as offline fallback.

### TD-16: DAST scanner doesn't invoke ZAP even when available
- **Location:** `apps/securewise/scanners/dast.py:47-51`
- **Problem:** ZAP baseline is detected but explicitly not invoked. DAST is passive-only HTTP header/cookie checks.
- **Recommendation:** Add ZAP integration with configurable time limit; keep passive scan as minimal fallback.

### TD-17: No API versioning
- **Location:** `apps/securewise/urls.py`
- **Problem:** All endpoints are under `/api/securewise/` with no version prefix. Breaking changes will affect all clients simultaneously.
- **Recommendation:** Add `/api/v1/securewise/` prefix before public API launch.

### TD-18: Audit log has hardcoded event choices but usage drifts
- **Location:** `apps/securewise/models.py:146-169` vs `views.py:700,820-828`
- **Problem:** `AUDIT_EVENT_CHOICES` doesn't include all events actually created (e.g. `scan_retried`, `ai_suggestion_generated`, `finding_auto_resolved`, `finding_reopened`). Django won't enforce the choices list on JSONField-adjacent string fields, but it's a documentation/validation mismatch.
- **Recommendation:** Add missing event types to choices, or switch to a non-choices string field with a documented event catalog.

## Low Priority

### TD-19: `DummyProvider` returns resume-optimization JSON
- **Location:** `apps/ai_services/providers.py:97-112`
- **Problem:** The dummy AI provider returns career/resume-related JSON, not security-related content. It's the GuideWisey career tool's dummy, not a SecureWise-appropriate mock.
- **Recommendation:** Add a SecureWise-specific dummy that returns plausible fix suggestion JSON matching the expected schema.

### TD-20: Frontend has TanStack Query as dependency but doesn't use it
- **Location:** `securewise-frontend/package.json`
- **Problem:** `@tanstack/react-query` is listed as a dependency but all data fetching uses plain Axios with `useEffect`. This means no query caching, deduplication, or automatic revalidation.
- **Recommendation:** Either adopt TanStack Query for all data fetching or remove the unused dependency.

### TD-21: No structured logging
- **Location:** All Python modules use `logging.getLogger(__name__)` with default formatting
- **Problem:** Production deployments need structured JSON logging for log aggregation services.
- **Recommendation:** Add `python-json-logger` or similar structured logging formatter.

### TD-22: No database index on Finding.project + Finding.status
- **Location:** `apps/securewise/models.py:601`
- **Problem:** Quality gate evaluation and dashboard queries filter on `(project, status)` combination. Only `fingerprint` has an explicit `db_index`.
- **Recommendation:** Add composite index on `(project_id, status)` and `(project_id, scanner_type, status)`.

### TD-23: Services directory has `repository.py` alongside `scanners/repository.py`
- **Location:** `apps/securewise/services/repository.py` vs `apps/securewise/scanners/repository.py`
- **Problem:** URL validation/normalization is in `services/repository.py`, cloning is in `scanners/repository.py`. Import paths are confusing (`from .services.repository import ...` vs `from .scanners.repository import ...`).
- **Recommendation:** Consolidate into a single module or clearly delineate the boundary.

### TD-24: No rate limiting on scan start/retry
- **Location:** `apps/securewise/views.py:633-711`
- **Problem:** `start` and `retry` actions have no throttling. A user could trigger hundreds of concurrent scans, each spawning threads + subprocess calls.
- **Recommendation:** Add per-user throttle on scan start (e.g., 5/minute) and per-org concurrency limit.

### TD-25: GitLab token header leak in test endpoint
- **Location:** `apps/securewise/views.py:259`
- **Problem:** `headers["Authorization"] = f"******"` — this is a masked placeholder string, not a real GitLab Private-Token header. GitLab integration test will always fail.
- **Recommendation:** Use `headers["PRIVATE-TOKEN"] = token` for GitLab provider.
