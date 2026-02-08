# GuideWisey Backend

Backend API for the **GuideWisey** platform built with Django REST Framework.

---

## Features

- Django REST Framework APIs
- User registration and login/logout
- Session-based authentication
- Accounts app for managing users
- Admin interface for management
- SQLite database for local development
- Dockerized setup for easy deployment

---

## Requirements

- Python 3.13+
- Docker & Docker Compose (optional for containerized deployment)
- Node.js (only for frontend integration)
- Git

---

## Installation (Local Development)

1. Clone the repository:
```bash
git clone https://github.com/roshanguptamca/gw-backend.git
cd gw-backend
```

2. Create and activate a virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate  # macOS/Linux
venv\Scripts\activate     # Windows
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Create a `.env` file in the project root:
```
SECRET_KEY=dev-secret
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
DB_ENGINE=django.db.backends.sqlite3
DB_NAME=db.sqlite3
STATIC_URL=/static/
MEDIA_URL=/media/
MEDIA_ROOT=media
SESSION_COOKIE_SECURE=False
CSRF_COOKIE_SECURE=False
CORS_ALLOWED_ORIGINS=
```

5. Apply migrations:
```bash
python manage.py migrate
```

6. Create a superuser (optional):
```bash
python manage.py createsuperuser
```

7. Run the development server:
```bash
python manage.py runserver
```

Access the API at `http://localhost:8000/api/` and the admin at `http://localhost:8000/admin/`.

## Docker Deployment

1. Build and start the container:
```bash
docker-compose up --build
```

2. Access the backend API at `http://localhost:8000/api/`.

**Note:** Ensure `.env` exists and Docker has permissions.

## API Endpoints

### Accounts

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/accounts/register/` | Register a new user |
| POST | `/api/accounts/login/` | Login user |
| POST | `/api/accounts/logout/` | Logout authenticated user |

## Testing

Run all tests using Django's test runner:
```bash
python manage.py test
```

- Test accounts registration, login/logout, and serializer validations.
- Tests are located in `tests/accounts/`.

## Project Structure
```
gw-backend/
│
├─ apps/
│  ├─ accounts/             # User management
│  ├─ doc-c/            # Document-related APIs
│                  
│
├─ tests/                   
│  └─ accounts/
├─ manage.py
├─ guidewisey/
│  ├─ settings.py
│  ├─ urls.py
│  └─ wsgi.py
├─ requirements.txt
├─ Dockerfile
├─ docker-compose.yml
└─ .env
```
# Doc-X App Production Workflow
Frontend (FE)
   |
   | 1️⃣ Upload File
   |      (PDF/DOCX/Image)
   |      → S3
   v
S3 Bucket (AWS)
   |
   | 2️⃣ Provide S3 Key
   v
Doc-X Django App (Backend)
   |
   |-- 3a️⃣ Download file from S3
   |      (services/s3_service.py)
   |
   |-- 3b️⃣ Extract text
   |      (extract.py: PDF/DOCX/Image)
   |
   |-- 3c️⃣ Call OpenAI API
   |      (services/openai_service.py)
   |      - input: extracted text + conversation history
   |      - output: explanation / summary
   |
   |-- 3d️⃣ Store in PostgreSQL
   |      models: Document, Conversation
   |
   v
Frontend receives JSON response
   - document_id
   - summary

-----------------------------------------------------

# Follow-Up Questions

Frontend
   |
   | 4️⃣ POST question
   |      {document_id, question}
   v
Doc-X Django App
   |
   |-- 4a️⃣ Load document + conversation history from PostgreSQL
   |
   |-- 4b️⃣ Call OpenAI API
   |      - input: question + previous conversation
   |      - output: answer
   |
   |-- 4c️⃣ Save user question + AI answer to PostgreSQL
   |
   v
Frontend receives JSON response
   - answer
   - 
## Notes

- Email is mandatory for user registration.
- Password confirmation is required.
- Session-based authentication is used.
- Admin static files may require `python manage.py collectstatic` in production.

## License

MIT License