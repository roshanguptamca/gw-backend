"""
SCA engine: real trivy via subprocess when available, else a lockfile-parsing
fallback that flags a curated list of well-known vulnerable pinned versions
and records a full dependency inventory in raw_summary.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
from pathlib import Path

from .base import BaseScanner, ScannerFinding, ScannerResult
from .parsers.trivy_parser import parse_trivy_vuln_json

logger = logging.getLogger(__name__)

# name -> list of (max_exclusive_vulnerable_version_str, cve, fixed_version)
# Best-effort curated list — not exhaustive.
_KNOWN_VULNS = {
    "requests": [("2.31.0", "CVE-2023-32681", "2.31.0")],
    "django": [("4.2.10", "CVE-2024-24680", "4.2.10"), ("5.0.2", "CVE-2024-24680", "5.0.2")],
    "lodash": [("4.17.21", "CVE-2020-8203", "4.17.21")],
    "express": [("4.17.3", "CVE-2022-24999", "4.17.3")],
    "log4j-core": [("2.17.1", "CVE-2021-44228", "2.17.1")],
}


def _version_lt(a: str, b: str) -> bool:
    """Best-effort version comparison for dotted numeric versions."""

    def parts(v: str):
        return [int(x) for x in re.findall(r"\d+", v)]

    pa, pb = parts(a), parts(b)
    length = max(len(pa), len(pb))
    pa += [0] * (length - len(pa))
    pb += [0] * (length - len(pb))
    return pa < pb


def _check_known_vuln(name: str, version: str) -> tuple[str, str] | None:
    for known_name, ranges in _KNOWN_VULNS.items():
        if known_name.lower() != name.lower():
            continue
        for max_version, cve, fixed in ranges:
            if version and _version_lt(version, max_version):
                return cve, fixed
    return None


class ScaScanner(BaseScanner):
    scanner_type = "sca"

    def is_available(self) -> bool:
        return True

    def run(self, repo_path: Path, scan_id: str, metadata: dict) -> ScannerResult:
        if shutil.which("trivy"):
            return self._run_trivy(repo_path, scan_id)
        return self._run_fallback(repo_path, scan_id)

    def _run_trivy(self, repo_path: Path, scan_id: str) -> ScannerResult:
        try:
            proc = subprocess.run(
                ["trivy", "fs", "--format", "json", "--scanners", "vuln", str(repo_path)],
                capture_output=True,
                timeout=180,
            )
            data = json.loads(proc.stdout or b"{}")
            findings = parse_trivy_vuln_json(data, scan_id)
            return ScannerResult(success=True, findings=findings, metadata={"raw_tool": "trivy"})
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("trivy run failed, falling back")
            return self._run_fallback(repo_path, scan_id, error=str(exc))

    def _run_fallback(self, repo_path: Path, scan_id: str, error: str = "") -> ScannerResult:
        findings: list[ScannerFinding] = []
        inventory: list[dict] = []

        if repo_path.exists():
            self._parse_requirements_txt(repo_path, findings, inventory)
            self._parse_package_json(repo_path, findings, inventory)
            self._parse_go_mod(repo_path, findings, inventory)
            self._parse_gemfile_lock(repo_path, findings, inventory)
            self._parse_generic_lockfiles(repo_path, inventory)

        return ScannerResult(
            success=True,
            findings=findings,
            metadata={
                "raw_tool": "fallback-lockfile-parser",
                "dependencies_parsed": len(inventory),
                "dependency_inventory": inventory,
                "note": error or None,
            },
        )

    # ------------------------------------------------------------------
    def _flag(self, name: str, version: str, file_path: str, findings: list[ScannerFinding]):
        hit = _check_known_vuln(name, version)
        if not hit:
            return
        cve, fixed = hit
        findings.append(
            ScannerFinding(
                title=f"{cve} in {name}=={version}",
                description=f"{name} {version} is affected by {cve}.",
                severity="high",
                confidence="high",
                scanner_type="sca",
                file_path=file_path,
                cwe_id="CWE-1104",
                owasp_category="A06:2021",
                recommendation=f"Upgrade {name} to {fixed} or later.",
                evidence={"raw_tool": "fallback-lockfile-parser", "cve": cve, "package": name, "version": version},
                fingerprint=f"fallback-sca-{cve}-{name}",
            )
        )

    def _parse_requirements_txt(self, repo_path: Path, findings, inventory):
        req = repo_path / "requirements.txt"
        if not req.exists():
            return
        for line in req.read_text(errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            match = re.match(r"^([A-Za-z0-9_.\-]+)\s*==\s*([0-9][0-9A-Za-z.\-]*)", line)
            if match:
                name, version = match.group(1), match.group(2)
                inventory.append({"name": name, "version": version, "source": "requirements.txt"})
                self._flag(name, version, "requirements.txt", findings)

    def _parse_package_json(self, repo_path: Path, findings, inventory):
        pkg = repo_path / "package.json"
        if not pkg.exists():
            return
        try:
            data = json.loads(pkg.read_text(errors="ignore"))
        except json.JSONDecodeError:
            return
        deps = {}
        deps.update(data.get("dependencies", {}) or {})
        deps.update(data.get("devDependencies", {}) or {})
        for name, version_spec in deps.items():
            version = re.sub(r"^[^\d]*", "", version_spec or "")
            inventory.append({"name": name, "version": version or version_spec, "source": "package.json"})
            if version:
                self._flag(name, version, "package.json", findings)

    def _parse_go_mod(self, repo_path: Path, findings, inventory):
        gomod = repo_path / "go.mod"
        if not gomod.exists():
            return
        for line in gomod.read_text(errors="ignore").splitlines():
            match = re.match(r"^\s*([\w./\-]+)\s+v([0-9][0-9A-Za-z.\-+]*)", line.strip())
            if match:
                inventory.append({"name": match.group(1), "version": match.group(2), "source": "go.mod"})

    def _parse_gemfile_lock(self, repo_path: Path, findings, inventory):
        gemfile = repo_path / "Gemfile.lock"
        if not gemfile.exists():
            return
        for line in gemfile.read_text(errors="ignore").splitlines():
            match = re.match(r"^\s{4}([A-Za-z0-9_\-]+)\s+\(([0-9][0-9A-Za-z.\-]*)\)", line)
            if match:
                inventory.append({"name": match.group(1), "version": match.group(2), "source": "Gemfile.lock"})

    def _parse_generic_lockfiles(self, repo_path: Path, inventory):
        for fname in (
            "pyproject.toml",
            "package-lock.json",
            "yarn.lock",
            "pnpm-lock.yaml",
            "pom.xml",
            "build.gradle",
            "composer.lock",
        ):
            fpath = repo_path / fname
            if fpath.exists():
                inventory.append(
                    {
                        "name": f"<parsed from {fname}>",
                        "version": "",
                        "source": fname,
                        "note": "recorded, not individually parsed",
                    }
                )
