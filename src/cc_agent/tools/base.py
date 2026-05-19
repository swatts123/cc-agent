"""Tool protocol and registry."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolResult:
    """Result of a tool invocation, suitable for handing back to Bedrock."""

    output: str
    is_error: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


class Tool(ABC):
    """Base class every tool implements."""

    name: str
    description: str
    input_schema: dict[str, Any]

    @abstractmethod
    def run(self, **kwargs: Any) -> ToolResult: ...

    def to_bedrock_spec(self) -> dict[str, Any]:
        """Return the Bedrock Converse toolSpec dict for this tool."""
        return {
            "toolSpec": {
                "name": self.name,
                "description": self.description,
                "inputSchema": {"json": self.input_schema},
            }
        }


class ToolRegistry:
    """Registers tools and dispatches by name."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return list(self._tools.keys())

    def schemas(self) -> list[dict[str, Any]]:
        return [t.to_bedrock_spec() for t in self._tools.values()]

    def dispatch(self, name: str, inputs: dict[str, Any]) -> ToolResult:
        tool = self.get(name)
        if tool is None:
            return ToolResult(output=f"Unknown tool: {name}", is_error=True)
        try:
            return tool.run(**inputs)
        except TypeError as exc:
            return ToolResult(output=f"Invalid inputs for {name}: {exc}", is_error=True)
        except Exception as exc:  # noqa: BLE001 — surfaced to model, not crash
            return ToolResult(output=f"{type(exc).__name__}: {exc}", is_error=True)
