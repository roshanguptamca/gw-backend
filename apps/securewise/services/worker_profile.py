"""Runtime policy for opt-in constrained SecureWise worker profiles."""

from __future__ import annotations

import os
import uuid

LIGHTWEIGHT_SCAN_TYPES = frozenset({"full", "sast", "sca", "secrets", "iac", "api"})
LIGHTWEIGHT_ENGINE_TYPES = frozenset({"sast", "sca", "secrets", "iac", "api"})
LIGHTWEIGHT_CAPABILITIES = tuple(sorted(LIGHTWEIGHT_ENGINE_TYPES))
AUTOPENTEST_API_WORKER_PROFILE = "autopentest_api"
WEBSITE_PASSIVE_WORKER_PROFILE = "website_passive"
EXPERIMENTAL_LOW_RESOURCE_CAPABILITY = "autopentest_experimental_low_resource"
EXPERIMENTAL_LOW_RESOURCE_FLAG = "SECUREWISE_AUTOPENTEST_EXPERIMENTAL_LOW_RESOURCE"
EXPERIMENTAL_ENVIRONMENT = "acc"
# Experimental sessions are capped well below the normal 900s/60rpm limits.
EXPERIMENTAL_MAX_TIMEOUT_SECONDS = 600
EXPERIMENTAL_MAX_REQUESTS_PER_MINUTE = 20


def is_lightweight_worker() -> bool:
    return os.environ.get("SECUREWISE_WORKER_PROFILE", "").strip().lower() == "lightweight"


def is_autopentest_api_worker() -> bool:
    return os.environ.get("SECUREWISE_WORKER_PROFILE", "").strip().lower() == AUTOPENTEST_API_WORKER_PROFILE


def is_website_passive_worker() -> bool:
    return os.environ.get("SECUREWISE_WORKER_PROFILE", "").strip().lower() == WEBSITE_PASSIVE_WORKER_PROFILE


def website_passive_scan_allowed(scan) -> bool:
    """Only authorized, URL-based passive DAST scans; never repository, image, spec or runtime work."""
    return (
        scan.scan_type == "dast"
        and bool(scan.target_url)
        and bool(scan.testing_authorization_id)
        and not scan.docker_image
        and not scan.api_spec_url
        and not scan.repository_id
    )


def experimental_low_resource_allowed() -> bool:
    """Fail closed: opt-in flag AND an explicit ACC deployment marker; production never qualifies."""
    return (
        os.environ.get(EXPERIMENTAL_LOW_RESOURCE_FLAG, "").strip() == "1"
        and os.environ.get("SECUREWISE_DEPLOYMENT_ENV", "").strip().lower() == EXPERIMENTAL_ENVIRONMENT
    )


def experimental_limits_active() -> bool:
    return is_autopentest_api_worker() and experimental_low_resource_allowed()


def autopentest_api_repository_id() -> str | None:
    """Return the single explicitly authorized repository configured for this worker."""
    value = os.environ.get("SECUREWISE_AUTOPENTEST_REPOSITORY_ID", "").strip()
    if not value:
        return None
    try:
        return str(uuid.UUID(value))
    except (ValueError, AttributeError):
        return None


def autopentest_api_worker_configured() -> bool:
    """Require runtime builds and an exact reviewed digest for the allowlisted repository."""
    repository_id = autopentest_api_repository_id()
    if repository_id is None or os.environ.get("SECUREWISE_RUNTIME_BUILDS_ENABLED", "").strip().lower() != "true":
        return False
    from apps.securewise.runtime.trust import configured_trusted_runtime_content

    return repository_id in configured_trusted_runtime_content()


def lightweight_scan_allowed(scan) -> bool:
    """Allow only repository-static jobs with no external target or runtime input."""
    return (
        scan.scan_type in LIGHTWEIGHT_SCAN_TYPES
        and not scan.target_url
        and not scan.docker_image
        and not scan.api_spec_url
    )
