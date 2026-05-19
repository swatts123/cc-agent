"""Path-resolution helpers shared by the file tools."""

from __future__ import annotations

from pathlib import Path


class WorkspaceError(Exception):
    """Raised when a path resolves outside the workspace root."""


def resolve_inside_workspace(workspace_root: Path, raw_path: str) -> Path:
    """Resolve `raw_path` and ensure the result is inside `workspace_root`.

    Cross-platform: uses Path.resolve() which canonicalizes via realpath on POSIX
    and GetFinalPathNameByHandle on Windows, so symlink and junction escapes are
    caught on both.
    """
    root = workspace_root.resolve()
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = (root / candidate)
    # strict=False lets us resolve a path that doesn't exist yet (for write/edit creating files)
    resolved = candidate.resolve(strict=False)

    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise WorkspaceError(
            f"path '{raw_path}' resolves to '{resolved}' which is outside workspace '{root}'"
        ) from exc

    return resolved
