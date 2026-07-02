# SecureWise — Plugin Architecture Design

> Generated: 2026-07-02 · Branch: `feature/securewise-production-scans`

---

## 1. Problem Statement

Today, adding a new scanner to SecureWise requires:
1. Writing a new Python class in `apps/securewise/scanners/`
2. Adding it to the `_ENGINE_CLASSES` dictionary in `orchestrator.py`
3. Adding the engine name to `ENGINE_CHOICES` and `SCAN_TYPE_CHOICES` in `models.py`
4. Deploying the updated backend

This is bespoke engineering for every integration. There is no documented interface contract, no external plugin mechanism, and no way for customers or third-party vendors to add scanners without modifying SecureWise's core codebase.

## 2. Current Interface Analysis

The existing `BaseScanner` is minimal but well-shaped:

```python
class BaseScanner(ABC):
    scanner_type: str = "unknown"
    def is_available(self) -> bool: return True
    @abstractmethod
    def run(self, repo_path: Path, scan_id: str, metadata: dict) -> ScannerResult: ...
```

`ScannerFinding` and `ScannerResult` are pure dataclasses with no Django dependencies — they're already serialization-friendly. This is a good foundation.

## 3. Proposed Plugin Interface

### 3.1 Scanner Plugin Protocol

```python
# apps/securewise/scanners/plugin_interface.py

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Sequence

# Re-export existing data structures (no breaking change)
from .base import ScannerFinding, ScannerResult


class ScannerCapability(Enum):
    """What kind of scanning this plugin performs."""
    SAST = "sast"
    SCA = "sca"
    SECRETS = "secrets"
    DAST = "dast"
    IAC = "iac"
    CONTAINER = "container"
    API = "api"
    CUSTOM = "custom"


class ScanTarget(Enum):
    """What the scanner operates on."""
    SOURCE_CODE = "source_code"       # needs cloned repo
    DOCKER_IMAGE = "docker_image"     # needs image reference
    LIVE_URL = "live_url"             # needs target URL
    API_SPEC = "api_spec"             # needs OpenAPI spec
    ARTIFACT = "artifact"             # needs build artifact


@dataclass(frozen=True)
class ScannerPluginManifest:
    """Declarative metadata about a scanner plugin."""
    name: str                                    # e.g. "semgrep", "checkmarx-sast", "custom-sqli-scanner"
    version: str                                 # semver, e.g. "1.0.0"
    vendor: str                                  # e.g. "SecureWise", "Checkmarx", "Acme Corp"
    capability: ScannerCapability                 # primary capability
    scan_targets: tuple[ScanTarget, ...]         # what inputs it needs
    supported_languages: tuple[str, ...] = ()    # e.g. ("python", "javascript") — empty = all
    requires_network: bool = False               # does it call external APIs?
    requires_binary: str = ""                    # external tool name (e.g. "semgrep", "trivy")
    max_timeout_seconds: int = 300               # hard timeout for this scanner
    description: str = ""
    documentation_url: str = ""


class ScannerPlugin(ABC):
    """
    Contract that all scanner plugins must implement.

    Lifecycle:
    1. Orchestrator calls `manifest()` to get plugin metadata
    2. Orchestrator calls `is_available()` to check runtime prerequisites
    3. Orchestrator calls `run()` with appropriate context
    4. Orchestrator validates returned findings (fingerprint stability, etc.)
    """

    @abstractmethod
    def manifest(self) -> ScannerPluginManifest:
        """Return static metadata about this scanner."""
        ...

    def is_available(self) -> bool:
        """
        Return True if this scanner can run in the current environment.
        Check for required binaries, credentials, network access, etc.
        Default: True (always available).
        """
        return True

    def validate_config(self, config: dict[str, Any]) -> list[str]:
        """
        Validate scanner-specific configuration.
        Returns a list of error messages (empty = valid).
        Override to add custom validation.
        """
        return []

    @abstractmethod
    def run(self, context: ScanContext) -> ScannerResult:
        """
        Execute the scan and return normalized findings.

        FINGERPRINT CONTRACT:
        Every ScannerFinding.fingerprint MUST be:
        - Content-stable: same code/config → same fingerprint across runs
        - NOT scan-ID-derived: must not contain the scan_id
        - Unique within this scanner: two distinct issues must have distinct fingerprints
        - Prefixed with scanner name: e.g. "semgrep-python.lang.security.audit.sqli-path/to/file-42"

        Violating this contract breaks deduplication (ADR-0002).
        """
        ...

    def cleanup(self) -> None:
        """
        Called after run() completes (success or failure).
        Clean up temp files, connections, etc.
        Default: no-op.
        """
        pass


@dataclass(frozen=True)
class ScanContext:
    """
    Immutable context passed to ScannerPlugin.run().
    Plugins should not access Django models directly.
    """
    scan_id: str
    repo_path: Path                              # cloned repo root (may not exist for DAST/container)
    target_url: str = ""                         # for DAST
    docker_image: str = ""                       # for container scanning
    api_spec_path: str = ""                      # for API scanning
    branch: str = ""
    commit_sha: str = ""
    config: dict[str, Any] = field(default_factory=dict)  # scanner-specific config
    languages: tuple[str, ...] = ()              # hint: detected languages in repo
    timeout_seconds: int = 300
```

### 3.2 Plugin Registry

```python
# apps/securewise/scanners/registry.py

from __future__ import annotations
import importlib
import logging
from typing import Type

from django.conf import settings

from .plugin_interface import ScannerPlugin, ScannerPluginManifest

logger = logging.getLogger(__name__)


class PluginRegistry:
    """
    Thread-safe singleton registry for scanner plugins.
    Plugins can be registered via:
    1. Built-in registration (hardcoded in code)
    2. Django settings (SECUREWISE_SCANNER_PLUGINS list of dotted paths)
    3. Entry points (setuptools entry_points, future)
    """

    _instance: PluginRegistry | None = None
    _plugins: dict[str, Type[ScannerPlugin]]

    def __new__(cls) -> PluginRegistry:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._plugins = {}
        return cls._instance

    def register(self, plugin_class: Type[ScannerPlugin]) -> None:
        """Register a scanner plugin class."""
        instance = plugin_class()
        manifest = instance.manifest()
        name = manifest.name
        if name in self._plugins:
            logger.warning("Scanner plugin '%s' already registered; overwriting.", name)
        self._plugins[name] = plugin_class
        logger.info("Registered scanner plugin: %s v%s (%s)", name, manifest.version, manifest.vendor)

    def unregister(self, name: str) -> None:
        self._plugins.pop(name, None)

    def get(self, name: str) -> Type[ScannerPlugin] | None:
        return self._plugins.get(name)

    def get_all(self) -> dict[str, Type[ScannerPlugin]]:
        return dict(self._plugins)

    def get_available(self) -> dict[str, ScannerPlugin]:
        """Return instantiated plugins that report is_available() = True."""
        available = {}
        for name, cls in self._plugins.items():
            try:
                instance = cls()
                if instance.is_available():
                    available[name] = instance
            except Exception:
                logger.exception("Failed to instantiate scanner plugin '%s'", name)
        return available

    def load_from_settings(self) -> None:
        """Load plugins listed in settings.SECUREWISE_SCANNER_PLUGINS."""
        plugin_paths = getattr(settings, "SECUREWISE_SCANNER_PLUGINS", [])
        for dotted_path in plugin_paths:
            try:
                module_path, class_name = dotted_path.rsplit(".", 1)
                module = importlib.import_module(module_path)
                plugin_class = getattr(module, class_name)
                self.register(plugin_class)
            except Exception:
                logger.exception("Failed to load scanner plugin: %s", dotted_path)

    def load_from_entry_points(self) -> None:
        """Load plugins registered via setuptools entry_points."""
        try:
            from importlib.metadata import entry_points
            eps = entry_points(group="securewise.scanners")
            for ep in eps:
                try:
                    plugin_class = ep.load()
                    self.register(plugin_class)
                except Exception:
                    logger.exception("Failed to load entry_point plugin: %s", ep.name)
        except Exception:
            pass  # importlib.metadata not available or no entry points


# Module-level singleton
registry = PluginRegistry()
```

### 3.3 Adapter for Existing Scanners

Existing `BaseScanner` subclasses should be wrapped without rewriting them:

```python
# Example: wrapping existing SastScanner as a plugin

class SastScannerPlugin(ScannerPlugin):
    def manifest(self) -> ScannerPluginManifest:
        return ScannerPluginManifest(
            name="securewise-sast",
            version="1.0.0",
            vendor="SecureWise",
            capability=ScannerCapability.SAST,
            scan_targets=(ScanTarget.SOURCE_CODE,),
            supported_languages=("python", "javascript", "java", "go"),
            requires_binary="semgrep",  # preferred but has fallback
            description="SAST via Semgrep (bundled offline rules) with regex fallback",
        )

    def is_available(self) -> bool:
        return True  # has fallback

    def run(self, context: ScanContext) -> ScannerResult:
        from .sast import SastScanner
        scanner = SastScanner()
        return scanner.run(context.repo_path, context.scan_id, {})
```

### 3.4 Third-Party Plugin Examples

**Checkmarx SAST:**
```python
class CheckmarxSastPlugin(ScannerPlugin):
    def manifest(self) -> ScannerPluginManifest:
        return ScannerPluginManifest(
            name="checkmarx-sast",
            version="1.0.0",
            vendor="Checkmarx",
            capability=ScannerCapability.SAST,
            scan_targets=(ScanTarget.SOURCE_CODE,),
            requires_network=True,
            max_timeout_seconds=600,
            description="Checkmarx SAST cloud scanning",
        )

    def is_available(self) -> bool:
        return bool(os.environ.get("CHECKMARX_API_TOKEN"))

    def validate_config(self, config: dict) -> list[str]:
        errors = []
        if not config.get("project_id"):
            errors.append("Checkmarx project_id is required")
        return errors

    def run(self, context: ScanContext) -> ScannerResult:
        # Upload source, trigger scan, poll for results, parse SARIF output
        ...
```

**Nuclei (DAST):**
```python
class NucleiPlugin(ScannerPlugin):
    def manifest(self) -> ScannerPluginManifest:
        return ScannerPluginManifest(
            name="nuclei",
            version="1.0.0",
            vendor="ProjectDiscovery",
            capability=ScannerCapability.DAST,
            scan_targets=(ScanTarget.LIVE_URL,),
            requires_binary="nuclei",
            max_timeout_seconds=600,
        )
    ...
```

## 4. Orchestrator Evolution

The `ScannerOrchestrator` should be updated to:

1. **Load plugins from registry** instead of hardcoded `_ENGINE_CLASSES`
2. **Match plugins to scan context** based on `ScanTarget` and `ScannerCapability`
3. **Validate fingerprints** post-scan (reject findings with scan-ID-derived or empty fingerprints)
4. **Enforce timeouts** per-plugin based on `max_timeout_seconds`
5. **Support parallel plugin execution** (eventually, via thread pool or async)

```python
# Pseudocode for evolved orchestrator
class ScannerOrchestrator:
    def resolve_plugins(self, scan, repo_path: Path) -> list[ScannerPlugin]:
        available = registry.get_available()
        selected = []
        for name, plugin in available.items():
            manifest = plugin.manifest()
            if self._matches_scan(scan, manifest, repo_path):
                selected.append(plugin)
        return selected

    def _matches_scan(self, scan, manifest, repo_path) -> bool:
        # Engine selection logic based on scan_type, available targets, etc.
        ...
```

## 5. Migration Path

1. **Phase 1:** Define `ScannerPlugin` interface and `PluginRegistry` (no behavior change)
2. **Phase 2:** Wrap all 7 existing scanners as plugins; orchestrator uses registry
3. **Phase 3:** Support `settings.SECUREWISE_SCANNER_PLUGINS` for configuration-based loading
4. **Phase 4:** Support `entry_points` for pip-installable third-party plugins
5. **Phase 5:** Plugin marketplace / catalog in the UI

## 6. SARIF Interoperability

Many commercial tools (CodeQL, Checkmarx, Veracode, Semgrep) output SARIF (Static Analysis Results Interchange Format). A generic SARIF parser would allow any SARIF-producing tool to be integrated:

```python
class SarifImportPlugin(ScannerPlugin):
    """Generic plugin that imports pre-generated SARIF files."""
    def run(self, context: ScanContext) -> ScannerResult:
        sarif_path = Path(context.config.get("sarif_path", ""))
        # Parse SARIF, map to ScannerFinding with stable fingerprints
        ...
```

This would be the fastest path to supporting tools like CodeQL, Veracode, and Sonar without writing individual integrations.
