"""
Central CWE / OWASP Top 10 mapping table.

Note: "OWASP Top 10 2025" is referenced informally by some stakeholders, but
as of writing the most recent *published* OWASP Top 10 edition is 2021.
We map every issue key to the stable OWASP Top 10 2021 category (A01..A10)
so findings remain consistent as new editions are ratified.
"""

from __future__ import annotations

import json
from pathlib import Path

_DATASET_PATH = Path(__file__).with_name("data") / "security_taxonomy_v1.json"
with _DATASET_PATH.open(encoding="utf-8") as _dataset_file:
    SECURITY_TAXONOMY = json.load(_dataset_file)

DATASET_VERSION = SECURITY_TAXONOMY["dataset_version"]
_MAPPING: dict[str, tuple[str, str]] = {
    key: tuple(value) for key, value in SECURITY_TAXONOMY["issue_mappings"].items()
}


def map_finding(issue_key: str) -> dict:
    """Return {"cwe_id": ..., "owasp_category": ...} for a given issue key.

    Unknown keys resolve to empty strings so callers can decide whether to
    keep hand-authored values instead.
    """
    cwe_id, owasp_category = _MAPPING.get(issue_key, ("", ""))
    return {"cwe_id": cwe_id, "owasp_category": owasp_category}


def taxonomy_metadata() -> dict[str, str]:
    return {
        "dataset_version": DATASET_VERSION,
        "cwe_top25_edition": SECURITY_TAXONOMY["cwe_top25_edition"],
        "owasp_edition": SECURITY_TAXONOMY["owasp_edition"],
        "cwe_source": SECURITY_TAXONOMY["cwe_source"],
    }
