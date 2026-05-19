"""File tools: read / write / edit."""

from __future__ import annotations

from pathlib import Path

from cc_agent.config import FileToolConfig
from cc_agent.tools.edit import EditTool
from cc_agent.tools.read import ReadTool
from cc_agent.tools.write import WriteTool


def _read_tracker() -> set[Path]:
    return set()


def test_read_basic(tmp_workspace: Path) -> None:
    f = tmp_workspace / "hi.txt"
    f.write_text("line one\nline two\nline three\n", encoding="utf-8")
    tracker: set[Path] = set()
    tool = ReadTool(tmp_workspace, FileToolConfig(), tracker)
    result = tool.run(path="hi.txt")
    assert not result.is_error
    assert "line one" in result.output
    assert "1\t" in result.output  # line numbering
    assert f.resolve() in tracker


def test_read_rejects_binary(tmp_workspace: Path) -> None:
    f = tmp_workspace / "blob.bin"
    f.write_bytes(b"\x00\x01\x02\x03 some binary stuff")
    tool = ReadTool(tmp_workspace, FileToolConfig(), set())
    result = tool.run(path="blob.bin")
    assert result.is_error


def test_write_requires_prior_read_for_existing_file(tmp_workspace: Path) -> None:
    f = tmp_workspace / "x.txt"
    f.write_text("original", encoding="utf-8")
    tool = WriteTool(tmp_workspace, set())  # no prior reads
    result = tool.run(path="x.txt", content="changed")
    assert result.is_error
    assert "prior read" in result.output.lower()
    assert f.read_text(encoding="utf-8") == "original"


def test_write_new_file_no_prior_read_needed(tmp_workspace: Path) -> None:
    tool = WriteTool(tmp_workspace, set())
    result = tool.run(path="new.txt", content="hello")
    assert not result.is_error
    assert (tmp_workspace / "new.txt").read_text(encoding="utf-8") == "hello"


def test_write_after_read_succeeds(tmp_workspace: Path) -> None:
    f = tmp_workspace / "x.txt"
    f.write_text("original", encoding="utf-8")
    tracker: set[Path] = set()
    ReadTool(tmp_workspace, FileToolConfig(), tracker).run(path="x.txt")
    tool = WriteTool(tmp_workspace, tracker)
    result = tool.run(path="x.txt", content="updated")
    assert not result.is_error
    assert f.read_text(encoding="utf-8") == "updated"


def test_edit_unique_match(tmp_workspace: Path) -> None:
    f = tmp_workspace / "code.py"
    f.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    tracker: set[Path] = set()
    ReadTool(tmp_workspace, FileToolConfig(), tracker).run(path="code.py")
    tool = EditTool(tmp_workspace, tracker)
    result = tool.run(path="code.py", old_string="a + b", new_string="a - b")
    assert not result.is_error
    assert "a - b" in f.read_text(encoding="utf-8")


def test_edit_multiple_matches_requires_replace_all(tmp_workspace: Path) -> None:
    f = tmp_workspace / "code.py"
    f.write_text("x = 1\ny = 1\nz = 1\n", encoding="utf-8")
    tracker: set[Path] = set()
    ReadTool(tmp_workspace, FileToolConfig(), tracker).run(path="code.py")
    tool = EditTool(tmp_workspace, tracker)

    result = tool.run(path="code.py", old_string="1", new_string="2")
    assert result.is_error
    assert "appears" in result.output

    result = tool.run(path="code.py", old_string="1", new_string="2", replace_all=True)
    assert not result.is_error
    assert f.read_text(encoding="utf-8") == "x = 2\ny = 2\nz = 2\n"


def test_edit_requires_prior_read(tmp_workspace: Path) -> None:
    f = tmp_workspace / "code.py"
    f.write_text("x = 1\n", encoding="utf-8")
    tool = EditTool(tmp_workspace, set())
    result = tool.run(path="code.py", old_string="x = 1", new_string="x = 2")
    assert result.is_error
    assert "read" in result.output.lower()
