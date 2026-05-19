"""Read tool: line-numbered, binary-aware, capped-byte file reader."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..config import FileToolConfig
from .base import Tool, ToolResult
from .workspace import WorkspaceError, resolve_inside_workspace

_BINARY_SNIFF_BYTES = 4096


def _looks_binary(blob: bytes) -> bool:
    if b"\x00" in blob:
        return True
    try:
        blob.decode("utf-8")
        return False
    except UnicodeDecodeError:
        return True


class ReadTool(Tool):
    name = "read"
    description = (
        "Read a text file from the workspace. Returns line-numbered output. "
        "Use this before writing or editing any file."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to the file. Absolute or relative to the workspace root.",
            },
            "offset": {
                "type": "integer",
                "description": "Line number to start reading from (1-indexed). Default 1.",
                "minimum": 1,
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of lines to read. Default 2000.",
                "minimum": 1,
            },
        },
        "required": ["path"],
    }

    def __init__(
        self,
        workspace_root: Path,
        config: FileToolConfig,
        read_tracker: set[Path],
    ) -> None:
        self._workspace = workspace_root
        self._config = config
        self._read_tracker = read_tracker  # shared with WriteTool/EditTool

    def run(self, **kwargs: Any) -> ToolResult:
        path_str = kwargs.get("path")
        if not isinstance(path_str, str):
            return ToolResult(output="'path' is required and must be a string", is_error=True)
        offset = int(kwargs.get("offset", 1))
        limit = int(kwargs.get("limit", 2000))

        try:
            target = resolve_inside_workspace(self._workspace, path_str)
        except WorkspaceError as exc:
            return ToolResult(output=str(exc), is_error=True)

        if not target.exists():
            return ToolResult(output=f"file not found: {target}", is_error=True)
        if target.is_dir():
            return ToolResult(output=f"path is a directory, not a file: {target}", is_error=True)

        try:
            with target.open("rb") as fh:
                head = fh.read(_BINARY_SNIFF_BYTES)
            if _looks_binary(head):
                return ToolResult(
                    output=f"file appears to be binary (or non-utf8); refusing to read: {target}",
                    is_error=True,
                )
            data = target.read_bytes()
        except OSError as exc:
            return ToolResult(output=f"read failed: {exc}", is_error=True)

        if len(data) > self._config.max_read_bytes:
            data = data[: self._config.max_read_bytes]
            truncated = True
        else:
            truncated = False

        text = data.decode("utf-8", errors="replace")
        lines = text.splitlines()
        end = min(len(lines), offset - 1 + limit)
        selected = lines[offset - 1 : end]

        rendered_lines = [f"{offset + i:>6}\t{line}" for i, line in enumerate(selected)]
        rendered = "\n".join(rendered_lines)

        notes = []
        if offset > 1:
            notes.append(f"starting at line {offset}")
        if end < len(lines):
            notes.append(f"showing lines {offset}-{end} of {len(lines)}")
        if truncated:
            notes.append(f"file truncated to {self._config.max_read_bytes} bytes for read")

        suffix = f"\n\n[{' | '.join(notes)}]" if notes else ""

        self._read_tracker.add(target)

        return ToolResult(output=rendered + suffix, metadata={"path": str(target)})
