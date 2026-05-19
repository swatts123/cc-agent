"""Edit tool: exact-string replacement with uniqueness check."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import Tool, ToolResult
from .workspace import WorkspaceError, resolve_inside_workspace


class EditTool(Tool):
    name = "edit"
    description = (
        "Replace an exact string in a file. `old_string` must appear exactly once unless "
        "`replace_all` is true. Requires that `read` has been called on the file in this session."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "old_string": {"type": "string"},
            "new_string": {"type": "string"},
            "replace_all": {"type": "boolean", "default": False},
        },
        "required": ["path", "old_string", "new_string"],
    }

    def __init__(self, workspace_root: Path, read_tracker: set[Path]) -> None:
        self._workspace = workspace_root
        self._read_tracker = read_tracker

    def run(self, **kwargs: Any) -> ToolResult:
        path_str = kwargs.get("path")
        old_string = kwargs.get("old_string")
        new_string = kwargs.get("new_string")
        replace_all = bool(kwargs.get("replace_all", False))

        if not all(isinstance(x, str) for x in (path_str, old_string, new_string)):
            return ToolResult(
                output="'path', 'old_string', and 'new_string' are all required strings",
                is_error=True,
            )
        assert isinstance(path_str, str)
        assert isinstance(old_string, str)
        assert isinstance(new_string, str)

        if old_string == new_string:
            return ToolResult(output="old_string equals new_string; nothing to do", is_error=True)

        try:
            target = resolve_inside_workspace(self._workspace, path_str)
        except WorkspaceError as exc:
            return ToolResult(output=str(exc), is_error=True)

        if not target.exists():
            return ToolResult(output=f"file not found: {target}", is_error=True)
        if target not in self._read_tracker:
            return ToolResult(
                output=f"call `read` on {target} in this session before editing",
                is_error=True,
            )

        try:
            text = target.read_text(encoding="utf-8")
        except OSError as exc:
            return ToolResult(output=f"read failed: {exc}", is_error=True)
        except UnicodeDecodeError as exc:
            return ToolResult(output=f"file is not utf-8: {exc}", is_error=True)

        count = text.count(old_string)
        if count == 0:
            return ToolResult(
                output=f"old_string not found in {target}; no changes made", is_error=True
            )
        if count > 1 and not replace_all:
            return ToolResult(
                output=(
                    f"old_string appears {count} times in {target}; "
                    "include more context to make it unique, or set replace_all=true"
                ),
                is_error=True,
            )

        if replace_all:
            new_text = text.replace(old_string, new_string)
        else:
            new_text = text.replace(old_string, new_string, 1)

        try:
            target.write_text(new_text, encoding="utf-8")
        except OSError as exc:
            return ToolResult(output=f"write failed: {exc}", is_error=True)

        return ToolResult(
            output=f"replaced {count if replace_all else 1} occurrence(s) in {target}",
            metadata={"path": str(target), "replacements": count if replace_all else 1},
        )
