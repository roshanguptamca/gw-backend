"""
Tests for apps.securewise.scanners.mode_labels — the small helper that
labels how a scan engine actually produced its results (real tool vs
fallback heuristic vs passive-only vs not configured), used to prevent
SecureWise from ever silently presenting a fallback/passive run as a full
real scan. See docs/CURRENT_SECUREWISE_REVIEW.md and
docs/IMPLEMENTATION_ROADMAP.md (Phase 1).
"""

from apps.securewise.scanners.mode_labels import classify_raw_tool, engine_ran_in_real_tool_mode


class TestClassifyRawTool:
    def test_real_tools_are_classified_correctly(self):
        for tool in ("semgrep", "trivy", "gitleaks", "docker+trivy"):
            assert classify_raw_tool(tool) == "real_tool"

    def test_fallback_heuristics_are_classified_correctly(self):
        for tool in (
            "fallback-rules",
            "fallback-lockfile-parser",
            "fallback-regex",
            "fallback-iac-checks",
        ):
            assert classify_raw_tool(tool) == "fallback_heuristic"

    def test_passive_only_tools_are_classified_correctly(self):
        for tool in ("requests-passive-dast", "openapi-static-checks"):
            assert classify_raw_tool(tool) == "passive_only"

    def test_not_configured_variants(self):
        assert classify_raw_tool("none") == "not_configured"
        assert classify_raw_tool("") == "not_configured"
        assert classify_raw_tool(None) == "not_configured"

    def test_unknown_tool_name_falls_back_to_unknown(self):
        assert classify_raw_tool("some-future-tool") == "unknown"


class TestEngineRanInRealToolMode:
    def test_true_when_raw_tool_is_real(self):
        assert engine_ran_in_real_tool_mode({"raw_tool": "trivy"}) is True

    def test_false_when_raw_tool_is_fallback(self):
        assert engine_ran_in_real_tool_mode({"raw_tool": "fallback-regex"}) is False

    def test_false_when_raw_summary_missing_or_empty(self):
        assert engine_ran_in_real_tool_mode(None) is False
        assert engine_ran_in_real_tool_mode({}) is False
