from __future__ import annotations

import hashlib
import os
import re
import stat
from pathlib import Path

_IGNORED_DIRECTORIES = {
    ".git",
    ".pytest_cache",
    ".venv",
    "__pycache__",
    "node_modules",
    "venv",
}
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_FILES = 100_000
_MAX_BYTES = 2 * 1024 * 1024 * 1024


def repository_tree_sha256(root: str | Path) -> str:
    """Return a stable digest for reviewed build content; reject filesystem links."""
    repository = Path(root).resolve(strict=True)
    if not repository.is_dir():
        raise ValueError("Reviewed runtime content must be a repository directory.")
    entries = []
    total_bytes = 0
    for current, directories, files in os.walk(repository, followlinks=False):
        current_path = Path(current)
        for name in list(directories):
            path = current_path / name
            if name in _IGNORED_DIRECTORIES:
                directories.remove(name)
            elif path.is_symlink():
                raise ValueError("Runtime repository content may not contain symlinks.")
        for name in files:
            path = current_path / name
            if path.is_symlink():
                raise ValueError("Runtime repository content may not contain symlinks.")
            if not path.is_file():
                continue
            relative = path.relative_to(repository).as_posix()
            entries.append((relative, path))
            if len(entries) > _MAX_FILES:
                raise ValueError("Runtime repository contains too many files for review.")
            total_bytes += path.stat().st_size
            if total_bytes > _MAX_BYTES:
                raise ValueError("Runtime repository exceeds the reviewed content size limit.")

    digest = hashlib.sha256()
    for relative, path in sorted(entries, key=lambda entry: entry[0]):
        encoded_path = relative.encode("utf-8")
        file_stat = path.stat()
        digest.update(len(encoded_path).to_bytes(4, "big"))
        digest.update(encoded_path)
        digest.update((stat.S_IMODE(file_stat.st_mode) & 0o777).to_bytes(2, "big"))
        digest.update(file_stat.st_size.to_bytes(8, "big"))
        with path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
    return digest.hexdigest()


def trusted_runtime_content(repository_id: str, root: str | Path) -> tuple[bool, str]:
    """Require an exact admin-reviewed content hash before executing build scripts."""
    if os.getenv("SECUREWISE_RUNTIME_BUILDS_ENABLED", "").strip().lower() != "true":
        return (
            False,
            "Runtime builds are disabled. Enable them only after verifying the dedicated worker host, rootless "
            "Docker daemon, resource quotas, and outbound network restrictions.",
        )
    try:
        actual_digest = repository_tree_sha256(root)
    except (OSError, ValueError) as exc:
        return False, str(exc)
    configured = os.getenv("SECUREWISE_TRUSTED_RUNTIME_CONTENT", "")
    trusted = {}
    for entry in configured.split(","):
        repository, separator, digest = entry.strip().partition("=")
        if separator and repository and _SHA256_RE.fullmatch(digest):
            trusted[repository] = digest
    if trusted.get(str(repository_id)) != actual_digest:
        return (
            False,
            "Runtime execution is disabled because this exact repository content has not been reviewed. "
            "Review the checked-out source, then configure its repository UUID and SHA-256 content digest "
            "in SECUREWISE_TRUSTED_RUNTIME_CONTENT.",
        )
    return True, actual_digest
