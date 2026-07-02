"""SecureWise — idempotency test for the demo data seed command."""

from __future__ import annotations

from django.core.management import call_command

import pytest

from apps.securewise.models import (
    SecureWiseFinding,
    SecureWiseOrganization,
    SecureWiseScan,
    SecureWiseScanEngineResult,
)

pytestmark = pytest.mark.django_db


class TestSeedSecurewiseDemo:
    def test_seed_command_creates_data(self):
        call_command("seed_securewise_demo")
        assert SecureWiseOrganization.objects.filter(slug="securewise-demo-org").exists()
        scan = SecureWiseScan.objects.filter(project__slug="gw-backend-demo").first()
        assert scan is not None
        assert SecureWiseScanEngineResult.objects.filter(scan=scan).count() == 7
        assert SecureWiseFinding.objects.filter(scan=scan).count() >= 1

    def test_seed_command_is_idempotent(self):
        call_command("seed_securewise_demo")
        org_count_first = SecureWiseOrganization.objects.filter(slug="securewise-demo-org").count()
        scan_count_first = SecureWiseScan.objects.filter(project__slug="gw-backend-demo").count()

        call_command("seed_securewise_demo")

        org_count_second = SecureWiseOrganization.objects.filter(slug="securewise-demo-org").count()
        scan_count_second = SecureWiseScan.objects.filter(project__slug="gw-backend-demo").count()

        assert org_count_first == org_count_second == 1
        assert scan_count_first == scan_count_second == 1

    def test_seed_command_does_not_raise_on_repeated_calls(self):
        call_command("seed_securewise_demo")
        call_command("seed_securewise_demo")
        call_command("seed_securewise_demo")
