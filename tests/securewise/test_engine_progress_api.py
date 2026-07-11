"""
SecureWise — API tests for the new /progress/ and /engine-results/ scan
endpoints, including org isolation checks.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model

import pytest
from rest_framework.test import APIClient

from apps.securewise.models import (
    SecureWiseMembership,
    SecureWiseOrganization,
    SecureWiseProject,
    SecureWiseScan,
    SecureWiseScanEngineResult,
)

User = get_user_model()
pytestmark = pytest.mark.django_db


@pytest.fixture
def owner_a(db):
    return User.objects.create_user(username="prog_owner_a", email="prog_a@sw.test", password="TestPass123!")


@pytest.fixture
def owner_b(db):
    return User.objects.create_user(username="prog_owner_b", email="prog_b@sw.test", password="TestPass123!")


@pytest.fixture
def client_a(owner_a):
    c = APIClient()
    c.force_authenticate(user=owner_a)
    return c


@pytest.fixture
def client_b(owner_b):
    c = APIClient()
    c.force_authenticate(user=owner_b)
    return c


@pytest.fixture
def org_a(owner_a):
    o = SecureWiseOrganization.objects.create(name="ProgOrgA", slug="progorga", owner=owner_a)
    SecureWiseMembership.objects.create(organization=o, user=owner_a, role="owner")
    return o


@pytest.fixture
def org_b(owner_b):
    o = SecureWiseOrganization.objects.create(name="ProgOrgB", slug="progorgb", owner=owner_b)
    SecureWiseMembership.objects.create(organization=o, user=owner_b, role="owner")
    return o


@pytest.fixture
def project_a(org_a, owner_a):
    return SecureWiseProject.objects.create(organization=org_a, name="ProjA", slug="proja", created_by=owner_a)


@pytest.fixture
def scan_a(org_a, project_a, owner_a):
    scan = SecureWiseScan.objects.create(
        organization=org_a,
        project=project_a,
        scan_type="full",
        status="completed",
        progress=100,
        selected_engines=["sast", "sca"],
        triggered_by=owner_a,
    )
    SecureWiseScanEngineResult.objects.create(scan=scan, engine="sast", status="completed", findings_count=2)
    SecureWiseScanEngineResult.objects.create(
        scan=scan, engine="dast", status="skipped", skipped_reason="no target URL configured"
    )
    return scan


class TestScanProgressEndpoint:
    def test_owner_can_view_progress(self, client_a, scan_a):
        resp = client_a.get(f"/api/securewise/scans/{scan_a.id}/progress/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"
        assert data["progress"] == 100
        assert len(data["engines"]) == 2
        engine_names = {e["engine"] for e in data["engines"]}
        assert engine_names == {"sast", "dast"}

    def test_progress_exposes_diagnostics(self, client_a, org_a, project_a, owner_a):
        scan = SecureWiseScan.objects.create(
            organization=org_a,
            project=project_a,
            scan_type="dast",
            status="completed_partial",
            progress=100,
            triggered_by=owner_a,
        )
        SecureWiseScanEngineResult.objects.create(
            scan=scan,
            engine="dast",
            status="skipped",
            skipped_reason="Application could not be auto-started because the Docker build failed.",
            raw_summary={
                "dast_runtime_logs": "build step failed: missing dependency",
            },
        )

        resp = client_a.get(f"/api/securewise/scans/{scan.id}/progress/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["engines"][0]["diagnostics"]["log_excerpt"] == "build step failed: missing dependency"

    def test_other_org_user_cannot_view_progress(self, client_b, scan_a):
        resp = client_b.get(f"/api/securewise/scans/{scan_a.id}/progress/")
        assert resp.status_code == 404

    def test_anonymous_denied(self, scan_a):
        anon = APIClient()
        resp = anon.get(f"/api/securewise/scans/{scan_a.id}/progress/")
        assert resp.status_code in (401, 403)


class TestScanEngineResultsEndpoint:
    def test_owner_can_view_engine_results(self, client_a, scan_a):
        resp = client_a.get(f"/api/securewise/scans/{scan_a.id}/engine-results/")
        assert resp.status_code == 200
        data = resp.json()
        results = data if isinstance(data, list) else data.get("results", data)
        assert len(results) == 2
        engines = {r["engine"] for r in results}
        assert engines == {"sast", "dast"}

    def test_engine_results_expose_diagnostics(self, client_a, org_a, project_a, owner_a):
        scan = SecureWiseScan.objects.create(
            organization=org_a,
            project=project_a,
            scan_type="dast",
            status="completed_partial",
            progress=100,
            triggered_by=owner_a,
        )
        SecureWiseScanEngineResult.objects.create(
            scan=scan,
            engine="dast",
            status="skipped",
            skipped_reason="Application could not be auto-started because the Docker build failed.",
            raw_summary={
                "dast_runtime_logs": "build step failed: missing dependency",
            },
        )

        resp = client_a.get(f"/api/securewise/scans/{scan.id}/engine-results/")
        assert resp.status_code == 200
        data = resp.json()
        results = data if isinstance(data, list) else data.get("results", data)
        assert results[0]["diagnostics"]["log_excerpt"] == "build step failed: missing dependency"

    def test_other_org_user_cannot_view_engine_results(self, client_b, scan_a):
        resp = client_b.get(f"/api/securewise/scans/{scan_a.id}/engine-results/")
        assert resp.status_code == 404
