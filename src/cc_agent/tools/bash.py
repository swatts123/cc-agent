"""Bash tool: executes commands through a configured bash binary."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from ..config import BashToolConfig
from .base import Tool, ToolResult


class BashTool(Tool):
    name = "bash"
    description = (
        "Run a shell command through the host's bash. Use forward slashes in paths; "
        "Git Bash on Windows accepts POSIX-style paths. Output is captured and may be truncated. "
        "Per-call timeout applies."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "The shell command to execute."},
            "cwd": {
                "type": "string",
                "description": "Working directory. Defaults to the workspace root.",
            },
            "timeout_seconds": {
                "type": "integer",
                "description": "Override the default timeout (capped by config).",
                "minimum": 1,
            },
        },
        "required": ["command"],
    }

    def __init__(self, config: BashToolConfig, workspace_root: Path) -> None:
        self._config = config
        self._workspace = workspace_root
        self._bash_path = self._resolve_bash_path(config.bash_path)

    @staticmethod
    def _resolve_bash_path(configured: str | None) -> str:
        if configured:
            return configured
        # On Windows this finds Git Bash's bash.exe when it's on PATH.
        found = shutil.which("bash")
        if found is None:
            raise RuntimeError(
                "bash binary not found on PATH; set tools.bash.bash_path in config"
            )
        return found

    def run(self, **kwargs: Any) -> ToolResult:
        command = kwargs.get("command")
        if not isinstance(command, str) or not command.strip():
            return ToolResult(output="'command' is required and must be a non-empty string", is_error=True)

        cwd_raw = kwargs.get("cwd")
        cwd = Path(cwd_raw).expanduser() if isinstance(cwd_raw, str) and cwd_raw else self._workspace
        if not cwd.exists() or not cwd.is_dir():
            return ToolResult(output=f"cwd does not exist or is not a directory: {cwd}", is_error=True)

        requested_timeout = kwargs.get("timeout_seconds")
        if isinstance(requested_timeout, int) and requested_timeout > 0:
            timeout = min(requested_timeout, self._config.timeout_seconds)
        else:
            timeout = self._config.timeout_seconds

        try:
            proc = subprocess.run(
                [self._bash_path, "-lc", command],
                capture_output=True,
                cwd=str(cwd),
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return ToolResult(
                output=f"command timed out after {timeout}s",
                is_error=True,
                metadata={"timeout": True},
            )
        except FileNotFoundError as exc:
            return ToolResult(output=f"bash not executable: {exc}", is_error=True)

        stdout = self._cap(proc.stdout)
        stderr = self._cap(proc.stderr)

        rendered = self._render(stdout, stderr, proc.returncode)
        return ToolResult(
            output=rendered,
            is_error=proc.returncode != 0,
            metadata={"returncode": proc.returncode, "cwd": str(cwd)},
        )

    def _cap(self, blob: bytes) -> str:
        limit = self._config.max_output_bytes
        if len(blob) > limit:
            blob = blob[:limit] + f"\n[... truncated to {limit} bytes ...]".encode()
        return blob.decode("utf-8", errors="replace")

    @staticmethod
    def _render(stdout: str, stderr: str, returncode: int) -> str:
        parts = [f"exit_code: {returncode}"]
        if stdout:
            parts.append(f"stdout:\n{stdout}")
        if stderr:
            parts.append(f"stderr:\n{stderr}")
        return "\n\n".join(parts)
