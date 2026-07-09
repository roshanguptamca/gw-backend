"""ApplicationDiscoveryEngine — orchestrates the detectors into an ApplicationRunPlan."""

from __future__ import annotations

import logging
from pathlib import Path

from . import detectors
from .health import candidate_health_endpoints
from .run_plan import ApplicationRunPlan

logger = logging.getLogger(__name__)

# Detector functions tried in this order — first one to return a non-None
# result "wins" as the primary detected stack. All matching languages are
# still recorded in detected_languages/detected_frameworks for multi-service
# awareness.
_DETECTORS = [
    ("python", detectors.detect_python),
    ("node", detectors.detect_node),
    ("java", detectors.detect_java),
    ("go", detectors.detect_go),
]


class ApplicationDiscoveryEngine:
    """Static, read-only inspection of a cloned repository."""

    def discover(self, repo_path: Path) -> ApplicationRunPlan:
        plan = ApplicationRunPlan(repository_path=str(repo_path))

        if not repo_path.exists() or not repo_path.is_dir():
            plan.project_type = "unknown"
            plan.skip_reasons.append("repository path does not exist or is not a directory")
            return plan

        results = []
        for language, detector in _DETECTORS:
            try:
                result = detector(repo_path)
            except Exception:  # pragma: no cover - defensive; discovery must never crash a scan
                logger.exception("Discovery detector for %s failed", language)
                result = None
            if result:
                results.append(result)

        self._apply_language_results(plan, results)
        self._apply_docker_detection(plan, repo_path)
        self._apply_openapi_detection(plan, repo_path)
        self._apply_env_and_health(plan, repo_path)
        self._finalize_project_type(plan, results)
        self._compute_confidence(plan, results)

        return plan

    # ------------------------------------------------------------------
    def _apply_language_results(self, plan: ApplicationRunPlan, results: list[dict]) -> None:
        if not results:
            plan.warnings.append("No recognized language/framework signature found in this repository.")
            plan.skip_reasons.append("could not detect a supported language or framework")
            return

        for result in results:
            if result["language"] not in plan.detected_languages:
                plan.detected_languages.append(result["language"])
            if result.get("framework") and result["framework"] not in plan.detected_frameworks:
                plan.detected_frameworks.append(result["framework"])
            if result.get("package_manager") and result["package_manager"] not in plan.package_managers:
                plan.package_managers.append(result["package_manager"])
            for dep_file in result.get("dependency_files", []):
                if dep_file not in plan.dependency_files:
                    plan.dependency_files.append(dep_file)

        primary = results[0]
        plan.build_command = primary.get("build_command", "")
        plan.test_command = primary.get("test_command", "")
        plan.start_command = primary.get("start_command", "")
        if primary.get("default_port"):
            plan.candidate_ports.append(primary["default_port"])

        if len(results) > 1:
            plan.warnings.append(
                "Multiple languages/frameworks detected "
                f"({', '.join(r['language'] for r in results)}); this may be a multi-service repository."
            )

    def _apply_docker_detection(self, plan: ApplicationRunPlan, repo_path: Path) -> None:
        dockerfile = detectors.detect_dockerfile(repo_path)
        compose = detectors.detect_docker_compose(repo_path)

        plan.has_dockerfile = dockerfile is not None
        plan.dockerfile_path = str(dockerfile.relative_to(repo_path)) if dockerfile else ""
        plan.has_docker_compose = compose is not None
        plan.docker_compose_path = str(compose.relative_to(repo_path)) if compose else ""

        exposed = detectors.detect_exposed_ports(dockerfile)
        for port in exposed:
            if port not in plan.exposed_ports:
                plan.exposed_ports.append(port)
            if port not in plan.candidate_ports:
                plan.candidate_ports.append(port)

        compose_ports, external_services, env_files = detectors.detect_compose_ports_and_services(compose)
        for port in compose_ports:
            if port not in plan.candidate_ports:
                plan.candidate_ports.append(port)
        for service in external_services:
            if service not in plan.external_services:
                plan.external_services.append(service)
        if env_files:
            plan.warnings.append(f"docker-compose references env file(s): {', '.join(env_files)}")

    def _apply_openapi_detection(self, plan: ApplicationRunPlan, repo_path: Path) -> None:
        plan.openapi_specs = detectors.detect_openapi_specs(repo_path)

    def _apply_env_and_health(self, plan: ApplicationRunPlan, repo_path: Path) -> None:
        plan.required_env_vars = detectors.detect_required_env_vars(repo_path)
        # Default candidate list; refined in _finalize_project_type once the
        # primary framework's known health endpoint (e.g. Spring Boot's
        # /actuator/health) is known.
        plan.health_endpoints = candidate_health_endpoints("")

    def _finalize_project_type(self, plan: ApplicationRunPlan, results: list[dict]) -> None:
        if not results:
            plan.project_type = "unknown"
            plan.requires_runtime = False
            plan.can_auto_run = False
            return

        if len(results) > 1:
            plan.project_type = "multi_service"
        else:
            plan.project_type = results[0]["project_type"]
            if results[0].get("health_endpoint"):
                plan.health_endpoints = candidate_health_endpoints(results[0]["health_endpoint"])

        plan.requires_runtime = plan.project_type in ("web_app", "api_service", "frontend_app", "multi_service")
        if not plan.requires_runtime:
            plan.skip_reasons.append(
                f"project_type is '{plan.project_type}'; there is no HTTP runtime for DAST to target"
            )
            plan.can_auto_run = False
            return

        has_start_command = bool(plan.start_command) or plan.project_type == "multi_service"
        plan.can_auto_run = bool(plan.has_dockerfile or plan.has_docker_compose or has_start_command)
        if not plan.can_auto_run:
            plan.skip_reasons.append("no Dockerfile/docker-compose and no recognized start command was found")

    def _compute_confidence(self, plan: ApplicationRunPlan, results: list[dict]) -> None:
        score = 0.0
        if results:
            score += 0.4
        if plan.detected_frameworks:
            score += 0.2
        if plan.has_dockerfile or plan.has_docker_compose:
            score += 0.2
        if plan.start_command:
            score += 0.1
        if len(results) == 1:
            score += 0.1
        plan.confidence = round(min(score, 1.0), 2)
