"""Temporary, isolated workspace for runtime auto-start attempts."""

from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


class TemporaryWorkspace:
    """
    Context manager providing a scratch directory for anything the runtime
    manager needs to write (e.g. a generated Dockerfile for repos that don't
    have one). Never persisted, never committed, always cleaned up.
    """

    def __init__(self, prefix: str = "sw_runtime_"):
        self._prefix = prefix
        self._path: Path | None = None

    def __enter__(self) -> Path:
        self._path = Path(tempfile.mkdtemp(prefix=self._prefix))
        return self._path

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._path and self._path.exists():
            shutil.rmtree(self._path, ignore_errors=True)
        self._path = None
