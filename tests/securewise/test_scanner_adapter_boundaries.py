import json
from pathlib import Path
from unittest.mock import Mock

from apps.securewise.scanners import api, sca, secrets


def test_sca_collects_javascript_go_ruby_and_generic_lockfile_inventory(tmp_path):
    (tmp_path / "package.json").write_text(
        json.dumps({"dependencies": {"lodash": "^4.17.20"}, "devDependencies": {"test-tool": "*"}})
    )
    (tmp_path / "go.mod").write_text("require (\n example.test/module v1.2.3\n)\n")
    (tmp_path / "Gemfile.lock").write_text("    rails (7.0.0)\n")
    (tmp_path / "composer.lock").write_text("{}")
    result = sca.ScaScanner()._run_fallback(tmp_path, "synthetic")
    inventory = {item["name"]: item for item in result.metadata["dependency_inventory"]}
    assert inventory["example.test/module"]["version"] == "1.2.3"
    assert inventory["rails"]["source"] == "Gemfile.lock"
    assert inventory["test-tool"]["version"] == "*"
    assert inventory["<parsed from composer.lock>"]["note"] == "recorded, not individually parsed"
    assert any("CVE-2020-8203" in finding.title for finding in result.findings)


def test_sca_invalid_package_json_does_not_invent_inventory(tmp_path):
    (tmp_path / "package.json").write_text("{invalid")
    result = sca.ScaScanner()._run_fallback(tmp_path, "synthetic")
    assert result.metadata["dependencies_parsed"] == 0
    assert result.findings == []


def test_real_sca_adapter_parses_mocked_trivy_output(monkeypatch, tmp_path):
    monkeypatch.setattr(sca.subprocess, "run", Mock(return_value=Mock(stdout=b'{"Results": []}')))
    result = sca.ScaScanner()._run_trivy(tmp_path, "synthetic")
    assert result.success and result.findings == []
    assert result.metadata["raw_tool"] == "trivy"


def test_gitleaks_adapter_reads_report_and_removes_temporary_file(monkeypatch, tmp_path):
    report_paths = []

    def run(command, **kwargs):
        report = Path(command[command.index("--report-path") + 1])
        report_paths.append(report)
        report.write_text("[]")
        return Mock(returncode=0)

    monkeypatch.setattr(secrets.subprocess, "run", run)
    result = secrets.SecretsScanner()._run_gitleaks(tmp_path, "synthetic")
    assert result.success and result.findings == []
    assert result.metadata == {"raw_tool": "gitleaks", "matches": 0}
    assert len(report_paths) == 1 and not report_paths[0].exists()


def test_static_api_reads_explicit_relative_spec_and_reports_parse_failure(tmp_path):
    spec = tmp_path / "custom.json"
    spec.write_text('{"openapi":"3.0.0", "paths":{}}')
    result = api.ApiScanner().run(tmp_path, "synthetic", {"api_spec_url": "custom.json"})
    assert result.metadata["spec_file"] == str(spec)
    assert result.metadata["execution_mode"] == "openapi_static_analysis"
    spec.write_text("{invalid")
    result = api.ApiScanner().run(tmp_path, "synthetic", {"api_spec_url": str(spec)})
    assert result.status == "skipped"
    assert "could not be parsed" in result.skipped_reason
    assert api._load_spec(tmp_path / "missing.yaml") is None


def test_static_api_finds_nested_specs_without_runtime_access(tmp_path):
    nested = tmp_path / "docs"
    nested.mkdir()
    spec = nested / "openapi.yaml"
    spec.write_text("openapi: 3.0.0\npaths: {}\n")
    assert api._find_spec_file(tmp_path) == spec
    assert api._find_spec_file(tmp_path / "missing") is None
