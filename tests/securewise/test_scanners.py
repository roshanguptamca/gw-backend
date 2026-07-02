"""
SecureWise — unit tests for the new scanners package: base dataclasses,
CWE/OWASP mapping, recommendation templates, and each engine's fallback
(or real-tool) behavior.
"""

from __future__ import annotations

import json
import shutil
from unittest.mock import MagicMock, patch

import pytest

from apps.securewise.scanners.api import ApiScanner
from apps.securewise.scanners.base import BaseScanner, ScannerFinding, ScannerResult
from apps.securewise.scanners.container import ContainerScanner
from apps.securewise.scanners.cwe_mapping import map_finding
from apps.securewise.scanners.dast import DastScanner
from apps.securewise.scanners.iac import IacScanner
from apps.securewise.scanners.parsers.gitleaks_parser import parse_gitleaks_json
from apps.securewise.scanners.parsers.semgrep_parser import parse_semgrep_json
from apps.securewise.scanners.parsers.trivy_parser import parse_trivy_config_json, parse_trivy_vuln_json
from apps.securewise.scanners.parsers.zap_parser import parse_zap_json
from apps.securewise.scanners.recommendation import RecommendationEngine
from apps.securewise.scanners.sast import SastScanner
from apps.securewise.scanners.sca import ScaScanner
from apps.securewise.scanners.secrets import SecretsScanner

pytestmark = pytest.mark.django_db


class TestBaseDataclasses:
    def test_scanner_finding_defaults(self):
        f = ScannerFinding(title="x", description="y", severity="low", confidence="low", scanner_type="sast")
        assert f.fingerprint  # auto-generated
        assert f.evidence == {}

    def test_scanner_result_defaults(self):
        r = ScannerResult(success=True)
        assert r.status == "completed"
        assert r.findings == []

    def test_base_scanner_is_abstract(self):
        with pytest.raises(TypeError):
            BaseScanner()


class TestCweMapping:
    def test_known_mapping(self):
        result = map_finding("sql_injection")
        assert result["cwe_id"] == "CWE-89"
        assert result["owasp_category"] == "A03:2021"

    def test_unknown_mapping_returns_blank(self):
        result = map_finding("totally_unknown_issue")
        assert result == {"cwe_id": "", "owasp_category": ""}

    @pytest.mark.parametrize(
        "issue_key,cwe",
        [
            ("hardcoded_secret", "CWE-798"),
            ("weak_crypto", "CWE-327"),
            ("ssrf", "CWE-918"),
            ("path_traversal", "CWE-22"),
            ("command_injection", "CWE-78"),
            ("insecure_deserialization", "CWE-502"),
            ("xxe", "CWE-611"),
            ("csrf", "CWE-352"),
            ("open_redirect", "CWE-601"),
            ("missing_security_headers", "CWE-693"),
            ("insecure_cors", "CWE-942"),
            ("vulnerable_dependency", "CWE-1104"),
            ("iac_misconfiguration", "CWE-16"),
            ("weak_tls", "CWE-326"),
            ("prototype_pollution", "CWE-1321"),
            ("missing_authorization", "CWE-862"),
            ("xss", "CWE-79"),
        ],
    )
    def test_all_documented_mappings(self, issue_key, cwe):
        assert map_finding(issue_key)["cwe_id"] == cwe


class TestRecommendationEngine:
    def test_python_specific_template(self):
        rec = RecommendationEngine.get_recommendation("sql_injection", "python")
        assert rec["cwe_id"] == "CWE-89"
        assert rec["bad_code_example"]
        assert rec["fixed_code_example"]
        assert "references" in rec

    def test_generic_fallback_for_unknown_language(self):
        rec = RecommendationEngine.get_recommendation("leaked_secret", "rust")
        assert rec["cwe_id"] == "CWE-798"  # falls back to generic template

    def test_completely_unknown_issue_key_still_returns_dict(self):
        rec = RecommendationEngine.get_recommendation("some_never_seen_issue", "python")
        assert "what" in rec
        assert "how_to_fix" in rec

    def test_java_template(self):
        rec = RecommendationEngine.get_recommendation("xxe", "java")
        assert rec["cwe_id"] == "CWE-611"

    def test_javascript_template(self):
        rec = RecommendationEngine.get_recommendation("prototype_pollution", "javascript")
        assert rec["cwe_id"] == "CWE-1321"

    def test_go_template(self):
        rec = RecommendationEngine.get_recommendation("weak_tls", "go")
        assert rec["cwe_id"] == "CWE-326"


class TestSastScannerFallback:
    def test_fallback_used_when_semgrep_missing(self, tmp_path):
        (tmp_path / "app.py").write_text("import pickle\ndata = pickle.loads(raw)\n")
        with patch("apps.securewise.scanners.sast.shutil.which", return_value=None):
            result = SastScanner().run(tmp_path, "scan-1", {})
        assert result.success is True
        assert any("pickle" in f.description.lower() or "deseriali" in f.description.lower() for f in result.findings)
        assert result.metadata["raw_tool"] == "fallback-rules"

    def test_fallback_detects_eval_usage(self, tmp_path):
        (tmp_path / "danger.js").write_text("function run(x) { return eval(x); }\n")
        with patch("apps.securewise.scanners.sast.shutil.which", return_value=None):
            result = SastScanner().run(tmp_path, "scan-2", {})
        titles = " ".join(f.title.lower() for f in result.findings)
        assert "eval" in titles

    def test_semgrep_path_used_when_available(self, tmp_path):
        (tmp_path / "app.py").write_text("x = 1\n")
        fake_output = json.dumps({"results": [], "paths": {"scanned": []}}).encode()
        with patch("apps.securewise.scanners.sast.shutil.which", return_value="/usr/bin/semgrep"):
            with patch("apps.securewise.scanners.sast.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(stdout=fake_output)
                result = SastScanner().run(tmp_path, "scan-3", {})
        assert result.metadata["raw_tool"] == "semgrep"


class TestSecretsScannerRealGitleaks:
    @pytest.mark.skipif(shutil.which("gitleaks") is None, reason="gitleaks binary not installed")
    def test_real_gitleaks_detects_fake_aws_key(self, tmp_path):
        # NOTE: this is a synthetic, randomly-generated placeholder key used
        # only to exercise the gitleaks detection pattern — never a real
        # credential. (gitleaks' default allowlist specifically excludes
        # AWS docs' own "...EXAMPLE" key, so we avoid that suffix here.)
        (tmp_path / "leaked.env").write_text('AWS_ACCESS_KEY_ID = "AKIAHBRPOIGF3CBFNOBM"\n')
        scanner = SecretsScanner()
        assert shutil.which("gitleaks") is not None
        result = scanner.run(tmp_path, "scan-secrets-1", {})
        assert result.success is True
        assert result.metadata["raw_tool"] == "gitleaks"
        assert len(result.findings) >= 1


class TestSecretsScannerFallback:
    def test_fallback_detects_aws_key(self, tmp_path):
        (tmp_path / "leaked.env").write_text("AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE\n")
        with patch("apps.securewise.scanners.secrets.shutil.which", return_value=None):
            result = SecretsScanner().run(tmp_path, "scan-4", {})
        assert result.metadata["raw_tool"] == "fallback-regex"
        assert len(result.findings) >= 1
        assert result.findings[0].evidence["secret_masked"].endswith("MPLE")


class TestScaScannerFallback:
    def test_fallback_flags_known_cve(self, tmp_path):
        (tmp_path / "requirements.txt").write_text("requests==2.28.0\ndjango==4.2.0\n")
        with patch("apps.securewise.scanners.sca.shutil.which", return_value=None):
            result = ScaScanner().run(tmp_path, "scan-5", {})
        cve_ids = [f.evidence.get("cve") for f in result.findings]
        assert "CVE-2023-32681" in cve_ids
        assert result.metadata["dependencies_parsed"] >= 2


class TestIacScannerFallback:
    def test_fallback_flags_missing_user_instruction(self, tmp_path):
        (tmp_path / "Dockerfile").write_text("FROM python:3.12\nCOPY . /app\n")
        with patch("apps.securewise.scanners.iac.shutil.which", return_value=None):
            result = IacScanner().run(tmp_path, "scan-6", {})
        assert any("root" in f.description.lower() or "dockerfile" in f.title.lower() for f in result.findings)

    def test_skips_when_no_iac_files(self, tmp_path):
        with patch("apps.securewise.scanners.iac.shutil.which", return_value=None):
            result = IacScanner().run(tmp_path, "scan-7", {})
        assert result.status == "skipped"
        assert result.skipped_reason == "no IaC files found"


class TestContainerScanner:
    def test_skipped_when_no_image_configured(self, tmp_path):
        result = ContainerScanner().run(tmp_path, "scan-8", {})
        assert result.status == "skipped"
        assert "no docker image" in result.skipped_reason


class TestApiScanner:
    def test_skipped_when_no_spec(self, tmp_path):
        result = ApiScanner().run(tmp_path, "scan-9", {})
        assert result.status == "skipped"
        assert "no OpenAPI" in result.skipped_reason

    def test_flags_missing_security_schemes(self, tmp_path):
        spec = {
            "openapi": "3.0.0",
            "paths": {
                "/admin/users": {"get": {"responses": {"200": {}}}},
            },
        }
        (tmp_path / "openapi.json").write_text(json.dumps(spec))
        result = ApiScanner().run(tmp_path, "scan-10", {})
        assert result.status == "completed"
        titles = " ".join(f.title for f in result.findings)
        assert "securitySchemes" in titles or "security" in titles.lower()


class TestDastScanner:
    def test_skipped_when_no_target_url(self, tmp_path):
        result = DastScanner().run(tmp_path, "scan-11", {})
        assert result.status == "skipped"
        assert result.skipped_reason == "no target URL configured"

    def test_flags_missing_headers(self, tmp_path):
        fake_resp = MagicMock()
        fake_resp.headers = {}
        fake_resp.status_code = 200
        fake_resp.raw.headers.getlist.return_value = []
        with patch("apps.securewise.scanners.dast.requests.get", return_value=fake_resp):
            result = DastScanner().run(tmp_path, "scan-12", {"target_url": "https://example.test"})
        assert result.status == "completed"
        assert any("Content-Security-Policy" in f.title for f in result.findings)


class TestParsers:
    def test_semgrep_parser(self):
        data = {
            "results": [
                {
                    "check_id": "python.django.security.sql-injection",
                    "path": "app/views.py",
                    "start": {"line": 10},
                    "extra": {
                        "message": "possible sqli",
                        "severity": "ERROR",
                        "metadata": {"cwe": ["CWE-89: SQL Injection"], "owasp": ["A03:2021"]},
                    },
                }
            ],
            "paths": {"scanned": ["app/views.py"]},
        }
        findings = parse_semgrep_json(data, "scan-x")
        assert len(findings) == 1
        assert findings[0].severity == "high"
        assert findings[0].file_path == "app/views.py"

    def test_trivy_vuln_parser(self):
        data = {
            "Results": [
                {
                    "Target": "requirements.txt",
                    "Vulnerabilities": [
                        {
                            "VulnerabilityID": "CVE-2023-32681",
                            "PkgName": "requests",
                            "InstalledVersion": "2.28.0",
                            "FixedVersion": "2.31.0",
                            "Severity": "HIGH",
                            "Title": "requests vuln",
                        }
                    ],
                }
            ]
        }
        findings = parse_trivy_vuln_json(data, "scan-x")
        assert len(findings) == 1
        assert findings[0].severity == "high"

    def test_trivy_config_parser(self):
        data = {
            "Results": [
                {
                    "Target": "Dockerfile",
                    "Misconfigurations": [
                        {"ID": "DS002", "Title": "Root user", "Severity": "MEDIUM", "Message": "runs as root"}
                    ],
                }
            ]
        }
        findings = parse_trivy_config_json(data, "scan-x")
        assert len(findings) == 1
        assert findings[0].scanner_type == "iac"

    def test_gitleaks_parser(self):
        data = [
            {
                "RuleID": "aws-access-token",
                "File": ".env",
                "StartLine": 3,
                "Secret": "AKIAIOSFODNN7EXAMPLE",
                "Commit": "abc123",
            }
        ]
        findings = parse_gitleaks_json(data, "scan-x")
        assert len(findings) == 1
        assert findings[0].evidence["secret_masked"].endswith("MPLE")

    def test_zap_parser(self):
        data = {
            "site": [
                {
                    "alerts": [
                        {
                            "name": "Missing Anti-clickjacking Header",
                            "riskdesc": "Medium (High)",
                            "desc": "desc",
                            "solution": "add header",
                            "pluginid": "10020",
                            "instances": [{"uri": "https://example.test/"}],
                        }
                    ]
                }
            ]
        }
        findings = parse_zap_json(data, "scan-x")
        assert len(findings) == 1
        assert findings[0].severity == "medium"
        assert findings[0].endpoint == "https://example.test/"
