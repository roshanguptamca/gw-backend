"""ApplicationRunPlan — the output of ApplicationDiscoveryEngine.discover()."""

from __future__ import annotations

from dataclasses import dataclass, field

PROJECT_TYPE_CHOICES = (
    "web_app",
    "api_service",
    "frontend_app",
    "library",
    "cli",
    "multi_service",
    "unknown",
)


@dataclass
class ApplicationRunPlan:
    repository_path: str = ""
    project_type: str = "unknown"

    detected_languages: list[str] = field(default_factory=list)
    detected_frameworks: list[str] = field(default_factory=list)
    package_managers: list[str] = field(default_factory=list)
    dependency_files: list[str] = field(default_factory=list)

    build_command: str = ""
    test_command: str = ""
    start_command: str = ""

    dockerfile_path: str = ""
    docker_compose_path: str = ""
    has_dockerfile: bool = False
    has_docker_compose: bool = False

    requires_runtime: bool = False
    can_auto_run: bool = False

    exposed_ports: list[int] = field(default_factory=list)
    candidate_ports: list[int] = field(default_factory=list)

    health_endpoints: list[str] = field(default_factory=list)
    selected_health_endpoint: str = ""
    selected_runtime_url: str = ""

    openapi_specs: list[str] = field(default_factory=list)
    required_env_vars: list[str] = field(default_factory=list)
    external_services: list[str] = field(default_factory=list)

    warnings: list[str] = field(default_factory=list)
    skip_reasons: list[str] = field(default_factory=list)

    confidence: float = 0.0

    def to_dict(self) -> dict:
        return {
            "repository_path": self.repository_path,
            "project_type": self.project_type,
            "detected_languages": self.detected_languages,
            "detected_frameworks": self.detected_frameworks,
            "package_managers": self.package_managers,
            "dependency_files": self.dependency_files,
            "build_command": self.build_command,
            "test_command": self.test_command,
            "start_command": self.start_command,
            "dockerfile_path": self.dockerfile_path,
            "docker_compose_path": self.docker_compose_path,
            "has_dockerfile": self.has_dockerfile,
            "has_docker_compose": self.has_docker_compose,
            "requires_runtime": self.requires_runtime,
            "can_auto_run": self.can_auto_run,
            "exposed_ports": self.exposed_ports,
            "candidate_ports": self.candidate_ports,
            "health_endpoints": self.health_endpoints,
            "selected_health_endpoint": self.selected_health_endpoint,
            "selected_runtime_url": self.selected_runtime_url,
            "openapi_specs": self.openapi_specs,
            "required_env_vars": self.required_env_vars,
            "external_services": self.external_services,
            "warnings": self.warnings,
            "skip_reasons": self.skip_reasons,
            "confidence": self.confidence,
        }
