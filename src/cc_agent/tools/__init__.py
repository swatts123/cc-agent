"""Tool implementations and registry construction."""

from __future__ import annotations

from pathlib import Path

from ..config import Config
from .aws_cli import AwsCliTool
from .base import Tool, ToolRegistry, ToolResult
from .bash import BashTool
from .edit import EditTool
from .read import ReadTool
from .write import WriteTool

__all__ = [
    "Tool",
    "ToolRegistry",
    "ToolResult",
    "ReadTool",
    "WriteTool",
    "EditTool",
    "BashTool",
    "AwsCliTool",
    "build_registry",
]


def build_registry(config: Config) -> ToolRegistry:
    """Construct a tool registry honoring config.tools.*.enabled flags."""
    registry = ToolRegistry()
    workspace: Path = config.agent.workspace_root
    read_tracker: set[Path] = set()

    if config.tools.file.enabled:
        registry.register(ReadTool(workspace, config.tools.file, read_tracker))
        registry.register(WriteTool(workspace, read_tracker))
        registry.register(EditTool(workspace, read_tracker))

    if config.tools.bash.enabled:
        registry.register(BashTool(config.tools.bash, workspace))

    if config.tools.aws_cli.enabled:
        registry.register(AwsCliTool(config.aws, config.tools.aws_cli))

    return registry
