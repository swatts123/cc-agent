"""AWS CLI tool: runs `aws <service> <operation>` via a named profile."""

from __future__ import annotations

import json
import shutil
import subprocess
from typing import Any

from ..config import AwsCliToolConfig, AwsConfig
from .base import Tool, ToolResult


class AwsCliTool(Tool):
    name = "aws_cli"
    description = (
        "Run an AWS CLI command using one of the configured account profiles. "
        "Pick `profile` from the agent's configured profile names. Read verbs (describe, list, "
        "get, head, search, lookup, view, show) auto-approve; everything else prompts the operator."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "profile": {
                "type": "string",
                "description": "Friendly profile name as defined in agent config (e.g. 'default', 'prod').",
            },
            "service": {
                "type": "string",
                "description": "AWS service name as the CLI expects (e.g. 'ec2', 's3api', 'iam').",
            },
            "operation": {
                "type": "string",
                "description": "CLI operation in kebab-case (e.g. 'describe-instances').",
            },
            "parameters": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Additional CLI args, e.g. ['--instance-ids', 'i-0123'].",
            },
            "region": {
                "type": "string",
                "description": "Override region for this call.",
            },
        },
        "required": ["profile", "service", "operation"],
    }

    def __init__(self, aws_config: AwsConfig, cli_config: AwsCliToolConfig) -> None:
        self._aws_config = aws_config
        self._cli_config = cli_config
        self._aws_path = self._resolve_aws_path(cli_config.aws_path)

    @staticmethod
    def _resolve_aws_path(configured: str | None) -> str:
        if configured:
            return configured
        found = shutil.which("aws")
        if found is None:
            raise RuntimeError("aws CLI not found on PATH; set tools.aws_cli.aws_path in config")
        return found

    def run(self, **kwargs: Any) -> ToolResult:
        profile_name = kwargs.get("profile")
        service = kwargs.get("service")
        operation = kwargs.get("operation")
        parameters = kwargs.get("parameters") or []
        region = kwargs.get("region")

        if not isinstance(profile_name, str) or profile_name not in self._aws_config.profiles:
            return ToolResult(
                output=(
                    f"unknown profile '{profile_name}'. "
                    f"Configured: {sorted(self._aws_config.profiles.keys())}"
                ),
                is_error=True,
            )
        if not isinstance(service, str) or not service:
            return ToolResult(output="'service' is required", is_error=True)
        if not isinstance(operation, str) or not operation:
            return ToolResult(output="'operation' is required", is_error=True)
        if not isinstance(parameters, list) or not all(isinstance(p, str) for p in parameters):
            return ToolResult(output="'parameters' must be a list of strings", is_error=True)

        cli_profile = self._aws_config.profiles[profile_name].profile

        argv = [self._aws_path, service, operation, *parameters, "--profile", cli_profile]
        if isinstance(region, str) and region:
            argv += ["--region", region]
        argv += ["--output", "json"]

        try:
            proc = subprocess.run(
                argv,
                capture_output=True,
                timeout=self._cli_config.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return ToolResult(
                output=f"aws CLI call timed out after {self._cli_config.timeout_seconds}s",
                is_error=True,
                metadata={"timeout": True},
            )
        except FileNotFoundError as exc:
            return ToolResult(output=f"aws CLI not executable: {exc}", is_error=True)

        stdout = proc.stdout.decode("utf-8", errors="replace")
        stderr = proc.stderr.decode("utf-8", errors="replace")

        if proc.returncode != 0:
            return ToolResult(
                output=f"aws CLI exited {proc.returncode}\nstderr:\n{stderr}\nstdout:\n{stdout}",
                is_error=True,
                metadata={"returncode": proc.returncode},
            )

        # Try to parse as JSON; if not, return raw output.
        body: Any
        try:
            body = json.loads(stdout) if stdout.strip() else None
        except json.JSONDecodeError:
            body = stdout

        rendered = (
            json.dumps(body, indent=2, default=str) if not isinstance(body, str) else body
        )

        return ToolResult(
            output=rendered,
            metadata={
                "profile": profile_name,
                "cli_profile": cli_profile,
                "service": service,
                "operation": operation,
                "returncode": proc.returncode,
            },
        )
