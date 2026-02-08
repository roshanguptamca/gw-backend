# ==============================
# GuideWisey Production Makefile
# ==============================

# Config
PYTHON ?= python3
VENV_DIR ?= venv
DOCKER_COMPOSE ?= docker-compose
ENV_FILE ?= .env
DJANGO_MANAGE ?= $(VENV_DIR)/bin/python manage.py
ENV ?= DEV

# ---------------------------------
# Environment
# ---------------------------------

env: $(VENV_DIR)/bin/activate

$(VENV_DIR)/bin/activate: requirements.txt
	@echo "Creating virtual environment..."
	$(PYTHON) -m venv $(VENV_DIR)
	@echo "Installing dependencies..."
	$(VENV_DIR)/bin/pip install --upgrade pip setuptools wheel
	$(VENV_DIR)/bin/pip install -r requirements.txt
	touch $(VENV_DIR)/bin/activate

# ---------------------------------
# Run Django locally
# ---------------------------------

run: env
	@echo "Running Django development server..."
	ENV=$(ENV) $(DJANGO_MANAGE) runserver

run-dev:
	@echo "Running Django in DEV mode (SQLite)..."
	ENV=DEV $(DJANGO_MANAGE) runserver

run-prod:
	@echo "Running Django in PROD mode (Postgres)..."
	ENV=PROD $(DJANGO_MANAGE) runserver

# ---------------------------------
# Migrations
# ---------------------------------

migrate: env
	@echo "Running migrations..."
	ENV=$(ENV) $(DJANGO_MANAGE) makemigrations
	ENV=$(ENV) $(DJANGO_MANAGE) migrate

# ---------------------------------
# Create superuser
# ---------------------------------

superuser: env
	ENV=$(ENV) $(DJANGO_MANAGE) createsuperuser

# ---------------------------------
# Static files
# ---------------------------------

collectstatic: env
	@echo "Collecting static files..."
	ENV=$(ENV) $(DJANGO_MANAGE) collectstatic --noinput

# ---------------------------------
# Docker commands
# ---------------------------------

docker-build:
	@echo "Building Docker images..."
	$(DOCKER_COMPOSE) build

docker-up:
	@echo "Starting Docker containers..."
	$(DOCKER_COMPOSE) up -d

docker-down:
	@echo "Stopping Docker containers..."
	$(DOCKER_COMPOSE) down

docker-logs:
	@echo "Viewing logs..."
	$(DOCKER_COMPOSE) logs -f

docker-shell:
	@echo "Enter Docker container shell..."
	$(DOCKER_COMPOSE) exec web bash

# ---------------------------------
# Test & lint
# ---------------------------------

test: env
	@echo "Running tests..."
	ENV=$(ENV) $(DJANGO_MANAGE) test

lint:
	@echo "Linting Python code..."
	$(VENV_DIR)/bin/flake8 .

format:
	@echo "Formatting Python code..."
	$(VENV_DIR)/bin/black .

# ---------------------------------
# Check ENV
# ---------------------------------

check-env:
	@echo "ENV=$(ENV)"
	@echo "DJANGO_SECRET_KEY=$(DJANGO_SECRET_KEY)"
	@echo "OPENAI_API_KEY=$(OPENAI_API_KEY)"
	@echo "AWS_ACCESS_KEY_ID=$(AWS_ACCESS_KEY_ID)"
	@echo "AWS_SECRET_ACCESS_KEY=$(AWS_SECRET_ACCESS_KEY)"
	@echo "AWS_REGION=$(AWS_REGION)"
	@echo "S3_BUCKET=$(S3_BUCKET)"

# ---------------------------------
# Test S3 client
# ---------------------------------

s3-test:
	@echo "Testing S3 client..."
	$(VENV_DIR)/bin/python - <<END
import os
from services.s3 import S3Client

try:
    s3 = S3Client()
    print("S3Client initialized successfully!")
except Exception as e:
    print("Error:", e)
END

# ---------------------------------
# Test AI client
# ---------------------------------

ai-test:
	@echo "Testing AI client..."
	$(VENV_DIR)/bin/python - <<END
import os
from services.ai import AIClient

try:
    ai = AIClient()
    if ai.client:
        print("AIClient initialized successfully!")
    else:
        print("AIClient not initialized (OPENAI_API_KEY missing)")
except Exception as e:
    print("Error:", e)
END

# ---------------------------------
# Clean
# ---------------------------------

clean:
	@echo "Cleaning pyc, __pycache__, static files, and venv..."
	find . -name "*.pyc" -delete
	find . -name "__pycache__" -delete
	rm -rf staticfiles
	rm -rf $(VENV_DIR)

# ---------------------------------
# Help
# ---------------------------------

help:
	@echo "Available targets:"
	@echo "  env            - Setup virtual environment and install dependencies"
	@echo "  run            - Run Django dev server (uses ENV variable)"
	@echo "  run-dev        - Run Django in DEV mode (SQLite)"
	@echo "  run-prod       - Run Django in PROD mode (Postgres)"
	@echo "  migrate        - Make and apply migrations"
	@echo "  superuser      - Create Django superuser"
	@echo "  collectstatic  - Collect static files"
	@echo "  docker-build   - Build Docker containers"
	@echo "  docker-up      - Start Docker containers"
	@echo "  docker-down    - Stop Docker containers"
	@echo "  docker-logs    - View Docker logs"
	@echo "  docker-shell   - Enter Docker container shell"
	@echo "  test           - Run Django tests"
	@echo "  lint           - Lint code with flake8"
	@echo "  format         - Format code with black"
	@echo "  check-env      - Show runtime environment variables"
	@echo "  s3-test        - Test S3 client initialization"
	@echo "  ai-test        - Test AI client initialization"
	@echo "  clean          - Remove temporary files and venv"
	@echo "  help           - Show this message"
