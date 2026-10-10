# SecureWise Phase 3 execution evidence

**Environment:** Local Docker Engine/Desktop and the controlled fixture under
`tests/fixtures/securewise-autopentest-api/`
**Test:** `SECUREWISE_RUN_DOCKER_INTEGRATION=1 ./venv/bin/python -m pytest tests/securewise/test_autopentest_worker.py::test_authenticated_api_scans_real_isolated_fixture_and_cleans_up -s -q`
**Result:** 1 passed

The test submitted an authenticated AutoPentest session through the Django API,
verified that credentials were not included in the response, registered the
worker capability, and passed the queued session through the existing
`process_next_job()` queue entry point. The worker built and started the
allowlisted fixture in its isolated Docker network. Separate short-lived
resource-limited containers sent the real read-only API requests. The test
asserted the authorization outcomes, unified finding persistence, and cleanup.

Sanitized test output:

```json
{
  "api_engine_status": "completed",
  "api_request_containers_cleaned": true,
  "confirmed_authorization_cases": 1,
  "passed_authorization_cases": 3,
  "persisted_findings": 1,
  "runtime_container_cleaned": true,
  "runtime_image_cleaned": true,
  "runtime_network_cleaned": true,
  "session_id": "6d76fd8b-5637-4c12-bf5d-a9dba7091781",
  "session_status": "completed",
  "unified_scan_id": "63c0d873-81c4-476b-9131-0d11b64889a1"
}
```

The confirmed `CWE-639` finding was based on a successful cross-user response
containing the deliberate fixture's protected `ownerId` and invoice record.
The API test also observed three passing authorization controls. Evidence
stores the request method, endpoint, synthetic identity label, response status,
and sanitized response body; bearer credentials are not included.

**Important limitations:** The queue entry point ran synchronously inside
pytest. This verifies API enqueueing, queue claiming, real Docker runtime and
API execution, but does **not** verify a separately running
`python manage.py securewise_worker` process or a Compose worker service.
The test database is rolled back after pytest. Production execution and
deployment remain unverified. This vertical slice exercises only documented
GET/HEAD routes in the controlled fixture; it does not include Playwright,
session-expiration testing, general request-body generation, or third-party
targets.
