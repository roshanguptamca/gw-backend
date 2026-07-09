"""
Small helper for labeling *how* a scan engine actually produced its results.

This exists so SecureWise never silently presents a fallback/heuristic or
passive-only check as if it were a full, real security tool run. See
docs/CURRENT_SECUREWISE_REVIEW.md and docs/IMPLEMENTATION_ROADMAP.md (Phase 1)
for the full context — this module is an intentionally small, additive first
step; a proper `mode` column on SecureWiseScanEngineResult/SecureWiseFinding
is tracked as backlog item SW-101 for a later migration-backed follow-up.
"""

from __future__ import annotations

# `raw_tool` values that indicate a real, external security tool actually ran.
REAL_TOOL_MARKERS = {
    "semgrep",
    "trivy",
    "gitleaks",
    "docker+trivy",
    "zap",
}

# `raw_tool` values that indicate a deterministic-but-weaker, non-external-tool
# fallback ran instead of the real scanner (still genuine analysis, just not
# as thorough as the real tool).
FALLBACK_HEURISTIC_MARKERS = {
    "fallback-rules",
    "fallback-lockfile-parser",
    "fallback-regex",
    "fallback-iac-checks",
}

# `raw_tool` values that indicate only a passive/static check ran (no active
# dynamic testing against a live target).
PASSIVE_ONLY_MARKERS = {
    "requests-passive-dast",
    "openapi-static-checks",
}

# `raw_tool` values that indicate nothing actually ran (engine was skipped).
NOT_CONFIGURED_MARKERS = {"none", ""}


def classify_raw_tool(raw_tool: str | None) -> str:
    """
    Map a scanner's `metadata["raw_tool"]` value to one of:
    "real_tool" | "fallback_heuristic" | "passive_only" | "not_configured" | "unknown"
    """
    value = (raw_tool or "").strip()
    if value in REAL_TOOL_MARKERS:
        return "real_tool"
    if value in FALLBACK_HEURISTIC_MARKERS:
        return "fallback_heuristic"
    if value in PASSIVE_ONLY_MARKERS:
        return "passive_only"
    if value in NOT_CONFIGURED_MARKERS:
        return "not_configured"
    return "unknown"


def engine_ran_in_real_tool_mode(raw_summary: dict | None) -> bool:
    """True only if this engine's `raw_summary` shows a real external tool ran."""
    if not raw_summary:
        return False
    return classify_raw_tool(raw_summary.get("raw_tool")) == "real_tool"
