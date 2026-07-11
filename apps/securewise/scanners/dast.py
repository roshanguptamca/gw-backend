"""
DAST engine.

SecureWise runs OWASP ZAP baseline scanning when ZAP is available, preferring a
host `zap-baseline.py` binary and falling back to the official ZAP Docker image.
If neither is available, the engine keeps the lightweight passive HTTP
header/cookie/CORS/disclosure checks so scans still produce honest evidence.

Security warning: DAST must only be run against targets you own or are
explicitly authorized to test. The ZAP path uses baseline/passive scanning only;
no active/destructive rules are enabled by this engine.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import requests

from .base import BaseScanner, ScannerFinding, ScannerResult
from .parsers.zap_parser import parse_zap_json

logger = logging.getLogger(__name__)

_TIMEOUT = 8
_ZAP_TIMEOUT = 180
_ZAP_MAX_MINUTES = "1"
_ZAP_DOCKER_IMAGE = "ghcr.io/zaproxy/zaproxy:stable"
_ZAP_REPORT_NAME = "zap-report.json"


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
                metadata={
                    "raw_tool": "none",
                    "dast_skip_reason": skipped_reason,
                    "dast_runtime_logs": metadata.get("dast_runtime_logs", ""),
                },
            )

        logger.warning(
            "DAST scan starting against %s — only authorized targets should ever be scanned; "
            "no destructive payloads are sent.",
            target_url,
        )

        if shutil.which("zap-baseline.py"):
            result = self._zap_cli_scan(target_url)
            if result is not None:
                return result

        if shutil.which("docker"):
            result = self._zap_docker_scan(target_url)
            if result is not None:
                return result

        logger.info("OWASP ZAP is unavailable or failed to produce a report; passive requests-based scan used.")

        return self._passive_scan(target_url)

    def _zap_cli_scan(self, target_url: str) -> ScannerResult | None:
        with tempfile.TemporaryDirectory(prefix="securewise-zap-") as tmp:
            tmp_path = Path(tmp)
            command = self._zap_command(target_url)
            return self._run_zap_command(command, tmp_path, target_url, runner="zap-baseline.py")

    def _zap_docker_scan(self, target_url: str) -> ScannerResult | None:
        with tempfile.TemporaryDirectory(prefix="securewise-zap-") as tmp:
            tmp_path = Path(tmp)
            docker_target_url = _docker_reachable_url(target_url)
            command = [
                "docker",
                "run",
                "--rm",
                "--add-host",
                "host.docker.internal:host-gateway",
                "-w",
                "/zap/wrk",
                "-v",
                f"{tmp_path}:/zap/wrk:rw",
                _ZAP_DOCKER_IMAGE,
                *self._zap_command(docker_target_url),
            ]
            return self._run_zap_command(command, tmp_path, target_url, runner="docker-zap-baseline")

    def _zap_command(self, target_url: str) -> list[str]:
        return [
            "zap-baseline.py",
            "-t",
            target_url,
            "-J",
            _ZAP_REPORT_NAME,
            "-I",
            "-m",
            _ZAP_MAX_MINUTES,
        ]

    def _run_zap_command(
        self,
        command: list[str],
        work_dir: Path,
        target_url: str,
        *,
        runner: str,
    ) -> ScannerResult | None:
        try:
            proc = subprocess.run(
                command,
                cwd=work_dir,
                capture_output=True,
                timeout=_ZAP_TIMEOUT,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            logger.warning("OWASP ZAP %s run failed before report parsing: %s", runner, exc)
            return None

        report_path = work_dir / _ZAP_REPORT_NAME
        if not report_path.exists():
            logger.warning(
                "OWASP ZAP %s did not produce %s; returncode=%s stderr=%s",
                runner,
                _ZAP_REPORT_NAME,
                proc.returncode,
                _truncate_output(proc.stderr),
            )
            return None

        try:
            data = json.loads(report_path.read_text(encoding="utf-8") or "{}")
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("OWASP ZAP %s report could not be parsed: %s", runner, exc)
            return None

        findings = parse_zap_json(data, target_url)
        return ScannerResult(
            success=True,
            findings=findings,
            metadata={
                "raw_tool": "zap",
                "runner": runner,
                "target_url": target_url,
                "returncode": proc.returncode,
                "stdout": _truncate_output(proc.stdout),
                "stderr": _truncate_output(proc.stderr),
            },
        )

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


def _docker_reachable_url(target_url: str) -> str:
    parsed = urlsplit(target_url)
    if parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        return target_url

    netloc = "host.docker.internal"
    if parsed.port:
        netloc = f"{netloc}:{parsed.port}"
    return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))


def _truncate_output(value: bytes | str | None, limit: int = 2000) -> str:
    if value is None:
        return ""
    text = value.decode("utf-8", errors="replace") if isinstance(value, bytes) else str(value)
    return text[:limit]
