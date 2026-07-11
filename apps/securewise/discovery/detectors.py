"""
Static repository detectors used by ApplicationDiscoveryEngine.

Every function here only *reads* files from the cloned repository — nothing
is ever imported, executed, or `eval`'d. This is a hard security requirement:
discovery must be safe to run against untrusted/unknown source code.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from . import ports
from .framework_signatures import (
    CRA_SIGNATURE,
    DJANGO_SIGNATURE,
    EXPRESS_SIGNATURE,
    EXTERNAL_SERVICE_IMAGE_MARKERS,
    FASTAPI_IMPORT_MARKERS,
    FASTAPI_SIGNATURE,
    FLASK_IMPORT_MARKERS,
    FLASK_SIGNATURE,
    GO_FRAMEWORK_MARKERS,
    GO_GENERIC_SIGNATURE,
    JAVA_DEPENDENCY_FILES,
    NEXTJS_SIGNATURE,
    NODE_FRAMEWORK_DEPENDENCY_MARKERS,
    NODE_LOCKFILES,
    PHP_DEPENDENCY_FILES,
    PHP_GENERIC_SIGNATURE,
    PHP_LARAVEL_SIGNATURE,
    PYTHON_DEPENDENCY_FILES,
    RUBY_DEPENDENCY_FILES,
    RUBY_RAILS_SIGNATURE,
    RUBY_SINATRA_SIGNATURE,
    SPRING_BOOT_MARKERS,
    SPRING_BOOT_SIGNATURE,
)

logger = logging.getLogger(__name__)

_MAX_FILES_SCANNED = 400
_MAX_FILE_BYTES = 200_000
_SPEC_FILENAMES = ("openapi.json", "openapi.yaml", "openapi.yml", "swagger.json", "swagger.yaml", "swagger.yml")
_IGNORED_DIR_NAMES = {
    ".git",
    "node_modules",
    "venv",
    ".venv",
    "__pycache__",
    "dist",
    "build",
    ".next",
    "target",
    "vendor",
}
_PYTHON_RUNTIME_ENTRYPOINTS = ("app.py", "main.py", "server.py", "wsgi.py", "asgi.py")
_NODE_RUNTIME_ENTRYPOINTS = ("server.js", "app.js", "main.js", "index.js")
_PHP_RUNTIME_ENTRYPOINTS = ("artisan", "index.php", "server.php")
_RUBY_RUNTIME_ENTRYPOINTS = ("app.rb", "config.ru")
_PORT_HINT_PATTERNS = [
    re.compile(r"PORT\s*\|\|\s*(\d{2,5})", re.IGNORECASE),
    re.compile(r"PORT\s*\?\?\s*(\d{2,5})", re.IGNORECASE),
    re.compile(r"port\s*=\s*(\d{2,5})", re.IGNORECASE),
    re.compile(r"--port(?:=|\s+)(\d{2,5})", re.IGNORECASE),
    re.compile(r"get\(\s*['\"]PORT['\"]\s*,\s*(\d{2,5})\s*\)", re.IGNORECASE),
    re.compile(r"PORT['\"]?\s*[:=]\s*(\d{2,5})", re.IGNORECASE),
    re.compile(r"EXPOSE\s+(\d{2,5})", re.IGNORECASE),
]


def _iter_files(repo_path: Path, max_files: int = _MAX_FILES_SCANNED):
    count = 0
    for path in repo_path.rglob("*"):
        if count >= max_files:
            return
        if not path.is_file():
            continue
        if any(part in _IGNORED_DIR_NAMES for part in path.parts):
            continue
        count += 1
        yield path


def _read_text_safely(path: Path, max_bytes: int = _MAX_FILE_BYTES) -> str:
    try:
        if path.stat().st_size > max_bytes:
            return ""
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _top_level_file(repo_path: Path, names: tuple[str, ...]) -> Path | None:
    for name in names:
        candidate = repo_path / name
        if candidate.is_file():
            return candidate
    return None


def _first_named_file(repo_path: Path, names: tuple[str, ...]) -> Path | None:
    for path in _iter_files(repo_path):
        if path.name in names:
            return path
    return None


def _find_django_settings_file(repo_path: Path) -> Path | None:
    for path in _iter_files(repo_path):
        if path.name != "settings.py":
            continue
        sibling_dir = path.parent
        if (sibling_dir / "wsgi.py").is_file() or (sibling_dir / "asgi.py").is_file():
            return path
    return None


def _python_module_from_path(repo_path: Path, path: Path) -> str:
    rel = path.relative_to(repo_path).with_suffix("")
    parts = list(rel.parts)
    if parts and parts[0] == "src":
        parts = parts[1:]
    return ".".join(parts)


def _infer_port_hint(text: str, default: int) -> int:
    for pattern in _PORT_HINT_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        try:
            port = int(match.group(1))
            if 1 <= port <= 65535:
                return port
        except (TypeError, ValueError):
            continue
    return default


# ---------------------------------------------------------------------------
# Dockerfile / docker-compose
# ---------------------------------------------------------------------------


def detect_dockerfile(repo_path: Path) -> Path | None:
    direct = repo_path / "Dockerfile"
    if direct.is_file():
        return direct
    for path in repo_path.glob("Dockerfile.*"):
        if path.is_file():
            return path
    return None


def detect_docker_compose(repo_path: Path) -> Path | None:
    for name in ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"):
        candidate = repo_path / name
        if candidate.is_file():
            return candidate
    return None


def detect_exposed_ports(dockerfile_path: Path | None) -> list[int]:
    if not dockerfile_path:
        return []
    return ports.parse_dockerfile_exposed_ports(_read_text_safely(dockerfile_path))


def detect_compose_ports_and_services(compose_path: Path | None) -> tuple[list[int], list[str], list[str]]:
    """Returns (host_ports, external_service_labels, env_files_referenced)."""
    if not compose_path:
        return [], [], []
    text = _read_text_safely(compose_path)
    host_ports = ports.parse_compose_host_ports(text)

    external_services: list[str] = []
    for image_marker, label in EXTERNAL_SERVICE_IMAGE_MARKERS.items():
        if re.search(rf"image:\s*['\"]?[\w./-]*{re.escape(image_marker)}", text, re.IGNORECASE):
            if label not in external_services:
                external_services.append(label)

    env_files = sorted(set(re.findall(r"env_file:\s*\n?\s*-?\s*([\w./-]+)", text)))
    return host_ports, external_services, env_files


# ---------------------------------------------------------------------------
# OpenAPI specs
# ---------------------------------------------------------------------------


def detect_openapi_specs(repo_path: Path) -> list[str]:
    found = []
    for path in _iter_files(repo_path):
        if path.name.lower() in _SPEC_FILENAMES:
            found.append(str(path.relative_to(repo_path)))
    return found


# ---------------------------------------------------------------------------
# Required env vars (names only — never values, never secret contents)
# ---------------------------------------------------------------------------


def detect_required_env_vars(repo_path: Path) -> list[str]:
    names: set[str] = set()
    for filename in (".env.example", ".env.sample", ".env.dist", ".env.template"):
        candidate = repo_path / filename
        if not candidate.is_file():
            continue
        for line in _read_text_safely(candidate).splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key = line.split("=", 1)[0].strip()
            if key and key.replace("_", "").isalnum():
                names.add(key)
    return sorted(names)


# ---------------------------------------------------------------------------
# Python
# ---------------------------------------------------------------------------


def detect_python(repo_path: Path) -> dict | None:
    dependency_files = [f for f in PYTHON_DEPENDENCY_FILES if (repo_path / f).is_file()]
    manage_py = repo_path / "manage.py"
    nested_manage_py = None if manage_py.is_file() else _first_named_file(repo_path, ("manage.py",))
    manage_py = manage_py if manage_py.is_file() else nested_manage_py
    has_python_files = manage_py is not None or any(repo_path.rglob("*.py"))
    if not dependency_files and not has_python_files:
        return None

    package_manager = "pip"
    if (repo_path / "poetry.lock").is_file():
        package_manager = "poetry"
    elif (repo_path / "Pipfile").is_file():
        package_manager = "pipenv"

    if manage_py and manage_py.is_file():
        sig = DJANGO_SIGNATURE
        manage_py_rel = str(manage_py.relative_to(repo_path))
        requirements_path = None
        for candidate in (repo_path / "requirements.txt", manage_py.parent / "requirements.txt"):
            if candidate.is_file():
                requirements_path = candidate
                break
        build_command = f"pip install -r {requirements_path.relative_to(repo_path)}" if requirements_path else "pip install ."
        return {
            "language": "python",
            "framework": sig.name,
            "project_type": sig.project_type,
            "package_manager": package_manager,
            "dependency_files": dependency_files or [manage_py_rel],
            "build_command": build_command,
            "test_command": f"python {manage_py_rel} test",
            "start_command": f"python {manage_py_rel} runserver 0.0.0.0:{sig.default_port}",
            "default_port": sig.default_port,
            "health_endpoint": sig.health_endpoint,
        }

    # No manage.py — look for FastAPI/Flask import markers in a bounded sample of .py files.
    sample_files = [p for p in _iter_files(repo_path) if p.suffix == ".py"][:_MAX_FILES_SCANNED]
    for path in sample_files:
        text = _read_text_safely(path)
        if any(marker in text for marker in FASTAPI_IMPORT_MARKERS):
            module = path.stem
            sig = FASTAPI_SIGNATURE
            return {
                "language": "python",
                "framework": sig.name,
                "project_type": sig.project_type,
                "package_manager": package_manager,
                "dependency_files": dependency_files,
                "build_command": "pip install -r requirements.txt" if dependency_files else "",
                "test_command": "pytest",
                "start_command": sig.start_command.format(module=module),
                "default_port": sig.default_port,
                "health_endpoint": sig.health_endpoint,
            }
        if any(marker in text for marker in FLASK_IMPORT_MARKERS):
            sig = FLASK_SIGNATURE
            return {
                "language": "python",
                "framework": sig.name,
                "project_type": sig.project_type,
                "package_manager": package_manager,
                "dependency_files": dependency_files,
                "build_command": "pip install -r requirements.txt" if dependency_files else "",
                "test_command": "pytest",
                "start_command": sig.start_command,
                "default_port": sig.default_port,
                "health_endpoint": sig.health_endpoint,
            }

    django_settings = _find_django_settings_file(repo_path)
    if django_settings is not None:
        settings_module = _python_module_from_path(repo_path, django_settings)
        pythonpath = "src" if (repo_path / "src").is_dir() and django_settings.is_relative_to(repo_path / "src") else "."
        build_command = "pip install -r requirements.txt" if "requirements.txt" in dependency_files else "pip install ."
        return {
            "language": "python",
            "framework": "django",
            "project_type": "web_app",
            "package_manager": package_manager,
            "dependency_files": dependency_files or [str(django_settings.relative_to(repo_path))],
            "build_command": build_command,
            "test_command": "pytest" if dependency_files else "python -m django test",
            "start_command": f"PYTHONPATH={pythonpath} DJANGO_SETTINGS_MODULE={settings_module} python -m django runserver 0.0.0.0:8000",
            "default_port": 8000,
            "health_endpoint": "",
        }

    runtime_entrypoint = _top_level_file(repo_path, _PYTHON_RUNTIME_ENTRYPOINTS)
    if runtime_entrypoint:
        text = _read_text_safely(runtime_entrypoint)
        default_port = 8000
        if "flask" in text.lower():
            default_port = 5000
        elif "streamlit" in text.lower():
            default_port = 8501
        elif "django" in text.lower():
            default_port = 8000
        port = _infer_port_hint(text, default_port)
        return {
            "language": "python",
            "framework": "generic_python_app",
            "project_type": "web_app",
            "package_manager": package_manager,
            "dependency_files": dependency_files or [runtime_entrypoint.name],
            "build_command": "pip install -r requirements.txt" if dependency_files else "pip install .",
            "test_command": "pytest",
            "start_command": f"python {runtime_entrypoint.name}",
            "default_port": port,
            "health_endpoint": "",
        }

    # Python present but no recognized web framework — likely a library/CLI/script.
    return {
        "language": "python",
        "framework": "",
        "project_type": "library",
        "package_manager": package_manager,
        "dependency_files": dependency_files,
        "build_command": "pip install -r requirements.txt" if dependency_files else "",
        "test_command": "pytest",
        "start_command": "",
        "default_port": None,
        "health_endpoint": "",
    }


# ---------------------------------------------------------------------------
# Node.js
# ---------------------------------------------------------------------------


def detect_node(repo_path: Path) -> dict | None:
    package_json_path = repo_path / "package.json"
    if not package_json_path.is_file():
        return None

    try:
        package_json = json.loads(_read_text_safely(package_json_path) or "{}")
    except (json.JSONDecodeError, ValueError):
        package_json = {}

    package_manager = "npm"
    for lockfile, manager in NODE_LOCKFILES.items():
        if (repo_path / lockfile).is_file():
            package_manager = manager
            break

    deps = {**package_json.get("dependencies", {}), **package_json.get("devDependencies", {})}
    scripts = package_json.get("scripts", {})

    signature = None
    for marker, sig in NODE_FRAMEWORK_DEPENDENCY_MARKERS:
        if marker in deps:
            signature = sig
            break

    if signature is None:
        signature = CRA_SIGNATURE if "react" in deps else EXPRESS_SIGNATURE if scripts.get("start") else None

    build_command = f"{package_manager} run build" if "build" in scripts else f"{package_manager} install"
    test_command = f"{package_manager} test" if "test" in scripts else ""

    if signature is None:
        runtime_entrypoint = _top_level_file(repo_path, _NODE_RUNTIME_ENTRYPOINTS)
        if runtime_entrypoint:
            text = _read_text_safely(runtime_entrypoint)
            port = _infer_port_hint(text, 3000)
            return {
                "language": "node",
                "framework": "generic_node_app",
                "project_type": "api_service",
                "package_manager": package_manager,
                "dependency_files": ["package.json"],
                "build_command": build_command,
                "test_command": test_command,
                "start_command": f"node {runtime_entrypoint.name}",
                "default_port": port,
                "health_endpoint": "",
            }

        # A package.json exists but no recognized runtime framework/start
        # script was found — treat as a library rather than guessing.
        return {
            "language": "node",
            "framework": "",
            "project_type": "library",
            "package_manager": package_manager,
            "dependency_files": ["package.json"],
            "build_command": build_command,
            "test_command": test_command,
            "start_command": "",
            "default_port": None,
            "health_endpoint": "",
        }

    start_command = signature.start_command.replace("npm", package_manager, 1)
    if scripts.get("start") and signature is not NEXTJS_SIGNATURE:
        start_command = f"{package_manager} start"

    return {
        "language": "node",
        "framework": signature.name,
        "project_type": signature.project_type,
        "package_manager": package_manager,
        "dependency_files": ["package.json"],
        "build_command": build_command,
        "test_command": test_command,
        "start_command": start_command,
        "default_port": signature.default_port,
        "health_endpoint": "",
    }


# ---------------------------------------------------------------------------
# PHP
# ---------------------------------------------------------------------------


def detect_php(repo_path: Path) -> dict | None:
    dependency_files = [f for f in PHP_DEPENDENCY_FILES if (repo_path / f).is_file()]
    if not dependency_files and not any((repo_path / f).is_file() for f in _PHP_RUNTIME_ENTRYPOINTS):
        return None

    composer_path = repo_path / "composer.json"
    composer = {}
    if composer_path.is_file():
        try:
            composer = json.loads(_read_text_safely(composer_path) or "{}")
        except (json.JSONDecodeError, ValueError):
            composer = {}

    require = {**composer.get("require", {}), **composer.get("require-dev", {})}
    if "laravel/framework" in require:
        sig = PHP_LARAVEL_SIGNATURE
    elif any(key.startswith("symfony/") for key in require):
        sig = PHP_GENERIC_SIGNATURE
    else:
        sig = PHP_GENERIC_SIGNATURE

    runtime_entrypoint = _top_level_file(repo_path, _PHP_RUNTIME_ENTRYPOINTS)
    start_command = sig.start_command
    if runtime_entrypoint and runtime_entrypoint.name == "index.php":
        start_command = "php -S 0.0.0.0:8000 -t public"
    elif runtime_entrypoint and runtime_entrypoint.name == "server.php":
        start_command = "php -S 0.0.0.0:8000 server.php"
    elif runtime_entrypoint and runtime_entrypoint.name == "artisan" and sig is PHP_GENERIC_SIGNATURE:
        start_command = "php artisan serve --host=0.0.0.0 --port=8000"

    return {
        "language": "php",
        "framework": sig.name,
        "project_type": sig.project_type,
        "package_manager": "composer",
        "dependency_files": dependency_files or [runtime_entrypoint.name if runtime_entrypoint else "composer.json"],
        "build_command": "composer install" if dependency_files else "",
        "test_command": "vendor/bin/phpunit" if dependency_files else "",
        "start_command": start_command,
        "default_port": sig.default_port,
        "health_endpoint": "",
    }


# ---------------------------------------------------------------------------
# Ruby
# ---------------------------------------------------------------------------


def detect_ruby(repo_path: Path) -> dict | None:
    dependency_files = [f for f in RUBY_DEPENDENCY_FILES if (repo_path / f).is_file()]
    if not dependency_files and not any((repo_path / f).is_file() for f in _RUBY_RUNTIME_ENTRYPOINTS):
        return None

    gemfile_path = repo_path / "Gemfile"
    gemfile_text = _read_text_safely(gemfile_path) if gemfile_path.is_file() else ""

    if "rails" in gemfile_text.lower():
        sig = RUBY_RAILS_SIGNATURE
    elif "sinatra" in gemfile_text.lower():
        sig = RUBY_SINATRA_SIGNATURE
    else:
        sig = RUBY_RAILS_SIGNATURE if (repo_path / "config.ru").is_file() else RUBY_SINATRA_SIGNATURE

    runtime_entrypoint = _top_level_file(repo_path, _RUBY_RUNTIME_ENTRYPOINTS)
    start_command = sig.start_command
    if runtime_entrypoint and runtime_entrypoint.name == "config.ru":
        start_command = "bundle exec rackup -o 0.0.0.0 -p 3000"
    elif runtime_entrypoint and runtime_entrypoint.name == "app.rb":
        start_command = "bundle exec ruby app.rb -o 0.0.0.0 -p 4567"

    return {
        "language": "ruby",
        "framework": sig.name,
        "project_type": sig.project_type,
        "package_manager": "bundler",
        "dependency_files": dependency_files or [runtime_entrypoint.name if runtime_entrypoint else "Gemfile"],
        "build_command": "bundle install" if dependency_files else "",
        "test_command": "bundle exec rspec" if dependency_files else "",
        "start_command": start_command,
        "default_port": sig.default_port,
        "health_endpoint": "",
    }


# ---------------------------------------------------------------------------
# Java
# ---------------------------------------------------------------------------


def detect_java(repo_path: Path) -> dict | None:
    dependency_files = [f for f in JAVA_DEPENDENCY_FILES if (repo_path / f).is_file()]
    if not dependency_files:
        return None

    is_spring_boot = False
    for filename in dependency_files:
        text = _read_text_safely(repo_path / filename)
        if any(marker in text for marker in SPRING_BOOT_MARKERS):
            is_spring_boot = True
            break

    if is_spring_boot:
        sig = SPRING_BOOT_SIGNATURE
        build_command = "./mvnw -B package" if "pom.xml" in dependency_files else "./gradlew build"
        return {
            "language": "java",
            "framework": sig.name,
            "project_type": sig.project_type,
            "package_manager": "maven" if "pom.xml" in dependency_files else "gradle",
            "dependency_files": dependency_files,
            "build_command": build_command,
            "test_command": "./mvnw test" if "pom.xml" in dependency_files else "./gradlew test",
            "start_command": sig.start_command,
            "default_port": sig.default_port,
            "health_endpoint": sig.health_endpoint,
        }

    return {
        "language": "java",
        "framework": "",
        "project_type": "library",
        "package_manager": "maven" if "pom.xml" in dependency_files else "gradle",
        "dependency_files": dependency_files,
        "build_command": "./mvnw -B package" if "pom.xml" in dependency_files else "./gradlew build",
        "test_command": "",
        "start_command": "",
        "default_port": None,
        "health_endpoint": "",
    }


# ---------------------------------------------------------------------------
# Go
# ---------------------------------------------------------------------------


def detect_go(repo_path: Path) -> dict | None:
    if not (repo_path / "go.mod").is_file():
        return None

    go_mod_text = _read_text_safely(repo_path / "go.mod")
    framework_name = ""
    for marker, name in GO_FRAMEWORK_MARKERS.items():
        if marker in go_mod_text:
            framework_name = name
            break

    has_main = (repo_path / "main.go").is_file() or any(repo_path.glob("cmd/**/main.go"))
    if not framework_name and not has_main:
        return {
            "language": "go",
            "framework": "",
            "project_type": "library",
            "package_manager": "go modules",
            "dependency_files": ["go.mod"],
            "build_command": "go build ./...",
            "test_command": "go test ./...",
            "start_command": "",
            "default_port": None,
            "health_endpoint": "",
        }

    sig = GO_GENERIC_SIGNATURE
    return {
        "language": "go",
        "framework": framework_name or sig.name,
        "project_type": sig.project_type,
        "package_manager": "go modules",
        "dependency_files": ["go.mod"],
        "build_command": "go build ./...",
        "test_command": "go test ./...",
        "start_command": sig.start_command,
        "default_port": sig.default_port,
        "health_endpoint": "",
    }
