"""
Health endpoint discovery.

Two distinct phases:
 1. Static candidate list (before anything is running) — used to populate
    ApplicationRunPlan.health_endpoints for the discovery preview.
 2. Live probing (once a runtime URL exists) — used by
    RuntimeEnvironmentManager to decide the app is ready, and to record
    ApplicationRunPlan.selected_health_endpoint / selected_runtime_url.

Rules (see docs/SMART_REPO_SCAN.md):
 - A dedicated health endpoint (200/204) is preferred.
 - If none responds but "/" returns 200/3xx/401/403, the app is still
   considered reachable (many apps have no dedicated health endpoint).
 - Missing a dedicated health endpoint is only ever a LOW-severity
   recommendation — never a reason to fail the scan.
"""

from __future__ import annotations

import logging

import requests

from .framework_signatures import COMMON_HEALTH_ENDPOINTS

logger = logging.getLogger(__name__)

_REACHABLE_STATUS_CODES = set(range(200, 300)) | set(range(300, 400)) | {401, 403}
_TIMEOUT = 3


def candidate_health_endpoints(preferred: str = "") -> list[str]:
    """Return the ordered list of endpoints to try, with `preferred` (e.g. Spring's
    /actuator/health) moved to the front if given."""
    endpoints = list(COMMON_HEALTH_ENDPOINTS)
    if preferred and preferred in endpoints:
        endpoints.remove(preferred)
        endpoints.insert(0, preferred)
    elif preferred:
        endpoints.insert(0, preferred)
    return endpoints


def probe_health(base_url: str, preferred_endpoint: str = "", timeout: int = _TIMEOUT) -> dict:
    """
    Probe `base_url` against the candidate health endpoints.

    Returns:
        {
            "reachable": bool,
            "selected_endpoint": str,   # e.g. "/health", or "" if unreachable
            "has_dedicated_health_endpoint": bool,
            "status_code": int | None,
        }
    """
    base = base_url.rstrip("/")
    root_result: dict | None = None

    for path in candidate_health_endpoints(preferred_endpoint):
        url = base + path if path != "/" else base + "/"
        try:
            resp = requests.get(url, timeout=timeout, allow_redirects=True)
        except requests.RequestException:
            continue

        if path == "/":
            root_result = {"status_code": resp.status_code}
            continue

        if resp.status_code in (200, 204):
            return {
                "reachable": True,
                "selected_endpoint": path,
                "has_dedicated_health_endpoint": True,
                "status_code": resp.status_code,
            }

    if root_result and root_result["status_code"] in _REACHABLE_STATUS_CODES:
        return {
            "reachable": True,
            "selected_endpoint": "/",
            "has_dedicated_health_endpoint": False,
            "status_code": root_result["status_code"],
        }

    return {
        "reachable": False,
        "selected_endpoint": "",
        "has_dedicated_health_endpoint": False,
        "status_code": None,
    }
