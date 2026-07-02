"""
Idempotent demo data seeder for SecureWise SASP.

Usage:
    python manage.py seed_securewise_demo
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.securewise.models import (
    SecureWiseFinding,
    SecureWiseMembership,
    SecureWiseOrganization,
    SecureWiseProject,
    SecureWiseRepository,
    SecureWiseScan,
    SecureWiseScanEngineResult,
)
from apps.securewise.scanners.recommendation import RecommendationEngine

User = get_user_model()

DEMO_REPO_URL = "https://github.com/roshanguptamca/gw-backend"


class Command(BaseCommand):
    help = "Seed idempotent SecureWise demo data (organization, project, repository, scan, findings)."

    def handle(self, *args, **options):
        created_summary = []

        owner, owner_created = User.objects.get_or_create(
            username="securewise_demo_owner",
            defaults={"email": "securewise-demo@example.com"},
        )
        if owner_created:
            owner.set_unusable_password()
            owner.save()
            created_summary.append("user: securewise_demo_owner")

        org, org_created = SecureWiseOrganization.objects.get_or_create(
            slug="securewise-demo-org",
            defaults={"name": "SecureWise Demo Org", "owner": owner},
        )
        if org_created:
            created_summary.append(f"organization: {org.name}")

        _, membership_created = SecureWiseMembership.objects.get_or_create(
            organization=org, user=owner, defaults={"role": "owner"}
        )
        if membership_created:
            created_summary.append("membership: owner")

        project, project_created = SecureWiseProject.objects.get_or_create(
            organization=org,
            slug="gw-backend-demo",
            defaults={"name": "GW Backend (Demo)", "created_by": owner},
        )
        if project_created:
            created_summary.append(f"project: {project.name}")

        repository, repo_created = SecureWiseRepository.objects.get_or_create(
            organization=org,
            project=project,
            repository_url=DEMO_REPO_URL,
            defaults={
                "name": "gw-backend",
                "clone_url": DEMO_REPO_URL + ".git",
                "provider": "github",
                "visibility": "public",
                "access_mode": "public",
                "created_by": owner,
            },
        )
        if repo_created:
            created_summary.append(f"repository: {repository.name}")

        scan, scan_created = SecureWiseScan.objects.get_or_create(
            organization=org,
            project=project,
            repository=repository,
            scan_type="full",
            branch="main",
            defaults={
                "status": "completed",
                "triggered_by": owner,
                "started_at": timezone.now(),
                "completed_at": timezone.now(),
                "duration_seconds": 42,
                "progress": 100,
                "selected_engines": ["sast", "sca", "secrets", "iac", "container", "api", "dast"],
                "quality_gate_passed": True,
            },
        )
        if scan_created:
            created_summary.append(f"scan: {scan.id}")
            self._seed_engine_results(scan)
            self._seed_findings(scan, project, org)

        self.stdout.write(self.style.SUCCESS("SecureWise demo seed complete."))
        if created_summary:
            self.stdout.write("Created:")
            for line in created_summary:
                self.stdout.write(f"  - {line}")
        else:
            self.stdout.write("Nothing new to create (already seeded).")

    # ------------------------------------------------------------------
    def _seed_engine_results(self, scan):
        engines_ran = [
            ("sast", "completed", 3, {"raw_tool": "fallback-rules", "files_scanned": 42}),
            ("sca", "completed", 2, {"raw_tool": "fallback-lockfile-parser", "dependencies_parsed": 18}),
            ("secrets", "completed", 1, {"raw_tool": "gitleaks", "matches": 1}),
            ("iac", "completed", 1, {"raw_tool": "fallback-iac-checks", "files_scanned": 2}),
            ("container", "skipped", 0, {"raw_tool": "none"}),
            ("api", "skipped", 0, {"raw_tool": "none"}),
            ("dast", "skipped", 0, {"raw_tool": "none"}),
        ]
        for engine, status, count, raw_summary in engines_ran:
            skipped_reason = ""
            if status == "skipped":
                skipped_reason = {
                    "container": "no docker image configured",
                    "api": "no OpenAPI/Swagger spec found",
                    "dast": "no target URL configured",
                }.get(engine, "")
            SecureWiseScanEngineResult.objects.create(
                scan=scan,
                engine=engine,
                status=status,
                started_at=timezone.now(),
                completed_at=timezone.now(),
                duration_seconds=5,
                findings_count=count,
                skipped_reason=skipped_reason,
                raw_summary=raw_summary,
            )

    def _seed_findings(self, scan, project, org):
        demo_findings = [
            ("sast", "hardcoded_secrets", "python", "config/settings_demo.py", 12, "high"),
            ("sast", "sql_injection", "python", "app/db/queries_demo.py", 58, "critical"),
            ("sca", "vulnerable_dependency", "generic", "requirements.txt", None, "high"),
            ("secrets", "leaked_secret", "generic", ".env.demo", 3, "critical"),
            ("iac", "insecure_dockerfile", "generic", "Dockerfile", None, "medium"),
        ]
        for scanner_type, issue_key, language, file_path, line_number, severity in demo_findings:
            rec = RecommendationEngine.get_recommendation(issue_key, language)
            SecureWiseFinding.objects.create(
                scan=scan,
                project=project,
                organization=org,
                title=rec["what"],
                description=rec["why"],
                severity=severity,
                confidence="high",
                scanner_type=scanner_type,
                file_path=file_path,
                line_number=line_number,
                cwe_id=rec["cwe_id"],
                owasp_category=rec["owasp_category"],
                risk=rec["why"],
                impact=rec["why"],
                recommendation=rec["recommendation"],
                bad_code_example=rec["bad_code_example"],
                fixed_code_example=rec["fixed_code_example"],
                evidence={"raw_tool": "demo-seed", "issue_key": issue_key},
                fingerprint=f"demo-{issue_key}-{file_path}-{line_number}",
                status="open",
            )
