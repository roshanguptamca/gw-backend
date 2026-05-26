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
```

---

## File Storage

Controlled by `FILE_STORAGE_BACKEND` in `.env`:

| Value | Behaviour |
|---|---|
| `db` | Store file bytes in the Django database — **default for local dev** |
| `s3` | Store in AWS S3 |
| `auto` | Use S3 if all 4 AWS credentials are present, else DB |

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

