"""
DAST engine — PASSIVE ONLY.

This engine currently only performs a passive HTTP request/header/cookie
inspection against `target_url`. It does NOT spider, does NOT run active
scan rules, and does NOT invoke OWASP ZAP despite ZAP being referenced in
comments below — those are aspirational, not implemented.

TODO(SW-401, docs/ZAP_DAST_ENGINE.md): replace this with a real ZAP-based
DAST engine (passive + spider + optional opt-in active scan) per the
SecureWise implementation roadmap (docs/IMPLEMENTATION_ROADMAP.md, Phase 4).
Every finding/engine-result produced by this file is labeled
`mode="passive_only"` (see scanners/mode_labels.py) so the UI never implies
this is a full dynamic scan.

Security warning: DAST must only be run against targets you own or are
explicitly authorized to test. No destructive payloads, fuzzing, or auth
bypass attempts are ever sent by this engine.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

import requests

from .base import BaseScanner, ScannerFinding, ScannerResult

logger = logging.getLogger(__name__)

_TIMEOUT = 8


class DastScanner(BaseScanner):
    scanner_type = "dast"

    def is_available(self) -> bool:
        return True

    def run(self, repo_path: Path, scan_id: str, metadata: dict) -> ScannerResult:
        target_url = metadata.get("target_url")
        if not target_url:
            # The orchestrator's smart-discovery/runtime path may have
            # already attempted to auto-start the application and produced a
            # specific, honest reason it couldn't (e.g. "Docker is not
            # available", "did not become reachable"). Prefer that reason
            # when present; otherwise fall back to the generic message.
            skipped_reason = metadata.get("dast_skip_reason") or "no target URL configured"
            return ScannerResult(
                success=True,
                findings=[],
                status="skipped",
                skipped_reason=skipped_reason,
                metadata={"raw_tool": "none"},
            )

        logger.warning(
            "DAST scan starting against %s — only authorized targets should ever be scanned; "
            "no destructive payloads are sent (passive scan only).",
            target_url,
        )

        if shutil.which("zap-baseline.py"):
            # A real OWASP ZAP baseline scan is available on this host, but we
            # keep this best-effort/optional and do not shell out to it by
            # default to avoid unbounded scan time in this environment.
            logger.info("zap-baseline.py detected but not invoked by default; passive requests-based scan used.")

        return self._passive_scan(target_url)

    def _passive_scan(self, target_url: str) -> ScannerResult:
        findings: list[ScannerFinding] = []
        try:
            resp = requests.get(target_url, timeout=_TIMEOUT, allow_redirects=True)
        except requests.RequestException as exc:
            return ScannerResult(
                success=False,
                error=str(exc),
                status="failed",
                metadata={"raw_tool": "requests-passive-dast", "target_url": target_url},
            )

        headers = {k.lower(): v for k, v in resp.headers.items()}
        findings.extend(self._check_security_headers(headers, target_url))
        findings.extend(self._check_cookies(resp, target_url))
        findings.extend(self._check_cors(headers, target_url))
        findings.extend(self._check_verbose_headers(headers, target_url))
        findings.extend(self._check_disclosure_paths(target_url))

        return ScannerResult(
            success=True,
            findings=findings,
            metadata={"raw_tool": "requests-passive-dast", "target_url": target_url, "status_code": resp.status_code},
        )

    def _check_security_headers(self, headers: dict, target_url: str) -> list[ScannerFinding]:
        findings = []
        required = {
            "content-security-policy": ("Missing Content-Security-Policy header", "CWE-693"),
            "x-frame-options": ("Missing X-Frame-Options header", "CWE-693"),
            "strict-transport-security": ("Missing Strict-Transport-Security (HSTS) header", "CWE-693"),
            "x-content-type-options": ("Missing X-Content-Type-Options header", "CWE-693"),
        }
        for header, (title, cwe) in required.items():
            if header not in headers:
                findings.append(
                    ScannerFinding(
                        title=title,
                        description=f"The response from {target_url} does not set the '{header}' header.",
                        severity="medium",
                        confidence="high",
                        scanner_type="dast",
                        endpoint=target_url,
                        cwe_id=cwe,
                        owasp_category="A05:2021",
                        recommendation=f"Add the '{header}' header to all HTTP responses.",
                        evidence={"raw_tool": "requests-passive-dast", "missing_header": header},
                        fingerprint=f"dast-missing-{header}-{target_url}",
                    )
                )
        return findings

    def _check_cookies(self, resp, target_url: str) -> list[ScannerFinding]:
        findings = []
        cookies = []
        try:
            cookies = resp.raw.headers.getlist("Set-Cookie")
        except AttributeError:
            if "Set-Cookie" in resp.headers:
                cookies = [resp.headers["Set-Cookie"]]
        for cookie in cookies:
            missing = []
            if "secure" not in cookie.lower():
                missing.append("Secure")
            if "httponly" not in cookie.lower():
                missing.append("HttpOnly")
            if "samesite" not in cookie.lower():
                missing.append("SameSite")
            if missing:
                findings.append(
                    ScannerFinding(
                        title=f"Cookie missing {'/'.join(missing)} attribute(s)",
                        description=f"A Set-Cookie header from {target_url} is missing: {', '.join(missing)}.",
                        severity="medium",
                        confidence="high",
                        scanner_type="dast",
                        endpoint=target_url,
                        cwe_id="CWE-693",
                        owasp_category="A05:2021",
                        recommendation="Set Secure, HttpOnly and SameSite attributes on all session cookies.",
                        evidence={"raw_tool": "requests-passive-dast", "missing_attributes": missing},
                        fingerprint=f"dast-cookie-{'-'.join(missing)}-{target_url}",
                    )
                )
        return findings

    def _check_cors(self, headers: dict, target_url: str) -> list[ScannerFinding]:
        findings = []
        acao = headers.get("access-control-allow-origin")
        acac = headers.get("access-control-allow-credentials")
        if acao == "*" and str(acac).lower() == "true":
            findings.append(
                ScannerFinding(
                    title="Wildcard CORS origin combined with credentials",
                    description="Access-Control-Allow-Origin: * is set alongside Access-Control-Allow-Credentials: true.",
                    severity="high",
                    confidence="very_high",
                    scanner_type="dast",
                    endpoint=target_url,
                    cwe_id="CWE-942",
                    owasp_category="A05:2021",
                    recommendation="Use an explicit origin allowlist when credentials are allowed.",
                    evidence={"raw_tool": "requests-passive-dast"},
                    fingerprint=f"dast-cors-wildcard-{target_url}",
                )
            )
        return findings

    def _check_verbose_headers(self, headers: dict, target_url: str) -> list[ScannerFinding]:
        findings = []
        for header in ("server", "x-powered-by"):
            value = headers.get(header)
            if value and any(ch.isdigit() for ch in value):
                findings.append(
                    ScannerFinding(
                        title=f"Verbose '{header}' header discloses version information",
                        description=f"The '{header}' header value '{value}' may help attackers fingerprint the stack.",
                        severity="low",
                        confidence="medium",
                        scanner_type="dast",
                        endpoint=target_url,
                        cwe_id="CWE-693",
                        owasp_category="A05:2021",
                        recommendation=f"Suppress or genericize the '{header}' header in production.",
                        evidence={"raw_tool": "requests-passive-dast", "header": header, "value": value},
                        fingerprint=f"dast-verbose-{header}-{target_url}",
                    )
                )
        return findings

    def _check_disclosure_paths(self, target_url: str) -> list[ScannerFinding]:
        findings = []
        base = target_url.rstrip("/")
        for path in ("/robots.txt", "/sitemap.xml"):
            try:
                resp = requests.get(base + path, timeout=_TIMEOUT)
            except requests.RequestException:
                continue
            if resp.status_code == 200 and resp.text.strip():
                findings.append(
                    ScannerFinding(
                        title=f"Informational: {path} is publicly accessible",
                        description=f"{path} was found and may reveal site structure. Review contents for sensitive paths.",
                        severity="info",
                        confidence="high",
                        scanner_type="dast",
                        endpoint=base + path,
                        recommendation="Review the file contents to ensure no sensitive paths are disclosed.",
                        evidence={"raw_tool": "requests-passive-dast"},
                        fingerprint=f"dast-disclosure-{path}-{target_url}",
                    )
                )
        return findings
