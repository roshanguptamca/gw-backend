"""
Static, rule-based framework/runtime signatures used by the discovery
detectors. Kept as plain data (regex/marker strings) rather than executing
any code from the scanned repository — discovery must never `import` or
`exec` anything from the target repo.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FrameworkSignature:
    name: str
    project_type: str
    default_port: int
    start_command: str
    health_endpoint: str = ""


# ---------------------------------------------------------------------------
# Python
# ---------------------------------------------------------------------------

PYTHON_DEPENDENCY_FILES = ("requirements.txt", "pyproject.toml", "Pipfile", "poetry.lock", "setup.py")

DJANGO_SIGNATURE = FrameworkSignature(
    name="django",
    project_type="web_app",
    default_port=8000,
    start_command="python manage.py runserver 0.0.0.0:8000",
)
FASTAPI_SIGNATURE = FrameworkSignature(
    name="fastapi",
    project_type="api_service",
    default_port=8000,
    start_command="uvicorn {module}:app --host 0.0.0.0 --port 8000",
)
FLASK_SIGNATURE = FrameworkSignature(
    name="flask",
    project_type="api_service",
    default_port=5000,
    start_command="flask run --host=0.0.0.0 --port=5000",
)

# Markers searched for (as plain substrings) inside a small sample of *.py files.
FASTAPI_IMPORT_MARKERS = ("from fastapi import", "import fastapi", "FastAPI(")
FLASK_IMPORT_MARKERS = ("from flask import Flask", "import flask", "Flask(__name__)")

# ---------------------------------------------------------------------------
# Node.js
# ---------------------------------------------------------------------------

NODE_DEPENDENCY_FILES = ("package.json",)
NODE_LOCKFILES = {
    "package-lock.json": "npm",
    "yarn.lock": "yarn",
    "pnpm-lock.yaml": "pnpm",
}

NEXTJS_SIGNATURE = FrameworkSignature(
    name="nextjs", project_type="frontend_app", default_port=3000, start_command="npm run start"
)
EXPRESS_SIGNATURE = FrameworkSignature(
    name="express", project_type="api_service", default_port=3000, start_command="npm start"
)
NESTJS_SIGNATURE = FrameworkSignature(
    name="nestjs", project_type="api_service", default_port=3000, start_command="npm run start:prod"
)
VITE_SIGNATURE = FrameworkSignature(
    name="vite", project_type="frontend_app", default_port=5173, start_command="npm run preview -- --host 0.0.0.0"
)
CRA_SIGNATURE = FrameworkSignature(
    name="react-scripts", project_type="frontend_app", default_port=3000, start_command="npm start"
)

# package.json "dependencies"/"devDependencies" keys, checked in this priority order.
NODE_FRAMEWORK_DEPENDENCY_MARKERS = [
    ("next", NEXTJS_SIGNATURE),
    ("@nestjs/core", NESTJS_SIGNATURE),
    ("express", EXPRESS_SIGNATURE),
    ("vite", VITE_SIGNATURE),
    ("react-scripts", CRA_SIGNATURE),
]

# ---------------------------------------------------------------------------
# Java
# ---------------------------------------------------------------------------

JAVA_DEPENDENCY_FILES = ("pom.xml", "build.gradle", "build.gradle.kts")

SPRING_BOOT_SIGNATURE = FrameworkSignature(
    name="spring_boot",
    project_type="api_service",
    default_port=8080,
    start_command="./mvnw spring-boot:run",
    health_endpoint="/actuator/health",
)
SPRING_BOOT_MARKERS = ("spring-boot", "org.springframework.boot")

# ---------------------------------------------------------------------------
# Go
# ---------------------------------------------------------------------------

GO_DEPENDENCY_FILES = ("go.mod",)

GO_GENERIC_SIGNATURE = FrameworkSignature(
    name="go_http", project_type="api_service", default_port=8080, start_command="go run ."
)
GO_FRAMEWORK_MARKERS = {
    "github.com/gin-gonic/gin": "gin",
    "github.com/labstack/echo": "echo",
    "github.com/gofiber/fiber": "fiber",
}

# ---------------------------------------------------------------------------
# Common health endpoint candidates (checked in this priority order once a
# runtime URL is available). See discovery/health.py.
# ---------------------------------------------------------------------------

COMMON_HEALTH_ENDPOINTS = (
    "/health",
    "/healthz",
    "/live",
    "/liveness",
    "/ready",
    "/readiness",
    "/status",
    "/api/health",
    "/actuator/health",
    "/",
)

# Docker/compose service image name -> "external service" label, used to
# populate ApplicationRunPlan.external_services without ever reading secret
# values (only image/service names are inspected).
EXTERNAL_SERVICE_IMAGE_MARKERS = {
    "postgres": "postgresql",
    "postgis": "postgresql",
    "mysql": "mysql",
    "mariadb": "mysql",
    "redis": "redis",
    "mongo": "mongodb",
    "rabbitmq": "rabbitmq",
    "elasticsearch": "elasticsearch",
    "memcached": "memcached",
}
