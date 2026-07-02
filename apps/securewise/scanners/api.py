"""
API security engine: parses an OpenAPI/Swagger spec (JSON or YAML) and
checks for missing security schemes, unauthenticated sensitive paths, unsafe
HTTP methods without auth, and missing error response schemas.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import yaml

from .base import BaseScanner, ScannerFinding, ScannerResult

logger = logging.getLogger(__name__)

_SPEC_FILENAMES = ("openapi.json", "openapi.yaml", "openapi.yml", "swagger.json", "swagger.yaml", "swagger.yml")
_SENSITIVE_PATH_HINTS = ("/admin", "/users", "/delete", "/internal")
_UNSAFE_METHODS = ("delete", "put")


def _find_spec_file(repo_path: Path) -> Path | None:
    if not repo_path.exists():
        return None
    for name in _SPEC_FILENAMES:
        candidate = repo_path / name
        if candidate.exists():
            return candidate
    for path in repo_path.rglob("*"):
        if path.is_file() and path.name.lower() in _SPEC_FILENAMES:
            return path
    return None


def _load_spec(path: Path) -> dict | None:
    try:
        text = path.read_text(errors="ignore")
    except OSError:
        return None
    try:
        if path.suffix == ".json":
            return json.loads(text)
        return yaml.safe_load(text)
    except Exception:
        logger.warning("Failed to parse OpenAPI/Swagger spec at %s", path)
        return None


class ApiScanner(BaseScanner):
    scanner_type = "api"

    def is_available(self) -> bool:
        return True

    def run(self, repo_path: Path, scan_id: str, metadata: dict) -> ScannerResult:
        spec_path = None
        api_spec_url = metadata.get("api_spec_url")
        if api_spec_url:
            candidate = Path(api_spec_url)
            if candidate.exists():
                spec_path = candidate
            else:
                candidate2 = repo_path / api_spec_url
                if candidate2.exists():
                    spec_path = candidate2
        if spec_path is None:
            spec_path = _find_spec_file(repo_path)

        if spec_path is None:
            return ScannerResult(
                success=True,
                findings=[],
                status="skipped",
                skipped_reason="no OpenAPI/Swagger spec found",
                metadata={"raw_tool": "openapi-static-checks"},
            )

        spec = _load_spec(spec_path)
        if not spec:
            return ScannerResult(
                success=True,
                findings=[],
                status="skipped",
                skipped_reason="OpenAPI/Swagger spec found but could not be parsed",
                metadata={"raw_tool": "openapi-static-checks", "spec_file": str(spec_path)},
            )

        findings = self._analyze_spec(spec, spec_path)
        return ScannerResult(
            success=True,
            findings=findings,
            metadata={
                "raw_tool": "openapi-static-checks",
                "spec_file": str(spec_path),
                "paths_scanned": len(spec.get("paths", {}) or {}),
            },
        )

    def _analyze_spec(self, spec: dict, spec_path: Path) -> list[ScannerFinding]:
        findings: list[ScannerFinding] = []
        rel = spec_path.name

        security_schemes = (spec.get("components", {}) or {}).get("securitySchemes") or spec.get("securityDefinitions")
        global_security = spec.get("security")
        if not security_schemes:
            findings.append(
                ScannerFinding(
                    title="OpenAPI spec has no securitySchemes defined",
                    description="The API specification does not declare any security schemes (API key, OAuth2, etc.).",
                    severity="high",
                    confidence="high",
                    scanner_type="api",
                    file_path=rel,
                    cwe_id="CWE-862",
                    owasp_category="A01:2021",
                    recommendation="Define at least one securityScheme and apply it globally or per-operation.",
                    evidence={"raw_tool": "openapi-static-checks", "issue": "missing_security_schemes"},
                    fingerprint=f"api-missing-security-schemes-{rel}",
                )
            )

        paths = spec.get("paths", {}) or {}
        for path_key, operations in paths.items():
            if not isinstance(operations, dict):
                continue
            is_sensitive = any(hint in path_key.lower() for hint in _SENSITIVE_PATH_HINTS)
            for method, op in operations.items():
                if method.lower() not in ("get", "post", "put", "delete", "patch", "options", "head"):
                    continue
                if not isinstance(op, dict):
                    continue
                op_security = op.get("security", global_security)
                has_auth = bool(op_security)

                if is_sensitive and not has_auth:
                    findings.append(
                        ScannerFinding(
                            title=f"Sensitive endpoint without security requirement: {method.upper()} {path_key}",
                            description="This endpoint's path suggests sensitive functionality but declares no security requirement.",
                            severity="high",
                            confidence="medium",
                            scanner_type="api",
                            file_path=rel,
                            endpoint=path_key,
                            cwe_id="CWE-862",
                            owasp_category="A01:2021",
                            recommendation="Require authentication/authorization for this endpoint.",
                            evidence={"raw_tool": "openapi-static-checks", "method": method},
                            fingerprint=f"api-sensitive-noauth-{method}-{path_key}",
                        )
                    )

                if method.lower() in _UNSAFE_METHODS and not has_auth:
                    findings.append(
                        ScannerFinding(
                            title=f"Unsafe method without auth: {method.upper()} {path_key}",
                            description=f"{method.upper()} is a state-changing method exposed with no security requirement.",
                            severity="medium",
                            confidence="medium",
                            scanner_type="api",
                            file_path=rel,
                            endpoint=path_key,
                            cwe_id="CWE-862",
                            owasp_category="A01:2021",
                            recommendation="Require authentication for state-changing HTTP methods.",
                            evidence={"raw_tool": "openapi-static-checks", "method": method},
                            fingerprint=f"api-unsafe-method-noauth-{method}-{path_key}",
                        )
                    )

                responses = op.get("responses", {}) or {}
                has_error_response = any(str(code).startswith(("4", "5")) for code in responses)
                if not has_error_response:
                    findings.append(
                        ScannerFinding(
                            title=f"Missing error response schema: {method.upper()} {path_key}",
                            description="This operation does not document any 4xx/5xx error responses.",
                            severity="low",
                            confidence="low",
                            scanner_type="api",
                            file_path=rel,
                            endpoint=path_key,
                            recommendation="Document expected 4xx/5xx error responses for API consumers.",
                            evidence={"raw_tool": "openapi-static-checks", "method": method},
                            fingerprint=f"api-missing-error-response-{method}-{path_key}",
                        )
                    )

        return findings
