"""
SAST engine: real semgrep via subprocess when available, else a lightweight
regex-based fallback engine that inspects actual repo files.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
from pathlib import Path

from .base import BaseScanner, ScannerFinding, ScannerResult
from .parsers.semgrep_parser import parse_semgrep_json
from .recommendation import RecommendationEngine

logger = logging.getLogger(__name__)

# Bundled, curated rule pack — deterministic and works fully offline (no call
# to the Semgrep registry). Set SECUREWISE_SEMGREP_CONFIG to point at
# `auto`/`p/security-audit`/a custom path if you want to opt into semgrep's
# hosted registry instead (requires network + optionally a login token).
_BUNDLED_RULES_DIR = Path(__file__).parent / "rules" / "semgrep"

_SKIP_DIRS = {".git", "node_modules", "venv", ".venv", "dist", "build", "__pycache__", ".tox", "site-packages"}
_SCAN_EXTENSIONS = {".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go"}

_EXT_TO_LANGUAGE = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "javascript",
    ".jsx": "javascript",
    ".tsx": "javascript",
    ".java": "java",
    ".go": "go",
}

# Compiled regex rules: (issue_key, languages, pattern)
_RULES: list[tuple[str, set[str], re.Pattern]] = [
    (
        "eval_usage",
        {".py", ".js", ".ts", ".jsx", ".tsx"},
        re.compile(r"\b(eval|exec)\s*\("),
    ),
    (
        "unsafe_pickle",
        {".py"},
        re.compile(r"\bpickle\.loads?\s*\("),
    ),
    (
        "unsafe_yaml_load",
        {".py"},
        re.compile(r"\byaml\.load\s*\((?!.*SafeLoader)"),
    ),
    (
        "command_injection",
        {".py"},
        re.compile(r"subprocess\.\w+\([^)]*shell\s*=\s*True"),
    ),
    (
        "debug_enabled",
        {".py"},
        re.compile(r"^\s*DEBUG\s*=\s*True\s*$", re.MULTILINE),
    ),
    (
        "sql_injection",
        {".py"},
        re.compile(r"execute\s*\(\s*(?:f[\"']|[\"'].*%s.*[\"']\s*%|[\"'].*\+)"),
    ),
]

_HARDCODED_SECRET_RE = re.compile(
    r"\b([A-Z_]*(?:API|SECRET|TOKEN|PASSWORD|KEY)[A-Z_]*)\s*=\s*[\"']([A-Za-z0-9/_\-\.\+=]{12,})[\"']"
)

_WEAK_HASH_RE = re.compile(r"hashlib\.(md5|sha1)\s*\(")
_AUTH_CONTEXT_RE = re.compile(r"(auth|password|passwd|login|credential)", re.IGNORECASE)


class SastScanner(BaseScanner):
    scanner_type = "sast"

    def is_available(self) -> bool:
        return True  # fallback engine always available

    def run(self, repo_path: Path, scan_id: str, metadata: dict) -> ScannerResult:
        if shutil.which("semgrep"):
            return self._run_semgrep(repo_path, scan_id)
        return self._run_fallback(repo_path, scan_id)

    # ------------------------------------------------------------------
    def _run_semgrep(self, repo_path: Path, scan_id: str) -> ScannerResult:
        config = os.environ.get("SECUREWISE_SEMGREP_CONFIG", str(_BUNDLED_RULES_DIR))
        try:
            proc = subprocess.run(
                ["semgrep", f"--config={config}", "--json", "--timeout", "60", "--metrics=off", str(repo_path)],
                capture_output=True,
                timeout=120,
            )
            data = json.loads(proc.stdout or b"{}")
            findings = parse_semgrep_json(data, scan_id)
            for f in findings:
                self._enrich(f)
            return ScannerResult(
                success=True,
                findings=findings,
                metadata={
                    "raw_tool": "semgrep",
                    "semgrep_config": config,
                    "files_scanned": len(data.get("paths", {}).get("scanned", [])),
                },
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("semgrep run failed, falling back")
            return self._run_fallback(repo_path, scan_id, error=str(exc))

    def _run_fallback(self, repo_path: Path, scan_id: str, error: str = "") -> ScannerResult:
        findings: list[ScannerFinding] = []
        files_scanned = 0
        if repo_path.exists():
            for path in repo_path.rglob("*"):
                if not path.is_file():
                    continue
                if any(part in _SKIP_DIRS for part in path.parts):
                    continue
                if path.suffix not in _SCAN_EXTENSIONS:
                    continue
                files_scanned += 1
                findings.extend(self._scan_file(path, repo_path))

        return ScannerResult(
            success=True,
            findings=findings,
            metadata={"raw_tool": "fallback-rules", "files_scanned": files_scanned, "note": error or None},
        )

    def _scan_file(self, path: Path, repo_path: Path) -> list[ScannerFinding]:
        findings: list[ScannerFinding] = []
        try:
            text = path.read_text(errors="ignore")
        except OSError:
            return findings
        rel_path = str(path.relative_to(repo_path))
        language = _EXT_TO_LANGUAGE.get(path.suffix, "generic")
        lines = text.splitlines()

        for issue_key, exts, pattern in _RULES:
            if path.suffix not in exts:
                continue
            for match in pattern.finditer(text):
                line_number = text.count("\n", 0, match.start()) + 1
                findings.append(self._build_finding(issue_key, rel_path, line_number, language, lines))

        if path.suffix == ".py":
            for match in _HARDCODED_SECRET_RE.finditer(text):
                line_number = text.count("\n", 0, match.start()) + 1
                findings.append(self._build_finding("hardcoded_secrets", rel_path, line_number, language, lines))

            if _AUTH_CONTEXT_RE.search(str(path)):
                for match in _WEAK_HASH_RE.finditer(text):
                    line_number = text.count("\n", 0, match.start()) + 1
                    findings.append(self._build_finding("weak_crypto", rel_path, line_number, language, lines))

        return findings

    def _build_finding(self, issue_key: str, rel_path: str, line_number: int, language: str, lines: list[str]) -> ScannerFinding:
        rec = RecommendationEngine.get_recommendation(issue_key, language)
        code_line = lines[line_number - 1].strip() if 0 < line_number <= len(lines) else ""
        severity = "critical" if issue_key in ("eval_usage", "unsafe_pickle", "sql_injection", "command_injection", "hardcoded_secrets") else "medium"
        finding = ScannerFinding(
            title=rec["what"],
            description=rec["why"],
            severity=severity,
            confidence="medium",
            scanner_type="sast",
            file_path=rel_path,
            line_number=line_number,
            cwe_id=rec["cwe_id"],
            owasp_category=rec["owasp_category"],
            risk=rec["why"],
            impact=rec["why"],
            recommendation=rec["recommendation"],
            bad_code_example=rec["bad_code_example"] or code_line,
            fixed_code_example=rec["fixed_code_example"],
            evidence={"raw_tool": "fallback-rules", "issue_key": issue_key, "matched_line": code_line},
            fingerprint=f"fallback-sast-{issue_key}-{rel_path}-{line_number}",
        )
        return finding

    def _enrich(self, finding: ScannerFinding) -> None:
        if not finding.recommendation:
            rec = RecommendationEngine.get_recommendation("vulnerable_dependency", "generic")
            finding.recommendation = rec["recommendation"]
