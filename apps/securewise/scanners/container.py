"""
Container engine: best-effort image scanning. Only runs meaningfully when a
docker_image is configured, or optionally when both `docker` and `trivy` are
present and a Dockerfile exists (build + scan). Otherwise marks "skipped".
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import uuid
from pathlib import Path

from ..runtime import docker_runner
from .base import BaseScanner, ScannerResult
from .parsers.trivy_parser import parse_trivy_vuln_json

logger = logging.getLogger(__name__)


class ContainerScanner(BaseScanner):
    scanner_type = "container"

    def is_available(self) -> bool:
        return bool(shutil.which("trivy"))

    def run(self, repo_path: Path, scan_id: str, metadata: dict) -> ScannerResult:
        docker_image = metadata.get("runtime_docker_image") or metadata.get("docker_image")

        if docker_image and shutil.which("trivy"):
            result = self._scan_image(docker_image)
            result.metadata["image_source"] = (
                "runtime_build" if docker_image == metadata.get("runtime_docker_image") else "configured"
            )
            return result

        if docker_image and not shutil.which("trivy"):
            return ScannerResult(
                success=True,
                findings=[],
                status="skipped",
                skipped_reason="trivy not installed; cannot scan configured docker image in this environment",
                metadata={"raw_tool": "none", "docker_image": docker_image},
            )

        dockerfile_exists = (repo_path / "Dockerfile").exists()
        if dockerfile_exists and not metadata.get("trusted_runtime_repository"):
            return ScannerResult(
                success=True,
                findings=[],
                status="skipped",
                skipped_reason=(
                    "Image build was blocked because this exact repository content has not been reviewed. "
                    "Configure its repository UUID and SHA-256 content digest in "
                    "SECUREWISE_TRUSTED_RUNTIME_CONTENT after reviewing the source."
                ),
                metadata={"raw_tool": "none", "execution_mode": "trusted_build_required"},
            )

        if dockerfile_exists and shutil.which("trivy") and docker_runner.is_docker_available()[0]:
            return self._build_and_scan(repo_path)

        if dockerfile_exists:
            cli_available, cli_reason = docker_runner.is_docker_cli_available()
            _, daemon_reason = docker_runner.is_docker_available() if cli_available else (False, cli_reason)
            return ScannerResult(
                success=True,
                findings=[],
                status="skipped",
                skipped_reason=(
                    "Dockerfile present but container scanning could not build the image: "
                    f"{daemon_reason or 'Trivy is not installed'}. "
                    "Configure docker_image explicitly or run the scan on a Docker-enabled worker."
                ),
                metadata={"raw_tool": "none"},
            )

        return ScannerResult(
            success=True,
            findings=[],
            status="skipped",
            skipped_reason="no docker image configured",
            metadata={"raw_tool": "none"},
        )

    def _scan_image(self, image: str) -> ScannerResult:
        try:
            proc = subprocess.run(
                ["trivy", "image", "--format", "json", image],
                capture_output=True,
                timeout=300,
            )
            if proc.returncode != 0 and not proc.stdout:
                return ScannerResult(
                    success=False,
                    error=(proc.stderr or b"Trivy image scan failed").decode("utf-8", errors="replace")[-2000:],
                    status="failed",
                    metadata={"raw_tool": "trivy", "image": image},
                )
            data = json.loads(proc.stdout or b"{}")
            findings = parse_trivy_vuln_json(data, image)
            for f in findings:
                f.scanner_type = "container"
            return ScannerResult(
                success=True,
                findings=findings,
                metadata={"raw_tool": "trivy", "image": image, "tool_exit_code": proc.returncode},
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("trivy image scan failed")
            return ScannerResult(success=False, error=str(exc), status="failed", metadata={"raw_tool": "trivy"})

    def _build_and_scan(self, repo_path: Path) -> ScannerResult:
        image_tag = f"securewise-scan-tmp:{uuid.uuid4().hex}"
        try:
            build = subprocess.run(
                ["docker", "build", "-t", image_tag, str(repo_path)],
                capture_output=True,
                timeout=300,
            )
            if build.returncode != 0:
                return ScannerResult(
                    success=True,
                    findings=[],
                    status="skipped",
                    skipped_reason="docker build failed; container scan skipped",
                    metadata={"raw_tool": "docker+trivy"},
                )
            return self._scan_image(image_tag)
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("docker build for container scan failed")
            return ScannerResult(
                success=True,
                findings=[],
                status="skipped",
                skipped_reason=f"docker build/scan unavailable: {exc}",
                metadata={"raw_tool": "docker+trivy"},
            )
        finally:
            try:
                subprocess.run(["docker", "rmi", "-f", image_tag], capture_output=True, timeout=60)
            except (OSError, subprocess.SubprocessError) as exc:
                logger.warning("Could not remove temporary image %s: %s", image_tag, exc)
