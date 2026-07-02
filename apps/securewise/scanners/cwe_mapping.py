"""
Central CWE / OWASP Top 10 mapping table.

Note: "OWASP Top 10 2025" is referenced informally by some stakeholders, but
as of writing the most recent *published* OWASP Top 10 edition is 2021.
We map every issue key to the stable OWASP Top 10 2021 category (A01..A10)
so findings remain consistent as new editions are ratified.
"""

from __future__ import annotations

# issue_key -> (cwe_id, owasp_category)
_MAPPING: dict[str, tuple[str, str]] = {
    "sql_injection": ("CWE-89", "A03:2021"),
    "xss": ("CWE-79", "A03:2021"),
    "missing_authorization": ("CWE-862", "A01:2021"),
    "hardcoded_secret": ("CWE-798", "A02:2021"),
    "weak_crypto": ("CWE-327", "A02:2021"),
    "ssrf": ("CWE-918", "A10:2021"),
    "path_traversal": ("CWE-22", "A01:2021"),
    "command_injection": ("CWE-78", "A03:2021"),
    "insecure_deserialization": ("CWE-502", "A08:2021"),
    "xxe": ("CWE-611", "A05:2021"),
    "csrf": ("CWE-352", "A01:2021"),
    "open_redirect": ("CWE-601", "A01:2021"),
    "missing_security_headers": ("CWE-693", "A05:2021"),
    "insecure_cors": ("CWE-942", "A05:2021"),
    "vulnerable_dependency": ("CWE-1104", "A06:2021"),
    "iac_misconfiguration": ("CWE-16", "A05:2021"),
    "weak_tls": ("CWE-326", "A02:2021"),
    "prototype_pollution": ("CWE-1321", "A03:2021"),
}


def map_finding(issue_key: str) -> dict:
    """Return {"cwe_id": ..., "owasp_category": ...} for a given issue key.

    Unknown keys resolve to empty strings so callers can decide whether to
    keep hand-authored values instead.
    """
    cwe_id, owasp_category = _MAPPING.get(issue_key, ("", ""))
    return {"cwe_id": cwe_id, "owasp_category": owasp_category}
