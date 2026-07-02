"""
Base data classes and scanner interface shared by all SecureWise scan engines.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import List


@dataclass
class ScannerFinding:
    title: str
    description: str
    severity: str  # critical | high | medium | low | info
    confidence: str  # very_high | high | medium | low
    scanner_type: str
    file_path: str = ""
    line_number: int | None = None
    code_snippet: str = ""
    endpoint: str = ""
    cwe_id: str = ""
    owasp_category: str = ""
    risk: str = ""
    impact: str = ""
    recommendation: str = ""
    bad_code_example: str = ""
    fixed_code_example: str = ""
    evidence: dict = field(default_factory=dict)
    fingerprint: str = field(default_factory=lambda: uuid.uuid4().hex)


@dataclass
class ScannerResult:
    success: bool
    findings: List[ScannerFinding] = field(default_factory=list)
    error: str = ""
    metadata: dict = field(default_factory=dict)
    status: str = "completed"  # completed | skipped | failed
    skipped_reason: str = ""


class BaseScanner(ABC):
    """Common interface for all SecureWise scan engines."""

    scanner_type: str = "unknown"

    def is_available(self) -> bool:
        """
        Return True if a real underlying tool is present on PATH, or True
        for scanners that always have a meaningful fallback engine.
        """
        return True

    @abstractmethod
    def run(self, repo_path: Path, scan_id: str, metadata: dict) -> ScannerResult:
        raise NotImplementedError
