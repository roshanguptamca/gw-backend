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

## License

MIT License
