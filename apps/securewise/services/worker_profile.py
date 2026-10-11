"""Runtime policy for opt-in constrained SecureWise worker profiles."""

from __future__ import annotations

import os

LIGHTWEIGHT_SCAN_TYPES = frozenset({"full", "sast", "sca", "secrets", "iac", "api"})
LIGHTWEIGHT_ENGINE_TYPES = frozenset({"sast", "sca", "secrets", "iac", "api"})
LIGHTWEIGHT_CAPABILITIES = tuple(sorted(LIGHTWEIGHT_ENGINE_TYPES))


def is_lightweight_worker() -> bool:
    return os.environ.get("SECUREWISE_WORKER_PROFILE", "").strip().lower() == "lightweight"


def lightweight_scan_allowed(scan) -> bool:
    """Allow only repository-static jobs with no external target or runtime input."""
    return (
        scan.scan_type in LIGHTWEIGHT_SCAN_TYPES
        and not scan.target_url
        and not scan.docker_image
        and not scan.api_spec_url
    )
