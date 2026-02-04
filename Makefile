# ==============================
# GuideWisey Production Makefile
# ==============================

# Config
PYTHON ?= python3
VENV_DIR ?= venv
DOCKER_COMPOSE ?= docker-compose
ENV_FILE ?= .env
DJANGO_MANAGE ?= $(VENV_DIR)/bin/python manage.py

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
	$(DJANGO_MANAGE) runserver

# ---------------------------------
# Migrations
# ---------------------------------

migrate: env
	@echo "Running migrations..."
	$(DJANGO_MANAGE) makemigrations
	$(DJANGO_MANAGE) migrate

# ---------------------------------
# Create superuser
# ---------------------------------

superuser: env
	$(DJANGO_MANAGE) createsuperuser

# ---------------------------------
# Static files
# ---------------------------------

collectstatic: env
	@echo "Collecting static files..."
	$(DJANGO_MANAGE) collectstatic --noinput

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
	$(DJANGO_MANAGE) test

lint:
	@echo "Linting Python code..."
	$(VENV_DIR)/bin/flake8 .

format:
	@echo "Formatting Python code..."
	$(VENV_DIR)/bin/black .

# ---------------------------------
# Environment & secrets
# ---------------------------------

env-check:
	@echo "Checking environment variables..."
	@grep -v '^#' $(ENV_FILE) | xargs -n1 echo

# ---------------------------------
# Clean
# ---------------------------------

clean:
	@echo "Cleaning pyc, __pycache__, and static files..."
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
	@echo "  run            - Run Django development server"
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
	@echo "  env-check      - Show environment variables"
	@echo "  clean          - Remove temporary files and venv"
	@echo "  help           - Show this message"
