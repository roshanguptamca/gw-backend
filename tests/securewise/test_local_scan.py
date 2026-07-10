from __future__ import annotations

import json

import pytest

from apps.securewise.cli import main as cli_main
from apps.securewise.scanners.base import ScannerFinding, ScannerResult
from apps.securewise.scanners.repository import copy_local_repository
from apps.securewise.services import local_scan
from apps.securewise.services.local_scan import (
    REPORT_HTML_NAME,
    REPORT_JSON_NAME,
    LocalScanError,
    run_local_scan,
    validate_repository_path,
)
from apps.securewise.services.pipeline import generate_github_actions_workflow, generate_jenkinsfile


class FakeScanner:
    def run(self, repo_path, scan_id, metadata):
        return ScannerResult(
            success=True,
            findings=[
                ScannerFinding(
                    title="Hardcoded secret",
                    description="A test finding.",
                    severity="high",
                    confidence="high",
                    scanner_type="sast",
                    file_path="app.py",
                    recommendation="Remove the hardcoded value.",
                    evidence={"raw_tool": "test"},
                    fingerprint="local-test-finding",
                )
            ],
            metadata={"raw_tool": "test"},
        )


class CleanScanner:
    def run(self, repo_path, scan_id, metadata):
        return ScannerResult(success=True, findings=[], metadata={"raw_tool": "test"})


def test_validate_repository_path_rejects_missing_path(tmp_path):
    with pytest.raises(LocalScanError) as exc:
        validate_repository_path(tmp_path / "missing")
    assert exc.value.code == "invalid_path"


def test_validate_repository_path_rejects_empty_repository(tmp_path):
    with pytest.raises(LocalScanError) as exc:
        validate_repository_path(tmp_path)
    assert exc.value.code == "empty_repository"


def test_validate_repository_path_rejects_unsupported_content(tmp_path):
    (tmp_path / "notes.txt").write_text("hello", encoding="utf-8")
    with pytest.raises(LocalScanError) as exc:
        validate_repository_path(tmp_path)
    assert exc.value.code == "unsupported_project_type"


def test_run_local_scan_writes_json_and_html_reports(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("SECRET = 'abc'\n", encoding="utf-8")
    output = tmp_path / "out"
    monkeypatch.setitem(local_scan._ENGINE_CLASSES, "sast", FakeScanner)

    report = run_local_scan(repo, output_dir=output, scan_type="sast", fail_on="high")

    assert report["summary"]["total_findings"] == 1
    assert report["scan"]["quality_gate_passed"] is False
    assert (output / REPORT_JSON_NAME).exists()
    assert (output / REPORT_HTML_NAME).exists()
    persisted = json.loads((output / REPORT_JSON_NAME).read_text(encoding="utf-8"))
    assert persisted["artifacts"]["html"].endswith(REPORT_HTML_NAME)


def test_copy_local_repository_copies_into_allowed_workspace(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "app.py").write_text("print('hello')\n", encoding="utf-8")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    dest = workspace / "repo"

    copy_local_repository(source, dest, allowed_root=workspace)

    assert (dest / "app.py").read_text(encoding="utf-8") == "print('hello')\n"


def test_cli_returns_zero_when_quality_gate_passes(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("print('ok')\n", encoding="utf-8")
    monkeypatch.setitem(local_scan._ENGINE_CLASSES, "sast", CleanScanner)

    exit_code = cli_main(["scan", "--path", str(repo), "--output", str(tmp_path / "out"), "--scan-type", "sast"])

    assert exit_code == 0


def test_cli_returns_one_when_quality_gate_fails(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("SECRET = 'abc'\n", encoding="utf-8")
    monkeypatch.setitem(local_scan._ENGINE_CLASSES, "sast", FakeScanner)

    exit_code = cli_main(["scan", "--path", str(repo), "--output", str(tmp_path / "out"), "--scan-type", "sast"])

    assert exit_code == 1


def test_pipeline_generators_include_scan_and_artifacts():
    workflow = generate_github_actions_workflow(output_dir="sw-out", fail_on="medium")
    jenkinsfile = generate_jenkinsfile(output_dir="sw-out", fail_on="critical")

    assert "python -m apps.securewise.cli scan --path ." in workflow
    assert "--fail-on medium" in workflow
    assert "actions/upload-artifact" in workflow
    assert "archiveArtifacts artifacts: 'sw-out/**'" in jenkinsfile
    assert "--fail-on critical" in jenkinsfile
