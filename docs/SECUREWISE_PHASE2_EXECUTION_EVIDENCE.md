# SecureWise Phase 2 execution evidence

**Run date:** 2026-10-10  
**Environment:** macOS, Docker Desktop `desktop-linux` 29.2.0  
**Fixture:** `tests/fixtures/securewise-autopentest-api/` (local controlled API)  
**Test:** `SECUREWISE_RUN_DOCKER_INTEGRATION=1 ./venv/bin/python -m pytest tests/securewise/test_docker_integration.py -s -q`
**Test scan ID:** `72615bb2-d79c-48da-8f04-4a27397602a7`

The opt-in integration test queued a SecureWise scan and processed it through
the existing `process_next_job()` worker entry point. It used the Docker daemon
to build and start the fixture, checked `/health` from the isolated container
network, scanned the runtime-built image with Trivy, and ran digest-pinned
OWASP ZAP baseline against the running fixture.

| Check | Observed result |
|---|---|
| Scan status | `completed` |
| Trivy | `completed`, real tool, runtime-built image reused, 268 findings |
| OWASP ZAP | `completed`, `zap_baseline`, Docker baseline runner, 1 finding |
| Persisted findings | 275 across all completed engines |
| Temporary runtime container removed | Yes |
| Temporary runtime image removed | Yes |
| Test result | 1 passed |

ZAP ran `ghcr.io/zaproxy/zaproxy@sha256:7aaa659b0d43078febd82e29bad112285c370727e86ab8340444220e17d9f0d2`.
The dedicated worker image (`securewise-worker-validation:local`) also built
successfully with Docker CLI 27.5.1 and Trivy 0.72.0.
When explicitly mounted into that worker image, `/var/run/docker.sock` returned
Docker daemon version 29.2.0 and both scanner executables were present.

**Evidence limits:** The scan used Docker Desktop and the worker's existing
database-backed job-processing function invoked by pytest; it did not run
through a separately deployed Compose worker service or a dedicated Linux
worker. Test database contents are rolled back when pytest exits. This is local
fixture evidence only—not production verification, a deployment certification,
or proof that arbitrary customer repositories are safely sandboxed.
