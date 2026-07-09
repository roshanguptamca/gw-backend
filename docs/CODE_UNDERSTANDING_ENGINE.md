# CodeUnderstandingEngine — Design

## Purpose

Given a cloned repository (already fetched by the existing `services/repository.py` clone step used by
`ScannerRunner`), inspect it and produce a structured `ApplicationRunPlan` describing how to build, run, and
safely test the application. This is the foundational new service that everything in the runtime/dynamic
layer depends on (`DockerizationEngine`, `RuntimeEnvironmentManager`, `FullScanOrchestrator`).

This is a **new module**: `apps/securewise/services/code_understanding.py`, invoked by the orchestrator
before any dockerization/runtime step, reusing the tempdir clone already produced by
`services/scanner.py::ScannerRunner` (no second clone).

## Detection strategy (deterministic first, AI-assisted second)

Detection should be layered:

1. **Deterministic file-signature detection** (fast, free, no LLM call) — look for well-known marker files:
   - `manage.py` + `requirements.txt`/`pyproject.toml` → Django
   - `main.py` + `fastapi` in deps → FastAPI
   - `package.json` → inspect `dependencies`/`scripts` for `react`, `next`, `express`, `vue`
   - `pom.xml`/`build.gradle` → Java/Spring Boot
   - `go.mod` → Go
   - `composer.json` → PHP/Laravel
   - `Gemfile` → Ruby/Rails
2. **AI-assisted fallback** for ambiguous/monorepo/uncommon stacks — feed the LLM a directory listing + key
   file excerpts (package manifests, entrypoint files) and ask for structured JSON matching `ApplicationRunPlan`.
   This reuses the existing OpenAI/Gemini provider abstraction already used by `services/ai_recommendation.py`
   (`get_ai_provider()`), so no new AI plumbing is required — just a new prompt/schema.
3. Detected values from step 1 always take priority over AI guesses (deterministic overrides AI); AI only
   fills gaps (e.g., start command flags, required env vars) or handles unrecognized stacks.

## What it must detect

| Signal | How |
|---|---|
| Language(s) | File extension histogram + manifest files |
| Framework(s) | Manifest dependency inspection (`package.json`, `requirements.txt`, `pyproject.toml`, `pom.xml`, `go.mod`, `Gemfile`, `composer.json`) |
| Package manager | Lockfile presence (`package-lock.json`→npm, `yarn.lock`→yarn, `pnpm-lock.yaml`→pnpm, `poetry.lock`→poetry, `Pipfile.lock`→pipenv) |
| Build command | Framework convention + `package.json` `scripts.build`, or AI-inferred |
| Test command | `package.json` `scripts.test`, `pytest.ini`/`tox.ini` presence, `Makefile` targets |
| Start command | Framework convention (`manage.py runserver`, `npm start`, `java -jar`) or `Procfile`/`docker-compose.yml` command directive |
| Ports | `EXPOSE` in existing Dockerfile, framework default (Django 8000, Next 3000, Spring 8080), or `.env`/`settings.py` scan |
| Dockerfile presence | Direct file check |
| docker-compose presence | Direct file check (`docker-compose.yml`, `compose.yaml`) |
| Environment variables required | Parse `.env.example`, `settings.py`/`config.py` `os.environ.get(...)` calls, `docker-compose.yml` `environment:` block |
| Database dependency | Manifest deps (`psycopg2`, `pymongo`, `mysqlclient`) + `docker-compose.yml` service names |
| External services | `docker-compose.yml` service list, deps like `redis`, `celery`, `boto3` |
| OpenAPI/Swagger files | Search for `openapi.yaml`/`swagger.json`/`drf-spectacular`/`drf-yasg` config, or a live `/api/schema/` route convention |
| Frontend/backend structure | Monorepo heuristics: `frontend/`+`backend/` dirs, or separate repos referenced |
| Authentication flow | Grep for `django.contrib.auth`, `passport`, `next-auth`, `spring-security`, JWT libs |
| Sensitive endpoints | Route file grep for `admin`, `internal`, `debug`, `actuator`, `.env` exposure risk |
| Admin endpoints | Django admin URL conventions, Spring Actuator, Rails `ActiveAdmin` |

## Output model: `ApplicationRunPlan`

New Django model (or, if preferred for a first pass, a `JSONField` on `SecureWiseScan` — recommend a real
model for queryability and reuse across re-scans of the same repo):

```python
class SecureWiseApplicationRunPlan(models.Model):
    scan = models.OneToOneField(SecureWiseScan, on_delete=models.CASCADE, related_name="run_plan")
    detected_languages = models.JSONField(default=list)       # ["python", "javascript"]
    detected_frameworks = models.JSONField(default=list)      # ["django", "react"]
    package_manager = models.CharField(max_length=40, blank=True)   # "poetry" | "npm" | ...
    build_steps = models.JSONField(default=list)              # ["pip install -r requirements.txt", "npm run build"]
    start_command = models.CharField(max_length=500, blank=True)
    test_command = models.CharField(max_length=500, blank=True)
    required_env_vars = models.JSONField(default=list)        # ["DATABASE_URL", "SECRET_KEY"]
    exposed_ports = models.JSONField(default=list)             # [8000, 5432]
    docker_strategy = models.CharField(
        max_length=20,
        choices=[("existing_dockerfile", "existing_dockerfile"),
                 ("existing_compose", "existing_compose"),
                 ("generated", "generated"),
                 ("unsupported", "unsupported")],
    )
    health_check_url = models.CharField(max_length=500, blank=True)  # "/health" or "/"
    api_specs = models.JSONField(default=list)                 # discovered OpenAPI file paths / URLs
    auth_flows = models.JSONField(default=dict)                # {"type": "session"|"jwt"|"oauth", "login_endpoint": "..."}
    risk_notes = models.JSONField(default=list)                # ["Uses SQLite - no real DB isolation risk", ...]
    detection_method = models.CharField(max_length=20, choices=[("deterministic", "deterministic"), ("ai_assisted", "ai_assisted")])
    confidence = models.CharField(max_length=10, choices=[("low", "low"), ("medium", "medium"), ("high", "high")])
    created_at = models.DateTimeField(auto_now_add=True)
```

## User-facing "scan plan preview"

Before a Full Scan proceeds to dockerization/runtime, the `ApplicationRunPlan` is returned to the frontend as
a **preview the user must confirm** (per the target UX flow in `UX_GAP_ANALYSIS.md`). This is also where the
authorization gate lives: if `risk_notes` includes "external target URL provided" the UI must show the
authorization checkbox described in `TARGET_ARCHITECTURE.md` §4.

## Failure modes & honesty rules

- If detection confidence is `low` or `docker_strategy == "unsupported"`, the orchestrator must **skip** the
  dockerization/runtime/dynamic-testing phases entirely and clearly report "Runtime testing skipped: could
  not confidently determine how to build/run this application" rather than guessing and silently failing
  later (consistent with the "no fake completed" principle in `IMPLEMENTATION_ROADMAP.md` Phase 1).
- All detection results are stored so re-scans don't need to re-detect from scratch (cache keyed by
  repository + commit SHA), though the user can force redetection if they change the repo's build setup.
