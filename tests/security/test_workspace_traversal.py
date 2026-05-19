"""Verify file tools cannot escape the workspace via traversal or symlinks."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from cc_agent.config import FileToolConfig
from cc_agent.tools.read import ReadTool
from cc_agent.tools.workspace import WorkspaceError, resolve_inside_workspace
from cc_agent.tools.write import WriteTool

pytestmark = pytest.mark.security


def test_parent_traversal_blocked(tmp_workspace: Path) -> None:
    with pytest.raises(WorkspaceError):
        resolve_inside_workspace(tmp_workspace, "../escape.txt")


def test_absolute_outside_blocked(tmp_workspace: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    with pytest.raises(WorkspaceError):
        resolve_inside_workspace(tmp_workspace, str(outside))


def test_nested_traversal_blocked(tmp_workspace: Path) -> None:
    (tmp_workspace / "sub").mkdir()
    with pytest.raises(WorkspaceError):
        resolve_inside_workspace(tmp_workspace, "sub/../../escape.txt")


@pytest.mark.skipif(sys.platform == "win32", reason="symlink creation needs privileges on Windows")
def test_symlink_escape_blocked(tmp_workspace: Path, tmp_path: Path) -> None:
    outside = tmp_path / "secret.txt"
    outside.write_text("nope", encoding="utf-8")
    link = tmp_workspace / "link.txt"
    os.symlink(outside, link)

    tool = ReadTool(tmp_workspace, FileToolConfig(), set())
    result = tool.run(path="link.txt")
    assert result.is_error
    assert "outside" in result.output.lower()


def test_read_outside_workspace_errors(tmp_workspace: Path, tmp_path: Path) -> None:
    outside = tmp_path / "secret.txt"
    outside.write_text("nope", encoding="utf-8")
    tool = ReadTool(tmp_workspace, FileToolConfig(), set())
    result = tool.run(path=str(outside))
    assert result.is_error


def test_write_outside_workspace_errors(tmp_workspace: Path, tmp_path: Path) -> None:
    outside_path = tmp_path / "should-not-write.txt"
    tool = WriteTool(tmp_workspace, set())
    result = tool.run(path=str(outside_path), content="x")
    assert result.is_error
    assert not outside_path.exists()
