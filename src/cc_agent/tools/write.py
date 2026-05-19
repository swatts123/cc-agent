"""Write tool: full-file write with stale-write protection."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import Tool, ToolResult
from .workspace import WorkspaceError, resolve_inside_workspace


class WriteTool(Tool):
    name = "write"
    description = (
        "Write contents to a file in the workspace. Overwrites if the file exists. "
        "If the file already exists, you MUST have called `read` on it in this session first."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path (absolute or relative to workspace)."},
            "content": {"type": "string", "description": "Full contents to write."},
        },
        "required": ["path", "content"],
    }

    def __init__(self, workspace_root: Path, read_tracker: set[Path]) -> None:
        self._workspace = workspace_root
        self._read_tracker = read_tracker

    def run(self, **kwargs: Any) -> ToolResult:
        path_str = kwargs.get("path")
        content = kwargs.get("content")
        if not isinstance(path_str, str):
            return ToolResult(output="'path' is required and must be a string", is_error=True)
        if not isinstance(content, str):
            return ToolResult(output="'content' is required and must be a string", is_error=True)

        try:
            target = resolve_inside_workspace(self._workspace, path_str)
        except WorkspaceError as exc:
            return ToolResult(output=str(exc), is_error=True)

        if target.exists() and target not in self._read_tracker:
            return ToolResult(
                output=(
                    f"refusing to overwrite existing file without prior read in this session: {target}. "
                    "Call `read` on the file first."
                ),
                is_error=True,
            )
        if target.is_dir():
            return ToolResult(output=f"path is a directory, not a file: {target}", is_error=True)

        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            target.write_text(content, encoding="utf-8")
        except OSError as exc:
            return ToolResult(output=f"write failed: {exc}", is_error=True)

        # After a successful write, treat the file as read for future writes.
        self._read_tracker.add(target)

        return ToolResult(
            output=f"wrote {len(content)} chars to {target}",
            metadata={"path": str(target), "bytes": len(content.encode('utf-8'))},
        )
