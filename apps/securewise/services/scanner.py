"""
SecureWise scanner service — orchestrates cloning a repository and running
the resolved set of real/fallback scan engines via ScannerOrchestrator.

Security rules:
- Tokens are decrypted only inside this runtime, never logged.
- Clone directory is always deleted after scan.
- Authenticated clone URL is never stored or logged.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from apps.securewise.scanners.orchestrator import ScannerOrchestrator
from apps.securewise.scanners.repository import clone_repository

logger = logging.getLogger(__name__)


class ScannerRunner:
    """
    Orchestrates cloning a repository and running one or more scan engines.
    """

    def run_scan(self, scan_id: str) -> None:
        """Entry point called by the view after saving the scan."""
        from django.utils import timezone

        from apps.securewise.models import SecureWiseAuditLog, SecureWiseFinding, SecureWiseScan

        try:
            scan = SecureWiseScan.objects.select_related(
                "repository", "repository__integration", "project", "organization", "policy"
            ).get(id=scan_id)
        except SecureWiseScan.DoesNotExist:
            logger.error("ScannerRunner: scan %s not found", scan_id)
            return

        scan.status = "running"
        scan.started_at = timezone.now()
        scan.progress = 0
        scan.save(update_fields=["status", "started_at", "progress"])

        SecureWiseAuditLog.objects.create(
            organization=scan.organization,
            user=scan.triggered_by,
            event="scan_started",
            target_type="SecureWiseScan",
            target_id=str(scan.id),
            detail={"scan_type": scan.scan_type, "project": str(scan.project_id)},
        )

        all_findings = []
        engine_meta: dict = {}
        any_engine_failed = False
        error_msg = ""

        try:
            with tempfile.TemporaryDirectory(prefix="sw_scan_") as tmpdir:
                repo_path = Path(tmpdir) / "repo"

                if scan.repository:
                    scan.status = "cloning"
                    scan.save(update_fields=["status"])
                    clone_repository(scan, repo_path, allowed_root=Path(tmpdir))
                else:
                    repo_path.mkdir(parents=True, exist_ok=True)

                orchestrator = ScannerOrchestrator()
                all_findings, engine_meta, any_engine_failed = orchestrator.run(scan, repo_path)
                scan.scanner_metadata = engine_meta
            # tempdir is cleaned up here automatically

        except Exception as exc:
            logger.exception("Scan %s failed during execution", scan_id)
            error_msg = str(exc)

        # Persist findings
        finding_objs = [
            SecureWiseFinding(
                scan=scan,
                project=scan.project,
                organization=scan.organization,
                title=f.title,
                description=f.description,
                severity=f.severity,
                confidence=f.confidence,
                scanner_type=f.scanner_type,
                file_path=f.file_path,
                line_number=f.line_number,
                endpoint=f.endpoint,
                cwe_id=f.cwe_id,
                owasp_category=f.owasp_category,
                risk=f.risk,
                impact=f.impact,
                recommendation=f.recommendation,
                bad_code_example=f.bad_code_example,
                fixed_code_example=f.fixed_code_example,
                evidence=f.evidence,
                fingerprint=f.fingerprint,
                status="open",
            )
            for f in all_findings
        ]
        SecureWiseFinding.objects.bulk_create(finding_objs, ignore_conflicts=True)

        if finding_objs:
            SecureWiseAuditLog.objects.create(
                organization=scan.organization,
                user=scan.triggered_by,
                event="finding_created",
                target_type="SecureWiseScan",
                target_id=str(scan.id),
                detail={"count": len(finding_objs)},
            )

        # Quality gate
        quality_gate_passed = self._evaluate_quality_gate(scan, all_findings)

        completed_at = timezone.now()
        duration = int((completed_at - scan.started_at).total_seconds())

        scan.refresh_from_db(fields=["status"])
        if scan.status == "cancelled":
            final_status = "cancelled"
        elif error_msg:
            final_status = "failed"
        elif any_engine_failed:
            final_status = "completed_with_warnings"
        else:
            final_status = "completed"

        scan.status = final_status
        scan.completed_at = completed_at
        scan.duration_seconds = duration
        scan.error_message = error_msg
        scan.quality_gate_passed = quality_gate_passed
        scan.progress = 100 if final_status != "cancelled" else scan.progress
        scan.save(
            update_fields=[
                "status",
                "completed_at",
                "duration_seconds",
                "error_message",
                "quality_gate_passed",
                "scanner_metadata",
                "progress",
            ]
        )

        SecureWiseAuditLog.objects.create(
            organization=scan.organization,
            user=scan.triggered_by,
            event="scan_completed" if final_status in ("completed", "completed_with_warnings") else "scan_failed",
            target_type="SecureWiseScan",
            target_id=str(scan.id),
            detail={
                "findings": len(all_findings),
                "quality_gate_passed": quality_gate_passed,
                "duration_seconds": duration,
                "status": final_status,
            },
        )

    # ------------------------------------------------------------------
    def _evaluate_quality_gate(self, scan, findings: list) -> bool:
        policy = scan.policy
        if not policy:
            return True
        severity_order = ["critical", "high", "medium", "low", "info"]
        fail_idx = severity_order.index(policy.fail_on_severity)
        for f in findings:
            fidx = severity_order.index(f.severity)
            if fidx <= fail_idx:
                return False
        critical_count = sum(1 for f in findings if f.severity == "critical")
        high_count = sum(1 for f in findings if f.severity == "high")
        if critical_count > policy.max_critical:
            return False
        if high_count > policy.max_high:
            return False
        return True
