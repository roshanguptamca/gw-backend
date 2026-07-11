"""
SecureWise — tests for ScannerOrchestrator: engine resolution, dedup by
fingerprint, and cross-engine correlation. All subprocess/git calls are
mocked; no live network access is used.
"""

from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth import get_user_model

import pytest

from apps.securewise.models import (
    SecureWiseMembership,
    SecureWiseOrganization,
    SecureWiseProject,
    SecureWiseRepository,
    SecureWiseScan,
    SecureWiseScanEngineResult,
)
from apps.securewise.scanners.base import ScannerFinding, ScannerResult
from apps.securewise.scanners.orchestrator import ScannerOrchestrator

User = get_user_model()
pytestmark = pytest.mark.django_db


@pytest.fixture
def org_project(db):
    owner = User.objects.create_user(username="orch_owner", email="orch@sw.test", password="TestPass123!")
    org = SecureWiseOrganization.objects.create(name="OrchOrg", slug="orchorg", owner=owner)
    SecureWiseMembership.objects.create(organization=org, user=owner, role="owner")
    project = SecureWiseProject.objects.create(organization=org, name="OrchProj", slug="orchproj", created_by=owner)
    return owner, org, project


def _make_scan(org, project, owner, scan_type="full", **kwargs):
    return SecureWiseScan.objects.create(
        organization=org,
        project=project,
        scan_type=scan_type,
        status="pending",
        triggered_by=owner,
        **kwargs,
    )


class TestResolveEngines:
    def test_single_type_returns_itself(self, org_project, tmp_path):
        owner, org, project = org_project
        scan = _make_scan(org, project, owner, scan_type="sast")
        engines = ScannerOrchestrator().resolve_engines(scan, tmp_path)
        assert engines == ["sast"]

    def test_dast_type_returns_itself(self, org_project, tmp_path):
        owner, org, project = org_project
        scan = _make_scan(org, project, owner, scan_type="dast")
        engines = ScannerOrchestrator().resolve_engines(scan, tmp_path)
        assert engines == ["dast"]

    def test_full_without_extras(self, org_project, tmp_path):
        owner, org, project = org_project
        scan = _make_scan(org, project, owner, scan_type="full")
        engines = ScannerOrchestrator().resolve_engines(scan, tmp_path)
        assert engines == ["sast", "sca", "secrets", "iac"]

    def test_full_with_dockerfile_adds_container(self, org_project, tmp_path):
        owner, org, project = org_project
        (tmp_path / "Dockerfile").write_text("FROM python:3.12\n")
        scan = _make_scan(org, project, owner, scan_type="full")
        engines = ScannerOrchestrator().resolve_engines(scan, tmp_path)
        assert "container" in engines

    def test_full_library_repo_skips_container_and_dast(self, org_project, tmp_path):
        owner, org, project = org_project
        (tmp_path / "requirements.txt").write_text("requests\n")
        (tmp_path / "setup.py").write_text("from setuptools import setup\nsetup(name='x')\n")
        (tmp_path / "mylib.py").write_text("def hello():\n    return 'hi'\n")
        (tmp_path / "Dockerfile").write_text("FROM python:3.12\n")
        repo = SecureWiseRepository.objects.create(
            organization=org,
            project=project,
            name="library-repo",
            access_mode="local_path",
            local_path=str(tmp_path),
            repository_url="",
            created_by=owner,
        )
        scan = _make_scan(org, project, owner, scan_type="full", repository=repo)

        engines = ScannerOrchestrator().resolve_engines(scan, tmp_path)

        assert engines == ["sast", "sca", "secrets", "iac"]

    def test_full_with_docker_image_field_adds_container(self, org_project, tmp_path):
        owner, org, project = org_project
        scan = _make_scan(org, project, owner, scan_type="full", docker_image="myapp:1.0")
        engines = ScannerOrchestrator().resolve_engines(scan, tmp_path)
        assert "container" in engines

    def test_full_with_api_spec_adds_api(self, org_project, tmp_path):
        owner, org, project = org_project
        (tmp_path / "openapi.json").write_text("{}")
        scan = _make_scan(org, project, owner, scan_type="full")
        engines = ScannerOrchestrator().resolve_engines(scan, tmp_path)
        assert "api" in engines

    def test_full_with_target_url_adds_dast(self, org_project, tmp_path):
        owner, org, project = org_project
        scan = _make_scan(org, project, owner, scan_type="full", target_url="https://example.test")
        engines = ScannerOrchestrator().resolve_engines(scan, tmp_path)
        assert "dast" in engines

    def test_full_with_everything(self, org_project, tmp_path):
        owner, org, project = org_project
        (tmp_path / "Dockerfile").write_text("FROM python:3.12\n")
        (tmp_path / "openapi.yaml").write_text("openapi: 3.0.0\n")
        scan = _make_scan(org, project, owner, scan_type="full", target_url="https://example.test")
        engines = ScannerOrchestrator().resolve_engines(scan, tmp_path)
        assert set(engines) == {"sast", "sca", "secrets", "iac", "container", "api", "dast"}


class TestOrchestratorRun:
    def test_run_persists_engine_results(self, org_project, tmp_path):
        owner, org, project = org_project
        scan = _make_scan(org, project, owner, scan_type="secrets")
        with patch("apps.securewise.scanners.secrets.shutil.which", return_value=None):
            findings, engine_meta, any_failed, any_skipped = ScannerOrchestrator().run(scan, tmp_path)
        assert any_failed is False
        assert "secrets" in engine_meta
        results = list(SecureWiseScanEngineResult.objects.filter(scan=scan))
        assert len(results) == 1
        assert results[0].engine == "secrets"
        assert results[0].status == "completed"
        scan.refresh_from_db()
        assert scan.selected_engines == ["secrets"]
        assert scan.progress == 100

    def test_run_marks_engine_skipped(self, org_project, tmp_path):
        owner, org, project = org_project
        scan = _make_scan(org, project, owner, scan_type="dast")
        findings, engine_meta, any_failed, any_skipped = ScannerOrchestrator().run(scan, tmp_path)
        result = SecureWiseScanEngineResult.objects.get(scan=scan)
        assert result.status == "skipped"
        assert result.skipped_reason == "no target URL configured"

    def test_dedup_by_fingerprint(self, org_project, tmp_path):
        owner, org, project = org_project
        scan = _make_scan(org, project, owner, scan_type="full")

        dup_finding_1 = ScannerFinding(
            title="dup",
            description="d",
            severity="high",
            confidence="low",
            scanner_type="sast",
            fingerprint="shared-fp",
        )
        dup_finding_2 = ScannerFinding(
            title="dup",
            description="d",
            severity="high",
            confidence="high",
            scanner_type="sca",
            fingerprint="shared-fp",
        )

        with (
            patch(
                "apps.securewise.scanners.sast.SastScanner.run",
                return_value=ScannerResult(success=True, findings=[dup_finding_1], metadata={}),
            ),
            patch(
                "apps.securewise.scanners.sca.ScaScanner.run",
                return_value=ScannerResult(success=True, findings=[dup_finding_2], metadata={}),
            ),
            patch(
                "apps.securewise.scanners.secrets.SecretsScanner.run",
                return_value=ScannerResult(success=True, findings=[], metadata={}),
            ),
            patch(
                "apps.securewise.scanners.iac.IacScanner.run",
                return_value=ScannerResult(
                    success=True, findings=[], status="skipped", skipped_reason="no IaC files found", metadata={}
                ),
            ),
        ):
            findings, engine_meta, any_failed, any_skipped = ScannerOrchestrator().run(scan, tmp_path)

        assert len(findings) == 1
        assert findings[0].confidence == "high"  # bumped from low by the sca duplicate

    def test_correlation_bumps_sast_confidence(self, org_project, tmp_path):
        owner, org, project = org_project
        scan = _make_scan(org, project, owner, scan_type="full", target_url="https://example.test")

        sast_finding = ScannerFinding(
            title="SQL Injection risk",
            description="d",
            severity="high",
            confidence="medium",
            scanner_type="sast",
            file_path="app/views.py",
            fingerprint="sast-fp",
        )
        dast_finding = ScannerFinding(
            title="SQL Injection detected",
            description="d",
            severity="high",
            confidence="high",
            scanner_type="dast",
            endpoint="/views/sql",
            fingerprint="dast-fp",
        )

        with (
            patch(
                "apps.securewise.scanners.sast.SastScanner.run",
                return_value=ScannerResult(success=True, findings=[sast_finding], metadata={}),
            ),
            patch(
                "apps.securewise.scanners.sca.ScaScanner.run",
                return_value=ScannerResult(success=True, findings=[], metadata={}),
            ),
            patch(
                "apps.securewise.scanners.secrets.SecretsScanner.run",
                return_value=ScannerResult(success=True, findings=[], metadata={}),
            ),
            patch(
                "apps.securewise.scanners.iac.IacScanner.run",
                return_value=ScannerResult(
                    success=True, findings=[], status="skipped", skipped_reason="no IaC files found", metadata={}
                ),
            ),
            patch(
                "apps.securewise.scanners.dast.DastScanner.run",
                return_value=ScannerResult(success=True, findings=[dast_finding], metadata={}),
            ),
        ):
            findings, engine_meta, any_failed, any_skipped = ScannerOrchestrator().run(scan, tmp_path)

        sast_result = next(f for f in findings if f.scanner_type == "sast")
        assert sast_result.confidence == "very_high"
        assert "correlated_with" in sast_result.evidence

    def test_engine_failure_marks_any_failed(self, org_project, tmp_path):
        owner, org, project = org_project
        scan = _make_scan(org, project, owner, scan_type="sast")
        with patch("apps.securewise.scanners.sast.SastScanner.run", side_effect=RuntimeError("boom")):
            findings, engine_meta, any_failed, any_skipped = ScannerOrchestrator().run(scan, tmp_path)
        assert any_failed is True
        result = SecureWiseScanEngineResult.objects.get(scan=scan)
        assert result.status == "failed"
