"""
Secrets engine: real gitleaks via subprocess when available (it IS available
in this environment), else a lightweight regex-based fallback.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from .base import BaseScanner, ScannerFinding, ScannerResult
from .parsers.gitleaks_parser import parse_gitleaks_json

logger = logging.getLogger(__name__)

_SKIP_DIRS = {".git", "node_modules", "venv", ".venv", "dist", "build", "__pycache__"}

_FALLBACK_PATTERNS = [
    ("aws_access_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("generic_api_key", re.compile(r"(?i)(api|secret)[_-]?key['\"]?\s*[:=]\s*['\"][A-Za-z0-9/_\-\.]{16,}['\"]")),
    ("private_key_block", re.compile(r"-----BEGIN[ A-Z]*PRIVATE KEY-----")),
    ("slack_token", re.compile(r"xox[baprs]-[0-9A-Za-z-]{10,}")),
    ("jwt_token", re.compile(r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")),
]


def _mask(secret: str) -> str:
    if len(secret) <= 4:
        return "*" * len(secret)
    return "*" * (len(secret) - 4) + secret[-4:]


class SecretsScanner(BaseScanner):
    scanner_type = "secrets"

    def is_available(self) -> bool:
        return True

    def run(self, repo_path: Path, scan_id: str, metadata: dict) -> ScannerResult:
        if shutil.which("gitleaks"):
            return self._run_gitleaks(repo_path, scan_id)
        return self._run_fallback(repo_path, scan_id)

    def _run_gitleaks(self, repo_path: Path, scan_id: str) -> ScannerResult:
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            report_path = Path(tmp.name)
        try:
            subprocess.run(
                [
                    "gitleaks",
                    "detect",
                    "--source",
                    str(repo_path),
                    "--no-git",
                    "--report-format",
                    "json",
                    "--report-path",
                    str(report_path),
                    "--exit-code",
                    "0",
                ],
                capture_output=True,
                timeout=120,
            )
            raw = report_path.read_text() if report_path.exists() else "[]"
            data = json.loads(raw) if raw.strip() else []
            findings = parse_gitleaks_json(data, scan_id)
            return ScannerResult(
                success=True,
                findings=findings,
                metadata={"raw_tool": "gitleaks", "matches": len(findings)},
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("gitleaks run failed, falling back")
            return self._run_fallback(repo_path, scan_id, error=str(exc))
        finally:
            report_path.unlink(missing_ok=True)

    def _run_fallback(self, repo_path: Path, scan_id: str, error: str = "") -> ScannerResult:
        findings: list[ScannerFinding] = []
        files_scanned = 0
        if repo_path.exists():
            for path in repo_path.rglob("*"):
                if not path.is_file() or any(part in _SKIP_DIRS for part in path.parts):
                    continue
                try:
                    text = path.read_text(errors="ignore")
                except OSError:
                    continue
                files_scanned += 1
                rel_path = str(path.relative_to(repo_path))
                for rule_id, pattern in _FALLBACK_PATTERNS:
                    for match in pattern.finditer(text):
                        line_number = text.count("\n", 0, match.start()) + 1
                        findings.append(
                            ScannerFinding(
                                title=f"Leaked secret detected: {rule_id}",
                                description=f"Fallback regex rule '{rule_id}' matched a potential secret.",
                                severity="critical",
                                confidence="medium",
                                scanner_type="secrets",
                                file_path=rel_path,
                                line_number=line_number,
                                cwe_id="CWE-798",
                                owasp_category="A02:2021",
                                recommendation="Rotate the exposed credential immediately and remove it from history.",
                                evidence={
                                    "raw_tool": "fallback-regex",
                                    "rule_id": rule_id,
                                    "secret_masked": _mask(match.group(0)),
                                },
                                fingerprint=f"fallback-secret-{rule_id}-{rel_path}-{line_number}",
                            )
                        )
        return ScannerResult(
            success=True,
            findings=findings,
            metadata={"raw_tool": "fallback-regex", "files_scanned": files_scanned, "note": error or None},
        )
