"""
SecureWise Smart Repository Scan — Application Discovery Engine.

Given a cloned repository, statically inspect it (no code execution) and
produce an `ApplicationRunPlan` describing what kind of application it is,
how it could plausibly be built/started, and whether a DAST target can be
auto-discovered by starting it in an isolated runtime.

See docs/SMART_REPO_SCAN.md for the full flow and docs/CODE_UNDERSTANDING_ENGINE.md
for the original design intent this implements a first real version of.
"""

from .engine import ApplicationDiscoveryEngine
from .run_plan import ApplicationRunPlan

__all__ = ["ApplicationDiscoveryEngine", "ApplicationRunPlan"]
