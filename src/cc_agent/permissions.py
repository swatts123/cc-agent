"""Approval gating for tool calls."""

from __future__ import annotations

import re
import shlex
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .config import Config


@dataclass(frozen=True)
class Decision:
    allowed: bool
    requires_prompt: bool
    reason: str = ""


class PermissionEngine:
    """Pure decision logic. UI for the actual prompt lives in repl.py."""

    def __init__(self, config: Config) -> None:
        self._config = config
        self._bash_deny = [re.compile(p) for p in config.tools.bash.command_denylist_patterns]
        self._bash_allow = set(config.tools.bash.binary_allowlist)
        self._aws_blocked = {op.lower() for op in config.tools.aws_cli.blocked_operations}
        self._aws_auto = [v.lower() for v in config.tools.aws_cli.auto_approve_verbs]

    def evaluate(self, tool_name: str, inputs: dict[str, Any]) -> Decision:
        if tool_name == "bash":
            return self._evaluate_bash(inputs)
        if tool_name == "aws_cli":
            return self._evaluate_aws_cli(inputs)
        # File tools: read auto, write/edit auto inside workspace
        return Decision(allowed=True, requires_prompt=False, reason="auto-approved file tool")

    def _evaluate_bash(self, inputs: dict[str, Any]) -> Decision:
        command = inputs.get("command", "")
        if not isinstance(command, str) or not command.strip():
            return Decision(allowed=False, requires_prompt=False, reason="empty command")

        # Hard deny patterns first.
        for pattern in self._bash_deny:
            if pattern.search(command):
                return Decision(
                    allowed=False,
                    requires_prompt=False,
                    reason=f"command matches deny pattern: {pattern.pattern}",
                )

        head = _head_binary(command)
        if head is None:
            return Decision(
                allowed=True,
                requires_prompt=self._config.tools.bash.require_approval_for_unlisted,
                reason="could not parse head binary",
            )
        if head in self._bash_allow:
            return Decision(allowed=True, requires_prompt=False, reason=f"{head} on allowlist")
        return Decision(
            allowed=True,
            requires_prompt=self._config.tools.bash.require_approval_for_unlisted,
            reason=f"{head} not on allowlist",
        )

    def _evaluate_aws_cli(self, inputs: dict[str, Any]) -> Decision:
        service = str(inputs.get("service", "")).lower()
        operation = str(inputs.get("operation", "")).lower()
        op_key = f"{service}:{operation}"

        # Hard block list.
        if op_key in self._aws_blocked:
            return Decision(allowed=False, requires_prompt=False, reason=f"blocked: {op_key}")
        # Operation can also be expressed as PascalCase (DeleteRole). Normalize.
        normalized_op = operation.replace("-", "")
        for blocked in self._aws_blocked:
            if blocked.startswith(f"{service}:") and blocked.split(":", 1)[1].replace("-", "") == normalized_op:
                return Decision(allowed=False, requires_prompt=False, reason=f"blocked: {blocked}")

        # Verb auto-approve.
        first_token = operation.split("-", 1)[0]
        if first_token in self._aws_auto:
            return Decision(
                allowed=True, requires_prompt=False, reason=f"verb '{first_token}' auto-approved"
            )
        return Decision(
            allowed=True, requires_prompt=True, reason=f"verb '{first_token}' needs approval"
        )


def _head_binary(command: str) -> str | None:
    """Return the leading binary name from a shell command, ignoring env assignments."""
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        return None
    for token in tokens:
        if "=" in token and not token.startswith(("-", "/")):
            # env var assignment like FOO=bar — skip
            continue
        # Strip path components: /usr/bin/git -> git
        return token.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    return None


PromptFn = Callable[[str, dict[str, Any], Decision], bool]
"""A callable that asks the user to approve and returns True/False."""
