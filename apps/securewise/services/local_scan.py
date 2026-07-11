"""
Local repository scanning for `securewise scan --path ...`.

This module deliberately avoids SecureWise database models so it can run in a
developer checkout or CI workspace and emit standalone JSON/HTML artifacts.
"""

from __future__ import annotations

import html
import json
import os
from collections import Counter
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable

from apps.securewise.discovery.engine import ApplicationDiscoveryEngine
from apps.securewise.runtime.manager import RuntimeEnvironmentManager
from apps.securewise.scanners.api import ApiScanner
from apps.securewise.scanners.base import ScannerFinding
from apps.securewise.scanners.container import ContainerScanner
from apps.securewise.scanners.dast import DastScanner
from apps.securewise.scanners.iac import IacScanner
from apps.securewise.scanners.mode_labels import classify_raw_tool
from apps.securewise.scanners.repository import _normalize_local_path
from apps.securewise.scanners.sast import SastScanner
from apps.securewise.scanners.sca import ScaScanner
from apps.securewise.scanners.secrets import SecretsScanner

SEVERITY_ORDER = ["critical", "high", "medium", "low", "info"]
SUPPORTED_SCAN_TYPES = ("sast", "sca", "secrets", "iac", "container", "api", "dast", "full")
REPORT_JSON_NAME = "securewise-report.json"
REPORT_HTML_NAME = "securewise-report.html"

_ENGINE_CLASSES = {
    "sast": SastScanner,
    "sca": ScaScanner,
    "secrets": SecretsScanner,
    "iac": IacScanner,
    "container": ContainerScanner,
    "api": ApiScanner,
    "dast": DastScanner,
}

_SCANNABLE_SUFFIXES = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".java",
    ".go",
    ".rb",
    ".php",
    ".cs",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".tf",
}
_SCANNABLE_FILENAMES = {
    "dockerfile",
    "package.json",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "requirements.txt",
    "poetry.lock",
    "pipfile.lock",
    "go.mod",
    "gemfile.lock",
    "pom.xml",
    "build.gradle",
}


class LocalScanError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def validate_repository_path(path: str | Path) -> Path:
    repo_path = _normalize_local_path(path).resolve()
    if not repo_path.exists():
        raise LocalScanError("invalid_path", f"Path does not exist: {repo_path}")
    if not repo_path.is_dir():
        raise LocalScanError("not_directory", f"Path is not a directory: {repo_path}")
    if not os.access(repo_path, os.R_OK | os.X_OK):
        raise LocalScanError("missing_permissions", f"Path is not readable: {repo_path}")
    try:
        entries = list(repo_path.iterdir())
    except OSError as exc:
        raise LocalScanError("missing_permissions", f"Path cannot be read: {repo_path}") from exc
    if not entries:
        raise LocalScanError("empty_repository", f"Repository path is empty: {repo_path}")
    if not _has_scannable_content(repo_path):
        raise LocalScanError(
            "unsupported_project_type", "No supported source, dependency, API, IaC, or Docker files found."
        )
    return repo_path


def run_local_scan(
    path: str | Path,
    *,
    output_dir: str | Path = "securewise-report",
    scan_type: str = "full",
    fail_on: str = "high",
    target_url: str = "",
    docker_image: str = "",
    api_spec_url: str = "",
) -> dict:
    if scan_type not in SUPPORTED_SCAN_TYPES:
        raise LocalScanError("invalid_scan_type", f"Unsupported scan type '{scan_type}'.")
    if fail_on not in SEVERITY_ORDER:
        raise LocalScanError("invalid_threshold", f"Unsupported severity threshold '{fail_on}'.")

    repo_path = validate_repository_path(path)
    output_path = Path(output_dir).expanduser().resolve()
    output_path.mkdir(parents=True, exist_ok=True)

    discovery = ApplicationDiscoveryEngine().discover(repo_path)
    warnings = list(discovery.warnings)
    if discovery.project_type == "unknown":
        warnings.append("Project type is unknown; SecureWise will run file-based checks where possible.")

    runtime_manager = None
    engines = resolve_local_engines(
        scan_type,
        repo_path,
        discovery=discovery,
        target_url=target_url,
        docker_image=docker_image,
        api_spec_url=api_spec_url,
    )
    engine_results = []
    findings: list[ScannerFinding] = []
    seen = set()
    metadata = {
        "target_url": target_url,
        "docker_image": docker_image,
        "api_spec_url": api_spec_url,
    }
    if scan_type in {"full", "dast"} and discovery.requires_runtime and not target_url:
        runtime_manager = RuntimeEnvironmentManager()
        runtime_result = runtime_manager.try_start(repo_path, discovery)
        if runtime_result.started:
            metadata["target_url"] = runtime_result.runtime_url
            warnings.append(f"Auto-started application runtime at {runtime_result.runtime_url}")
        else:
            metadata["dast_skip_reason"] = runtime_result.skip_reason
            warnings.append(runtime_result.skip_reason)

    if metadata.get("target_url") and "dast" in engines:
        target_url = metadata["target_url"]

    try:
        for engine_name in engines:
            engine = _ENGINE_CLASSES[engine_name]()
            result = engine.run(repo_path, "local", metadata)
            raw_tool = (result.metadata or {}).get("raw_tool")
            engine_results.append(
                {
                    "engine": engine_name,
                    "status": result.status,
                    "success": result.success,
                    "skipped_reason": result.skipped_reason,
                    "error": result.error,
                    "findings_count": len(result.findings),
                    "raw_tool": raw_tool,
                    "mode": classify_raw_tool(raw_tool),
                    "metadata": result.metadata,
                }
            )
            if result.success:
                for finding in result.findings:
                    if finding.fingerprint in seen:
                        continue
                    seen.add(finding.fingerprint)
                    findings.append(finding)
    finally:
        if runtime_manager is not None:
            runtime_manager.stop()

    report = build_local_report(
        repo_path,
        discovery.to_dict(),
        scan_type,
        engines,
        engine_results,
        findings,
        fail_on,
        warnings,
    )
    json_path = output_path / REPORT_JSON_NAME
    html_path = output_path / REPORT_HTML_NAME
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    html_path.write_text(render_local_html_report(report), encoding="utf-8")
    report["artifacts"] = {"json": str(json_path), "html": str(html_path)}
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report


def resolve_local_engines(
    scan_type: str,
    repo_path: Path,
    *,
    discovery=None,
    target_url: str = "",
    docker_image: str = "",
    api_spec_url: str = "",
) -> list[str]:
    if scan_type != "full":
        return [scan_type]
    engines = ["sast", "sca", "secrets", "iac"]
    discovery = discovery or ApplicationDiscoveryEngine().discover(repo_path)
    if docker_image or (_has_dockerfile(repo_path) and discovery.project_type not in ("library", "cli")):
        engines.append("container")
    if api_spec_url or _has_api_spec(repo_path):
        engines.append("api")
    if target_url or discovery.requires_runtime:
        engines.append("dast")
    return engines


def build_local_report(
    repo_path: Path,
    discovery: dict,
    scan_type: str,
    engines: list[str],
    engine_results: list[dict],
    findings: list[ScannerFinding],
    fail_on: str,
    warnings: list[str],
) -> dict:
    severity_counts = Counter(f.severity for f in findings)
    threshold_index = SEVERITY_ORDER.index(fail_on)
    failing_findings = [f for f in findings if f.severity in SEVERITY_ORDER[: threshold_index + 1]]
    return {
        "report_version": "local-1.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "repository_path": str(repo_path),
        "discovery": discovery,
        "scan": {
            "scan_type": scan_type,
            "engines": engines,
            "fail_on": fail_on,
            "quality_gate_passed": not failing_findings,
        },
        "summary": {
            "total_findings": len(findings),
            "failing_findings": len(failing_findings),
            "severity_counts": dict(severity_counts),
            "warnings": warnings,
        },
        "engine_results": engine_results,
        "findings": [_finding_to_dict(f) for f in findings],
    }


def render_local_html_report(report: dict) -> str:
    findings = report.get("findings", [])
    rows = "\n".join(
        "<tr>"
        f"<td>{html.escape(f.get('title', ''))}</td>"
        f"<td>{html.escape(f.get('severity', ''))}</td>"
        f"<td>{html.escape(f.get('scanner_type', ''))}</td>"
        f"<td>{html.escape(f.get('file_path') or f.get('endpoint') or '')}</td>"
        f"<td>{html.escape(f.get('recommendation', ''))}</td>"
        "</tr>"
        for f in findings
    )
    warnings = "".join(f"<li>{html.escape(w)}</li>" for w in report.get("summary", {}).get("warnings", []))
    engines = "".join(
        "<tr>"
        f"<td>{html.escape(e.get('engine', ''))}</td>"
        f"<td>{html.escape(e.get('status', ''))}</td>"
        f"<td>{html.escape(str(e.get('mode', '')))}</td>"
        f"<td>{html.escape(str(e.get('findings_count', 0)))}</td>"
        "</tr>"
        for e in report.get("engine_results", [])
    )
    quality_gate = report.get("scan", {}).get("quality_gate_passed")
    gate_class = "pass" if quality_gate else "fail"
    gate_text = "Passed" if quality_gate else "Failed"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>SecureWise Local Scan Report</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #0f172a; margin: 24px; }}
    h1, h2 {{ color: #0f172a; }}
    table {{ border-collapse: collapse; width: 100%; margin: 12px 0 24px; }}
    th, td {{ border: 1px solid #dbe2ea; padding: 8px; text-align: left; vertical-align: top; }}
    th {{ background: #f8fafc; }}
    .pass {{ background: #dcfce7; color: #166534; padding: 10px; border-radius: 6px; }}
    .fail {{ background: #fee2e2; color: #991b1b; padding: 10px; border-radius: 6px; }}
  </style>
</head>
<body>
  <h1>SecureWise Local Scan Report</h1>
  <p><strong>Repository:</strong> {html.escape(report.get("repository_path", ""))}</p>
  <p><strong>Generated:</strong> {html.escape(report.get("generated_at", ""))}</p>
  <div class="{gate_class}">Quality gate: {gate_text}</div>
  <h2>Summary</h2>
  <p>Total findings: {report.get("summary", {}).get("total_findings", 0)}</p>
  <p>Failing findings: {report.get("summary", {}).get("failing_findings", 0)}</p>
  <h2>Warnings</h2>
  <ul>{warnings or "<li>None</li>"}</ul>
  <h2>Engine Results</h2>
  <table><thead><tr><th>Engine</th><th>Status</th><th>Mode</th><th>Findings</th></tr></thead><tbody>{engines}</tbody></table>
  <h2>Findings</h2>
  <table><thead><tr><th>Title</th><th>Severity</th><th>Scanner</th><th>Location</th><th>Recommendation</th></tr></thead><tbody>{rows}</tbody></table>
</body>
</html>
"""


def _finding_to_dict(finding: ScannerFinding) -> dict:
    data = asdict(finding)
    data["line_number"] = finding.line_number
    return data


def _has_scannable_content(repo_path: Path) -> bool:
    return any(_is_scannable_file(path) for path in _iter_files(repo_path))


def _is_scannable_file(path: Path) -> bool:
    return path.name.lower() in _SCANNABLE_FILENAMES or path.suffix.lower() in _SCANNABLE_SUFFIXES


def _iter_files(repo_path: Path) -> Iterable[Path]:
    for path in repo_path.rglob("*"):
        if ".git" in path.parts or path.is_dir():
            continue
        yield path


def _has_dockerfile(repo_path: Path) -> bool:
    return any(path.name == "Dockerfile" or path.name.startswith("Dockerfile.") for path in _iter_files(repo_path))


def _has_api_spec(repo_path: Path) -> bool:
    names = {"openapi.json", "openapi.yaml", "openapi.yml", "swagger.json", "swagger.yaml", "swagger.yml"}
    return any(path.name.lower() in names for path in _iter_files(repo_path))
