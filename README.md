# GuideWisey Backend

Production-ready Django REST Framework API powering the GuideWisey platform — featuring AI document intelligence (Doc-X), scheduled future message delivery (FutureWise), AI insurance policy analysis (Insurance Explainer), and session-based authentication.

- **Live API:** https://gw-backend-eq2n.onrender.com/api
- **Swagger UI:** https://gw-backend-eq2n.onrender.com/api/docs/
- **ReDoc:** https://gw-backend-eq2n.onrender.com/api/redoc/

---

## Stack

| Layer | Technology |
|---|---|
| Framework | Django 5.x + Django REST Framework 3.15 |
| Auth | Session cookies + CSRF tokens |
| AI | Google Gemini 2.5 Flash |
| File Storage | DB (local dev) or AWS S3 (production) — switchable via `FILE_STORAGE_BACKEND` |
| DB | PostgreSQL (production) / SQLite (local dev — zero setup) |
| Schema | drf-spectacular 0.27 (OpenAPI 3.0) |
| Email | Django SMTP backend via Brevo SMTP relay |
| Scheduler | APScheduler + Django ORM (no Redis required) |
| Deployment | Render.com |

---

## Apps

### `accounts`
User registration, login, logout, session check, current user profile.

### `doc_x`
AI-powered document intelligence.
- **V1** — paste text → AI summary + follow-up Q&A (3 questions/doc)
- **V2** — upload file (PDF/DOCX/TXT/CSV) → DB or S3 → extract text → Gemini AI → poll status → chat

### `future_wise`
Schedule a message to be delivered at a future date.
- Anonymous users get email verification flow
- Authenticated users get immediate scheduling
- Supports attachments, tier-based limits (free / premium)
- Background delivery via APScheduler (DB-backed, no Redis)

### `insurance_explainer`
AI-powered insurance policy analysis.
- Submit policy text or upload file (PDF/DOCX/TXT)
- Country-aware analysis (NL, DE, FR, UK, US, and more)
- Multi-language responses (10 languages)
- Structured output: coverage highlights, important clauses, missing coverage, risks, action items, overall score
- Follow-up chat with full context

### `speaking_buddy`
AI voice-practice sessions with OpenAI Realtime audio, selectable 3D avatars, consent-based photo-inspired avatars, transcripts, history, vocabulary, mistakes, and account-scoped learning memory.
The app enforces a free quota of 100 completed conversations per authenticated user account through `BuddyUsageQuota` and `/api/buddy/usage/`. New sessions are blocked after the limit is reached, but the user can still review history and memory.

### Career Suite
Self-hosted resume building, parsing, ATS analysis, job matching, AI optimization, and PDF/DOCX export.

Resume generation uses an explicit template flow. New and imported resumes start without a template; clients list `/api/resume-templates/`, save a choice through `/api/resumes/{id}/select-template/`, and request `/api/resumes/{id}/preview/` before export. PDF and DOCX export reject resumes without a selected template.

Resume Builder is also available as a live beta for anonymous users. Anonymous visitors can create one resume, make up to ten edits, and claim that resume after signing in. Anonymous ownership is resolved through a minimal identity record using IP address, email, phone number, and session data. The claim flow is exposed at `/api/resumes/my-anonymous/` and `/api/resumes/claim-anonymous/`.

- Apps: `resumes`, `jobs`, `ai_services`, `exports`, `uploads`, `files`, `templates_app`
- Storage: PostgreSQL/SQLite binary fields only; no cloud storage
- Jobs: existing DB-backed APScheduler process; no Redis or Celery
- AI providers: OpenAI, Azure OpenAI, Ollama, or deterministic dummy provider
- Speaking Buddy: OpenAI-backed realtime/text practice with isolated buddy memory and avatar support
- Export: WeasyPrint PDF and `python-docx` DOCX
- Optional protected profile photos (JPG/PNG/WebP, maximum 5 MB)
- Stable-ID CRUD for skills, education, experience, projects, certifications, languages, awards, and references
- Honest target-score optimization using only existing facts and explicitly confirmed skills/evidence
- Independent English/Dutch resume, report, optimization, preview, and export languages
- Cross-language English/Dutch skill matching and localized ATS recommendations
- Access: every resume, upload, match, optimization, and download is owner-scoped
- Access: anonymous beta users can create one resume and make ten edits before claiming it into an account; logged-in users can create up to three resumes

Detailed language contract: [`CAREER_SUITE_I18N.md`](CAREER_SUITE_I18N.md).

---

## API Reference

All endpoints are documented interactively at `/api/docs/`.

### Accounts

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/api/accounts/csrf/` | Public | Get CSRF token |
| POST | `/api/accounts/register/` | Public | Register new user |
| POST | `/api/accounts/login/` | Public | Login |
| POST | `/api/accounts/logout/` | Required | Logout |
| GET | `/api/accounts/me/` | Required | Current user profile |
| GET | `/api/accounts/session/` | Public | Check session status |

### Doc-X V1

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/api/doc-x/process-text/` | Required | Summarise pasted text with Gemini |
| POST | `/api/doc-x/ask/` | Required | Ask follow-up question |
| GET | `/api/doc-x/ask/remaining/` | Required | Remaining question count |

### Doc-X V2

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/api/doc-x/documents/upload` | Required | Upload file (DB or S3) |
| GET | `/api/doc-x/documents` | Required | List all documents |
| GET | `/api/doc-x/documents/{id}` | Required | Get document details |
| DELETE | `/api/doc-x/documents/{id}/delete` | Required | Delete document |
| POST | `/api/doc-x/documents/{id}/process` | Required | Process with Gemini AI |
| GET | `/api/doc-x/documents/{id}/status` | Required | Poll processing status |
| POST | `/api/doc-x/documents/{id}/chat` | Required | Chat with document |
| GET | `/api/doc-x/documents/{id}/messages` | Required | Chat history |

### FutureWise

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/api/future-wise/reminders/` | Public | Create reminder |
| GET | `/api/future-wise/reminders/` | Required | List own reminders |
| GET | `/api/future-wise/reminders/{id}/` | Required | Get reminder |
| DELETE | `/api/future-wise/reminders/{id}/` | Required | Cancel reminder |
| GET | `/api/future-wise/reminders/verify/{token}/` | Public | Verify email token |

### Insurance Explainer

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/api/insurance/sessions/` | Required | Analyse policy (text or file upload) |
| GET | `/api/insurance/sessions/` | Required | List sessions |
| GET | `/api/insurance/sessions/{id}/` | Required | Get session + full analysis |
| DELETE | `/api/insurance/sessions/{id}/` | Required | Delete session |
| POST | `/api/insurance/sessions/{id}/chat/` | Required | Ask follow-up question |
| GET | `/api/insurance/sessions/{id}/messages/` | Required | Chat history |

---

## Local Development

### Prerequisites
- Python 3.13+
- Gemini API key (optional — AI features disabled without it)
- No other external dependencies required

### Setup

```bash
git clone https://github.com/roshanguptamca/gw-backend.git
cd gw-backend

python3 -m venv .venv
source .venv/bin/activate          # macOS/Linux
# .venv\Scripts\activate           # Windows

pip install -r requirements.txt
```

### Environment Variables

Create a `.env` file in the project root:

```env
ENV=DEV
SECRET_KEY=your-secret-key-here

# Database — leave blank to use SQLite (no setup required)
DB_ENGINE=
DB_NAME=
DB_USER=
DB_PASSWORD=
DB_HOST=
DB_PORT=

# Google Gemini AI
GEMINI_API_KEY=

# Career Suite AI (dummy requires no external service)
AI_PROVIDER=dummy
AI_MODEL=gpt-4o-mini
OPENAI_API_KEY=
AZURE_OPENAI_API_KEY=
AZURE_OPENAI_ENDPOINT=
AZURE_OPENAI_API_VERSION=2024-10-21
OLLAMA_BASE_URL=http://localhost:11434
CAREER_SUITE_TEMP_TTL_HOURS=24
CAREER_SUITE_RUN_JOBS_INLINE=true

# File storage: "db" (default, no S3 needed) | "s3" | "auto"
FILE_STORAGE_BACKEND=db

# AWS S3 — leave blank when using db storage
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_REGION=eu-west-1
S3_BUCKET=

# CORS / Auth
CORS_ALLOWED_ORIGINS=http://localhost:3000
ALLOWED_HOSTS=127.0.0.1,localhost

# Social auth / OAuth
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
OAUTH_REDIRECT_BASE_URL=http://localhost:8000
FRONTEND_AUTH_SUCCESS_URL=https://www.guidewisey.com/auth-callback?status=success
FRONTEND_AUTH_ERROR_URL=https://www.guidewisey.com/auth-callback?error=

# Speaking Buddy
OPENAI_API_KEY=
SPEAKING_BUDDY_MODEL=gpt-4o-mini
SPEAKING_BUDDY_REALTIME_MODEL=gpt-realtime-2
SPEAKING_BUDDY_MAX_AVATAR_BYTES=5242880
AVATAR_GENERATION_PROVIDER=template
ENABLE_EXPERIMENTAL_IMAGE_TO_3D=false
IMAGE_TO_3D_PROVIDER=template

# Email — Brevo SMTP relay
EMAIL_HOST=smtp-relay.brevo.com
EMAIL_PORT=587
EMAIL_USE_TLS=true
EMAIL_HOST_USER=ac98f2001@smtp-brevo.com
EMAIL_HOST_PASSWORD=          # leave blank → prints to console in DEV
EMAIL_SENDER_EMAIL=noreply@guidewisey.com
EMAIL_SENDER_NAME=FutureWise by GuideWisey
FUTUREWAVE_FRONTEND_BASE_URL=http://localhost:3000
```

> **Zero dependencies locally:** SQLite is used when DB vars are blank. Email prints to the console when `EMAIL_HOST_PASSWORD` is not set.

#### Marketplace checkout emails (account verification + order notifications)

The marketplace checkout endpoint (`POST /api/marketplace/orders/`) reuses the
same email machinery as the rest of the app — no separate config needed:

- **Account verification** (when a guest checks "Create an account to track
  my order" and submits a password): sent via
  `apps.future_wise.email_service.BrevoEmailService.send_account_confirmation_email`,
  the exact same flow as `/api/accounts/register/`.
- **Buyer order confirmation** and **seller new-order notification**: sent via
  `django.core.mail.send_mail` from `apps/marketplace/services.py`, dispatched
  in a background thread so the HTTP response returns immediately. A failure
  sending either email is logged and does **not** fail the order.

Every buyer/seller order email attempt is recorded in the `OrderEmailLog`
model (Django admin: **Marketplace → Order email logs**), with `email_type`,
`recipient`, `status` (`pending`/`sent`/`failed`), `error_message`, and
`sent_at` — so support can see exactly what was attempted and why it failed,
instead of relying only on server logs. `Order.buyer_email_sent_at` and
`Order.seller_email_sent_at` are updated the moment each email succeeds, so
the order list/detail views also show at a glance whether emails went out.

Locally, with `EMAIL_HOST_PASSWORD` and `BREVO_API_KEY` unset, `EMAIL_BACKEND`
falls back to `django.core.mail.backends.console.EmailBackend`, so all three
emails (verification, buyer confirmation, seller notification) print straight
to the `runserver` terminal — no SMTP setup required to see them while
testing checkout locally. Set `EMAIL_HOST_PASSWORD` (Brevo SMTP) or
`BREVO_API_KEY` (Brevo HTTP API) to send real emails instead.

### Twilio WhatsApp Sandbox

To test WhatsApp reminders with a Twilio trial account:

1. Open the Twilio Console → **Messaging** → **Try it out** → **Send a WhatsApp message** / **Sandbox**.
2. Copy the sandbox number and join phrase shown there.
3. From the recipient phone, send the `join xxxx` phrase to the sandbox number in WhatsApp.
4. Add these vars to `.env`, then restart the backend:

```bash
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_twilio_auth_token
TWILIO_WHATSAPP_NUMBER=+14155238886
TWILIO_WHATSAPP_FROM=+14155238886   # defaults to TWILIO_WHATSAPP_NUMBER
TWILIO_WHATSAPP_ENABLED=true
```

Template-based sends can also use Twilio Content API:

```bash
TWILIO_WHATSAPP_CONTENT_SID=HXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_WHATSAPP_USE_TEMPLATE=true
```

If `TWILIO_WHATSAPP_USE_TEMPLATE=true`, the provider falls back to `TWILIO_WHATSAPP_CONTENT_SID` when a reminder/context-specific `content_sid` is not supplied.

### Run

```bash
# Terminal 1 — API server
python manage.py migrate
python manage.py runserver 8000

# Terminal 2 — Background scheduler (reminder delivery, no Redis)
python manage.py runapscheduler
```

The default avatar provider uses local templates and does not require experimental image-to-3D models. Keep `OPENAI_API_KEY` in `.env`; never commit a real key.

| URL | Description |
|---|---|
| http://localhost:8000/api | REST API |
| http://localhost:8000/api/docs/ | Swagger UI |
| http://localhost:8000/admin/ | Django Admin |

### Validate OpenAPI Schema

```bash
python manage.py spectacular --validate --fail-on-warn
# → 0 errors, 0 warnings ✅
```

### Run Tests

```bash
make test          # all tests, verbose
make test-cov      # with HTML coverage report
make test-fast     # quiet

# Speaking Buddy validation
python manage.py makemigrations --check
python manage.py migrate --check
python manage.py showmigrations speaking_buddy
python manage.py test tests.speaking_buddy
black --check .
isort --check-only .
flake8
```

---

## File Storage

Controlled by `FILE_STORAGE_BACKEND` in `.env`:

| Value | Behaviour |
|---|---|
| `db` | Store file bytes in the Django database — **default for local dev** |
| `s3` | Store in AWS S3 |
| `auto` | Use S3 if all 4 AWS credentials are present, else DB |

Career Suite uploads and generated exports always use database storage and never use S3.

---

## Career Suite API

The main endpoints are:

```text
POST/GET        /api/resumes/
GET/PUT/DELETE  /api/resumes/{id}/
PUT             /api/resumes/{id}/personal/
PUT             /api/resumes/{id}/summary/
POST            /api/resumes/{id}/{experiences|education|projects|skills|certifications|languages}/
PUT/DELETE      /api/{section}/{item_id}/
POST            /api/resumes/{id}/photo/upload/
GET/DELETE      /api/resumes/{id}/photo/
GET             /api/resume-templates/
GET             /api/resume-templates/{id}/
POST            /api/resumes/{id}/select-template/
POST            /api/resumes/{id}/preview/
GET             /api/autocomplete/{skills|job-titles|companies|schools|degrees|locations}/?q=...
POST            /api/resumes/upload/
POST            /api/resumes/parse/
POST            /api/jobs/parse-text/
POST            /api/jobs/parse-url/
POST            /api/job-match/analyze/
POST            /api/job-match/{id}/optimize/
POST            /api/resumes/{id}/export/{pdf|docx}/
GET             /api/files/download/{file_id}/
```

Run the DB-backed scheduler in a second process:

```bash
python manage.py runapscheduler
```

---

## Doc-X V2 Flow

```
Frontend
  │
  │ 1. POST /documents/upload   (multipart/form-data)
  ▼
Storage (DB or S3)
  │
  │ 2. POST /documents/{id}/process
  ▼
Gemini AI  (extract text → summarise → chunk)
  │
  │ 3. GET /documents/{id}/status  (poll until "completed")
  │
  │ 4. POST /documents/{id}/chat   (Q&A with full history)
  ▼
Frontend
```

---

## Deployment on Render

A `render.yaml` is included for one-click infrastructure-as-code deployment.

It defines:
- **`gw-backend`** — web service (Gunicorn)
- **`gw-scheduler`** — worker service (`python manage.py runapscheduler`)
- **`gw-db`** — managed PostgreSQL

```bash
# Deploy via Render dashboard → New → Blueprint
# Point to this repo — render.yaml is picked up automatically
```

Set these secret env vars in the Render dashboard after deploy:
- `GEMINI_API_KEY`
- `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD`
- `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `S3_BUCKET` (if using S3)

---

## Project Structure

```
gw-backend/
├── apps/
│   ├── accounts/          # Auth: register, login, logout, session
│   ├── doc_x/
│   │   ├── views.py       # V1: process-text, ask
│   │   ├── views_v2.py    # V2: upload, process, status, chat
│   │   ├── extract.py     # PDF/DOCX/TXT/CSV text extraction
│   │   └── services/      # document_service, processing_service, chat_service
│   └── future_wise/
│       ├── tasks.py       # APScheduler job functions (no Celery)
│       ├── email_service.py  # Django SMTP backend wrapper
│       ├── storage.py     # DB/S3 attachment storage
│       └── management/commands/runapscheduler.py
├── guidewisey/
│   ├── settings.py
│   ├── urls.py            # /api/schema/, /api/docs/, /api/redoc/
│   └── email_backend.py  # CertifiSMTPEmailBackend (macOS SSL fix)
├── services/
│   ├── gemini.py          # Google Gemini API client
│   └── file_storage.py    # DB/S3 storage abstraction for doc_x
├── tests/                 # pytest test suite
├── render.yaml            # Render.com IaC deployment
├── Makefile
├── entrypoint.sh          # Docker/Render startup script
├── Dockerfile
└── .env                   # Local dev config (not committed)
```

---

## Docker

```bash
docker-compose up --build
```

Exposes port `8000`. Set all required env vars in `.env`.

---

## Testing

```bash
make test           # pytest verbose
make test-cov       # with coverage HTML report in htmlcov/
make test-parallel  # parallel with pytest-xdist
```

---

## SecureWise (Security Application Scanning Platform)

> **📐 Architecture & Roadmap:** Comprehensive architecture review, gap analysis, roadmap,
> and design documents are available in [`docs/architecture/`](docs/architecture/). Start with
> [`ARCHITECTURE_REVIEW.md`](docs/architecture/ARCHITECTURE_REVIEW.md) for the executive
> summary, or [`CURRENT_STATE.md`](docs/architecture/CURRENT_STATE.md) for a detailed as-built
> reference of every module.

SecureWise (`apps/securewise/`) is a multi-tenant security scanning platform: organizations
connect git repositories (public or private, via encrypted `SecureWiseGitIntegration` tokens),
configure scan policies/quality gates, and run scans that produce `SecureWiseFinding` records
with CWE/OWASP mapping and actionable remediation guidance.

### Scanner architecture

Each scan resolves to a list of **engines** (`apps/securewise/scanners/orchestrator.py`,
`ScannerOrchestrator.resolve_engines`). For a single-type scan (`sast`, `sca`, `secrets`,
`iac`, `container`, `api`, `dast`) only that engine runs. For `scan_type="full"`, the engines
`sast`, `sca`, `secrets`, `iac` always run, and `container` / `api` / `dast` are added only
when there is something real to scan (a `docker_image`/Dockerfile, an OpenAPI/Swagger spec,
or a `target_url`, respectively).

Every engine implements `BaseScanner` (`apps/securewise/scanners/base.py`) and, where a real
security tool is available on `PATH` (checked via `shutil.which`), shells out to it and parses
its native output (`apps/securewise/scanners/parsers/`). When the real tool is **not**
installed, a lightweight but genuinely functional fallback engine performs an equivalent
static check directly in Python. Every engine records which mode it used in
`SecureWiseScanEngineResult.raw_summary["tool"]` / `raw_tool`, so reports are always honest
about fidelity.

| Engine     | Real tool         | Available in this environment? | Fallback engine when tool is absent |
|------------|--------------------|:---:|--------------------------------------|
| `secrets`  | gitleaks           | ✅ Yes | regex fallback (AWS keys, private key blocks, Slack/JWT tokens) |
| `sast`     | semgrep            | ✅ Yes | regex/heuristic rules (eval/exec, unsafe pickle/yaml, shell=True, hardcoded secrets, DEBUG=True, weak hashing in auth code) |
| `sca`      | trivy              | ✅ Yes | lockfile parser (requirements.txt, package.json, go.mod, Gemfile.lock, …) + curated known-CVE list |
| `iac`      | trivy              | ✅ Yes | Dockerfile / Kubernetes YAML / Terraform / Helm static checks |
| `container`| trivy (image scan) | ✅ Yes | skipped unless a `docker_image` is configured (optional best-effort `docker build` + `trivy image` if both binaries exist) |
| `api`      | n/a (spec parsing) | — | always uses built-in OpenAPI/Swagger parser (json/yaml) |
| `dast`     | OWASP ZAP          | ❌ No  | passive `requests`-based header/cookie/CORS/disclosure checks only — **no active/destructive scanning** |

Install the real tools to upgrade fidelity (all except ZAP are already installed in this environment):

```bash
brew install gitleaks   # already installed in this environment
brew install trivy      # already installed in this environment
pip install semgrep     # already installed in the project venv
docker pull zaproxy/zap-stable   # ZAP via Docker; zap-baseline.py path is auto-detected if present
```

**SAST determinism note:** `semgrep` is run with a curated, offline rule pack bundled at
`apps/securewise/scanners/rules/semgrep/` instead of `--config=auto`, which depends on a live
call to the Semgrep registry and made scans slow (60–140s) and non-deterministic across
environments/network conditions. The bundled rules cover the most common vulnerability classes
per language (SQLi, command injection, unsafe deserialization, weak crypto, XXE, prototype
pollution, insecure JWT, missing HTTP timeouts, weak TLS, etc.) and map straight into
`cwe_mapping.py`/`recommendation.py`. Set `SECUREWISE_SEMGREP_CONFIG` (e.g. to `auto` or
`p/security-audit`) to opt into Semgrep's full hosted registry instead, if you have network
access and accept the added latency/non-determinism.

Findings are enriched via two shared modules:
- `apps/securewise/scanners/cwe_mapping.py` — canonical issue-key → CWE + OWASP Top 10 (2021,
  the current published edition) mapping.
- `apps/securewise/scanners/recommendation.py` — `RecommendationEngine` providing
  what/why/where/how-to-fix guidance, bad/fixed code examples, and references, with
  language-specific templates (Python/Django, Java/Spring, JavaScript/Node, Go) and a
  generic fallback.

While the cloned repository still exists on disk, `ScannerOrchestrator.run()` also captures a
small numbered `code_snippet` window (3 lines before, the flagged line, 2 after) for findings
with a real `file_path` + `line_number`. The snippet is path-traversal checked before reading,
stored on `SecureWiseFinding.code_snippet`, and omitted for binary, missing, or non-file-backed
findings such as API/DAST endpoint issues. The frontend finding detail page renders this in a
"Vulnerable Code" panel whenever it's present.

SecureWise can optionally generate **AI fix suggestions** per finding via
`POST /api/securewise/findings/{id}/ai-suggestion/`. This endpoint:
- uses the shared `apps.ai_services.providers` abstraction (`AI_PROVIDER` must be configured),
- sends the AI model **only** the finding's title/CWE/OWASP/severity/file/line/code snippet,
  explicitly framed in the system prompt as **untrusted data, never instructions** — a finding
  whose code/description contains prompt-injection text ("ignore previous instructions…") is
  still just treated as literal code content, and the response is constrained to a strict fixed
  JSON schema (`explanation`, `why_dangerous`, `fixed_code_example`, `framework_guidance`,
  `confidence`) that's validated before being stored or returned,
- caches the generated suggestion on the finding unless `?force=true` is supplied (so repeat
  views don't burn AI calls/cost),
- returns `engine_unavailable: true` instead of failing if no provider is configured, and
- is rate-limited per user (`AIRecommendationThrottle`) to control cost/abuse.

Reports can still be created as JSON data, and each ready report can now also be rendered as:
- `GET /api/securewise/reports/{id}/html/` — branded inline HTML report (SecureWise header/
  footer, severity color badges, CWE/OWASP tables)
- `GET /api/securewise/reports/{id}/pdf/` — branded PDF download rendered with WeasyPrint (same
  branding, with page numbers), served with a `Content-Disposition: attachment` download header

### Rescans, deduplication, and quality gates

Rescanning the same repository is a normal, expected workflow (drift detection, verifying a fix
landed) — it must never just pile up duplicate rows for the same issue:

- `SecureWiseFinding` is deduplicated per **(project, fingerprint)**. Re-detecting the same issue
  updates the existing row (`last_seen_at`, `occurrence_count`) instead of inserting a duplicate.
- A finding previously marked **Fixed** that reappears in a later scan is automatically reopened
  (with an audit log entry), since the underlying issue clearly wasn't actually resolved.
- A finding whose engine ran successfully but which is no longer detected is **auto-resolved**
  (`status="fixed"`, with a `review_note` explaining why) — the same behavior you'd expect from
  SonarQube/Snyk/Semgrep when code that used to trigger a rule stops triggering it.
- `first_seen_scan` (never changes) vs `scan` (always the most recent scan that (re-)detected the
  issue) let you distinguish "brand new in this run" from "still open, seen again."

**Quality gates** are policy-driven and fully optional/flexible:
- `SecureWiseScanPolicy` supports `fail_on_severity`, `max_critical`, `max_high`, `max_medium`
  (`-1` = unlimited), `fail_on_secrets`, `fail_on_new_findings_only` (evaluate only newly
  discovered findings, ignoring long-standing recurring ones), `allow_accepted_risks` and
  `allow_false_positives` (exempt those statuses from the gate).
- Exactly one policy per organization can be marked `is_default` (`POST
  /api/securewise/scan-policies/{id}/set-default/`); new scans that don't explicitly choose a
  policy automatically get the org's default applied.
- If a scan has **no policy attached at all**, `quality_gate_passed` is `null` ("not evaluated")
  — never silently rendered as a green "PASSED", which would be misleading.
- Users can explicitly **bypass** the gate for a single scan by setting
  `bypass_quality_gate=true` plus a required `bypass_reason` (audited), instead of the gate being
  silently skipped with no trace.

### Retrying a scan

`POST /api/securewise/scans/{id}/retry/` re-runs a scan that is `failed`, `cancelled`,
`completed_with_warnings`, or `completed`, using its exact original configuration. It clears any
stale per-engine results from the previous attempt first, so progress/engine-status reflect only
the new attempt. Because the scan keeps its original id, finding history (`first_seen_scan`,
`occurrence_count`) carries over correctly — retrying after a real code fix will correctly
auto-resolve findings that no longer reproduce.

### Full-scan engine selection

For `scan_type="full"`, `ScannerOrchestrator.resolve_engines()` always includes
`sast, sca, secrets, iac`, and conditionally adds:
- `container` — if `scan.docker_image` is set, or a `Dockerfile` exists in the repo
- `api` — if `scan.api_spec_url` is set, or an `openapi.json`/`openapi.yaml`/`swagger.json` is found
- `dast` — if `scan.target_url` is set

The resolved list is persisted to `scan.selected_engines` before execution. Progress
(`scan.progress`, 0–100) and status (`scan.status`, e.g. `running_sast`, `normalizing`,
`completed`) update as each engine finishes; per-engine results are stored in
`SecureWiseScanEngineResult` (status, timing, findings count, `raw_summary`, `skipped_reason`).

### Running a scan locally

```bash
python manage.py migrate
python manage.py seed_securewise_demo   # idempotent demo org/project/repo/scan/findings
python manage.py runserver
```

Then use the API (see `apps/securewise/urls.py`), e.g.:

```bash
POST /api/securewise/repositories/validate/     # validate a public/private repo URL
POST /api/securewise/scans/                     # create a scan
POST /api/securewise/scans/{id}/start/          # kick off the background thread
POST /api/securewise/scans/{id}/retry/          # re-run a failed/cancelled/completed scan
POST /api/securewise/scans/{id}/cancel/         # cancel a running scan
GET  /api/securewise/scans/{id}/progress/       # poll status/progress/per-engine summary
GET  /api/securewise/scans/{id}/engine-results/ # detailed per-engine results
GET  /api/securewise/scans/{id}/findings/       # findings this scan run currently reports
POST /api/securewise/findings/{id}/accept-risk/       # accept a finding's risk
POST /api/securewise/findings/{id}/mark-false-positive/ # mark a finding as false positive
POST /api/securewise/findings/{id}/ai-suggestion/       # cached AI remediation advice
POST /api/securewise/findings/{id}/ai-suggestion/?force=true # refresh cached AI advice
POST /api/securewise/scan-policies/{id}/set-default/    # make a policy the org default
GET  /api/securewise/reports/{id}/html/         # branded HTML report
GET  /api/securewise/reports/{id}/pdf/          # branded PDF report download
GET  /api/securewise/dashboard/summary/         # org-wide security posture
```

### Step-by-step: using SecureWise from the UI

This is the intended end-to-end flow for a new user, from the frontend (`securewise-frontend`,
`npm run dev`, default `http://localhost:5174`) against this backend (`http://localhost:8000`).
Login/auth for SecureWise is handled entirely by this same GuideWisey backend — there is no
separate SecureWise account system.

1. **Sign in.** Log in as you normally would; SecureWise reuses your existing session/auth.
2. **Create or select an Organization and Project** (Organizations / Projects pages). A project
   is the unit findings/scans/reports are grouped under.
3. **Connect a repository:**
   - *Public repo:* Repositories → Add Repository → paste the URL (e.g.
     `https://github.com/roshanguptamca/gw-backend`) → **Validate** (runs `git ls-remote` against
     it, no credentials needed) → Save.
   - *Private repo:* Settings/Integrations → add a Git Integration (GitHub or GitLab, personal
     access token) → **Test Connection** (verifies the token against the provider's API without
     ever logging it) → once connected, add the repository the same way; SecureWise will clone
     it using the encrypted, saved token and always deletes the local clone after each scan.
4. **Start a scan** (Run Scan page / "New Scan" on a project):
   - Pick a **scan type**: `sast`, `sca`, `secrets`, `dast`, `iac`, `container`, `api`, or
     **Full Scan** (runs everything that has something to scan — see "Full-scan engine
     selection" above).
   - Select the **Repository** (required for source-based scan types).
   - Fill in extra fields only if relevant: **Target URL** (DAST), **OpenAPI spec URL/path**
     (API scan), **Docker image** (container scan).
   - Optionally pick a **Quality Gate Policy** — if your organization has a default policy
     configured, it's preselected automatically; you can change it or leave it unset. If you
     genuinely need to skip gate enforcement for this one run, check **"Bypass quality gate"**
     and give a reason (this is logged to the audit trail, not silent).
   - Click **Start Scan**.
5. **Watch progress.** The scan detail page polls `/scans/{id}/progress/` and shows the current
   engine (`running_sast`, `running_secrets`, …), elapsed time, findings found so far, and which
   engines were skipped (with a reason, e.g. "no Dockerfile/docker_image configured").
   If a scan fails or is cancelled, a **Retry** button re-runs it with the same configuration.
6. **Review findings.** Once complete, the Findings page/tab lists every issue with severity,
   confidence, CWE, OWASP category, file/line (or endpoint), and — when available — the actual
   **vulnerable code snippet**. Open a finding for the full detail:
   - a rule-based **recommendation** (what's wrong / why it's dangerous / how to fix / bad vs.
     fixed code examples) is always present,
   - click **"✨ Get AI Fix Suggestion"** for an LLM-generated explanation and fix tailored to
     that exact snippet (requires `AI_PROVIDER` configured server-side; shows a clear "not
     configured" notice otherwise, never a raw error),
   - use the status actions to **Mark Fixed**, **Accept Risk**, or **Mark False Positive** — these
     are respected by the quality gate (per policy settings) and won't reappear as "new" if the
     issue is later re-detected while marked Accepted Risk / False Positive; a finding marked
     Fixed that reappears in a later scan is automatically reopened.
7. **Re-scan anytime** (e.g. after pushing a fix). Rescans update existing findings instead of
   creating duplicates: unchanged issues get a bumped "last seen" count, resolved issues are
   auto-marked Fixed, and recurring "Fixed" issues are automatically reopened.
8. **Generate a report** (Reports page): choose a report type (OWASP Top 10, CWE Top 25, Security
   Summary, Executive Summary, Developer Remediation, Quality Gate) and format. Every ready report
   can be **viewed inline as branded HTML** or **downloaded as a branded PDF** (SecureWise header/
   footer, severity color badges, generated timestamp) — no separate export tooling needed.
9. **Check the dashboard** for an org-wide rollup: security score, findings by severity/scanner
   type, OWASP/CWE Top 25 coverage, quality gate pass/fail counts, and recent scan activity.

### ⚠️ DAST authorization warning

`DastScanner` only ever runs **passive** checks (response headers, cookies, CORS, informational
`robots.txt`/`sitemap.xml` requests) — it never sends destructive payloads, performs auth
bypass attempts, or fuzzes inputs. Nonetheless, **only run DAST scans against targets you own
or are explicitly authorized to test.** Scanning third-party systems without authorization may
be illegal in your jurisdiction.

### Known limitations

- No live OSV.dev / vulnerability-database network lookups by default (SCA relies on a
  curated known-vulnerable-version list plus a full dependency inventory in `raw_summary`);
  an optional best-effort OSV query could be added later behind a short timeout.
- Container and API scanning require explicit configuration (`docker_image` / `api_spec_url`,
  or discoverable Dockerfile/spec files) — they cannot infer a target on their own.
- ZAP is not installed in this environment, so DAST is passive-only; installing ZAP
  (`docker pull zaproxy/zap-stable`) does not currently wire up active scanning automatically —
  it is detected but not invoked by default.
- The bundled offline semgrep rule pack (`apps/securewise/scanners/rules/semgrep/`) is a curated,
  high-precision starter set (SQLi, command injection, unsafe deserialization, weak crypto, XXE,
  etc. across Python/JS/Java/Go) — it is intentionally not a full copy of Semgrep's registry, so
  it will not catch everything a full `--config=auto`/`p/security-audit` run would. Expand the
  rule pack over time, or set `SECUREWISE_SEMGREP_CONFIG` if you want the full registry and
  accept the network dependency + slower runtime.
- AI fix suggestions require `AI_PROVIDER` to be configured; without it, the endpoint returns
  `engine_unavailable: true` rather than an error, and the UI shows a clear "not configured"
  notice instead of hiding the button.
- Scans currently run in a background Python thread (`ScannerRunner`) rather than a real task
  queue (Celery/Dramatiq) — acceptable for local/dev use, but a production deployment under load
  should swap this for a proper worker queue (the `ScannerRunner`/orchestrator interfaces are
  already decoupled from HTTP request handling, so this is a drop-in change).

---

## License

MIT License
