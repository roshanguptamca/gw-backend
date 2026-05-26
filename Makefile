# ==============================
# GuideWisey Backend Makefile
# ==============================

PYTHON     ?= python3
VENV_DIR   ?= .venv
ENV        ?= DEV
MANAGE     := $(VENV_DIR)/bin/python manage.py

# ---------------------------------
# Environment setup
# ---------------------------------

env: $(VENV_DIR)/bin/activate

$(VENV_DIR)/bin/activate: requirements.txt
	@echo "Creating virtual environment..."
	$(PYTHON) -m venv $(VENV_DIR)
	$(VENV_DIR)/bin/pip install --upgrade pip setuptools wheel
	$(VENV_DIR)/bin/pip install -r requirements.txt
	touch $(VENV_DIR)/bin/activate

# ---------------------------------
# Run locally
# ---------------------------------

run: env
	ENV=$(ENV) $(MANAGE) runserver

run-dev:
	ENV=DEV $(MANAGE) runserver

run-prod:
	ENV=PROD $(MANAGE) runserver

run-scheduler:
	@echo "Starting APScheduler background worker (DB-backed, no Redis)..."
	ENV=$(ENV) $(MANAGE) runapscheduler

# ---------------------------------
# Migrations
# ---------------------------------

migrate: env
	ENV=$(ENV) $(MANAGE) makemigrations
	ENV=$(ENV) $(MANAGE) migrate

# ---------------------------------
# Admin / static
# ---------------------------------

superuser: env
	ENV=$(ENV) $(MANAGE) createsuperuser

collectstatic: env
	ENV=$(ENV) $(MANAGE) collectstatic --noinput

# ---------------------------------
# Schema validation
# ---------------------------------

schema: env
	@echo "Validating OpenAPI schema..."
	ENV=$(ENV) $(MANAGE) spectacular --validate
	@echo "✅ Schema valid"

# ---------------------------------
# Docker
# ---------------------------------

docker-build:
	docker-compose build

docker-up:
	docker-compose up -d

docker-down:
	docker-compose down

docker-logs:
	docker-compose logs -f

docker-shell:
	docker-compose exec web bash

# ---------------------------------
# Test & coverage
# ---------------------------------

test: env
	$(VENV_DIR)/bin/pytest tests/ -v

test-fast: env
	$(VENV_DIR)/bin/pytest tests/ -q

test-cov: env
	$(VENV_DIR)/bin/pytest tests/ -v --cov=apps --cov=services --cov-report=html --cov-report=term-missing

test-parallel: env
	$(VENV_DIR)/bin/pytest tests/ -v -n auto

# ---------------------------------
# Code quality
# ---------------------------------

lint: env
	$(VENV_DIR)/bin/flake8 . --exclude=.venv,migrations,staticfiles --max-line-length=120

format: env
	$(VENV_DIR)/bin/black . --exclude="/(\.git|\.venv|migrations|staticfiles)/"

format-check: env
	$(VENV_DIR)/bin/black . --check --exclude="/(\.git|\.venv|migrations|staticfiles)/"

isort: env
	$(VENV_DIR)/bin/isort . --skip .venv --skip migrations --skip staticfiles

isort-check: env
	$(VENV_DIR)/bin/isort . --check --skip .venv --skip migrations --skip staticfiles

format-all: isort format

check: format-check isort-check lint

test-all: check test-cov

# ---------------------------------
# Clean
# ---------------------------------

clean:
	find . -name "*.pyc" -delete
	find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
	rm -rf staticfiles htmlcov .coverage
	rm -rf $(VENV_DIR)

# ---------------------------------
# Help
# ---------------------------------

help:
	@echo ""
	@echo "GuideWisey Backend — Available make targets"
	@echo "============================================"
	@echo ""
	@echo "Setup:"
	@echo "  env              Create .venv and install requirements"
	@echo "  migrate          Make + apply migrations"
	@echo "  superuser        Create Django superuser"
	@echo "  collectstatic    Collect static files"
	@echo ""
	@echo "Run:"
	@echo "  run              Django dev server (respects ENV var)"
	@echo "  run-dev          Django dev server (SQLite, ENV=DEV)"
	@echo "  run-prod         Django with ENV=PROD"
	@echo "  run-scheduler    APScheduler background worker (no Redis)"
	@echo ""
	@echo "Testing:"
	@echo "  test             Run all tests with pytest (verbose)"
	@echo "  test-fast        Run tests (quiet)"
	@echo "  test-cov         Run tests with HTML coverage report"
	@echo "  test-parallel    Run tests in parallel (pytest-xdist)"
	@echo "  test-all         check + test-cov"
	@echo ""
	@echo "Code quality:"
	@echo "  lint             flake8 linting"
	@echo "  format           black formatter"
	@echo "  format-check     black check (no changes)"
	@echo "  isort            sort imports"
	@echo "  isort-check      check import order (no changes)"
	@echo "  format-all       isort + black"
	@echo "  check            format-check + isort-check + lint"
	@echo ""
	@echo "Schema:"
	@echo "  schema           Validate OpenAPI schema (0 warnings = ✅)"
	@echo ""
	@echo "Docker:"
	@echo "  docker-build/up/down/logs/shell"
	@echo ""
	@echo "  clean            Remove pyc, __pycache__, staticfiles, .venv"
	@echo ""

.PHONY: env run run-dev run-prod run-scheduler migrate superuser collectstatic schema \
        docker-build docker-up docker-down docker-logs docker-shell \
        test test-fast test-cov test-parallel lint format format-check \
        isort isort-check format-all check test-all clean help

