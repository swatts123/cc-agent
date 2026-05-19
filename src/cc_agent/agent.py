"""Core agent loop: model -> tool calls -> model -> ..."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from .audit import AuditLogger
from .bedrock_client import BedrockClient, ConverseResponse
from .config import Config
from .conversation import Conversation
from .permissions import Decision, PermissionEngine
from .redact import Redactor
from .tools import ToolRegistry, ToolResult

# Callbacks the REPL implements. Kept narrow so headless modes can plug in their own.
ApprovalPrompt = Callable[[str, dict[str, Any], Decision], bool]
RenderText = Callable[[str], None]
RenderToolCall = Callable[[str, dict[str, Any]], None]
RenderToolResult = Callable[[str, ToolResult], None]


class Agent:
    """Drives one user turn through the tool-use loop until the model returns plain text."""

    def __init__(
        self,
        config: Config,
        bedrock: BedrockClient,
        tools: ToolRegistry,
        permissions: PermissionEngine,
        audit: AuditLogger,
        redactor: Redactor,
        system_prompt: str,
        approval_prompt: ApprovalPrompt,
        render_text: RenderText,
        render_tool_call: RenderToolCall,
        render_tool_result: RenderToolResult,
    ) -> None:
        self._config = config
        self._bedrock = bedrock
        self._tools = tools
        self._permissions = permissions
        self._audit = audit
        self._redactor = redactor
        self._system_prompt = system_prompt
        self._approve = approval_prompt
        self._render_text = render_text
        self._render_tool_call = render_tool_call
        self._render_tool_result = render_tool_result

        # Per-session override of the model id (e.g. /model haiku).
        self.active_model_id = config.bedrock.model_id

    def run_turn(self, user_input: str, conversation: Conversation) -> None:
        conversation.append_user_text(user_input)
        self._audit.log_turn(role="user", text=user_input)

        while True:
            response = self._invoke_model(conversation)
            conversation.append_assistant(response.content_blocks)
            conversation.update_usage(response.usage)
            self._audit.log_turn(
                role="assistant",
                text=" ".join(response.text_blocks()) or None,
                usage=response.usage,
            )

            # Render any text the model produced this turn.
            for text in response.text_blocks():
                if text.strip():
                    self._render_text(text)

            tool_uses = response.tool_uses()
            if not tool_uses:
                return

            # Execute all requested tool calls; batch results back as a single user message.
            tool_results = []
            for tu in tool_uses:
                result_block = self._handle_tool_use(tu)
                tool_results.append(result_block)

            conversation.append_tool_results_batch(tool_results)

            # If the model said it was done with tool_use stop, we'll loop and let it speak.
            if response.stop_reason not in {"tool_use", "end_turn", "max_tokens"}:
                # Unknown stop reason — bail to keep things bounded.
                return

    def _invoke_model(self, conversation: Conversation) -> ConverseResponse:
        return self._bedrock.converse(
            model_id=self.active_model_id,
            system_prompt=self._system_prompt,
            messages=conversation.to_bedrock(),
            tool_schemas=self._tools.schemas(),
        )

    def _handle_tool_use(self, tool_use: dict[str, Any]) -> dict[str, Any]:
        name = tool_use["name"]
        tool_use_id = tool_use["toolUseId"]
        inputs = tool_use.get("input", {}) or {}

        self._render_tool_call(name, inputs)

        decision = self._permissions.evaluate(name, inputs)
        if not decision.allowed:
            result = ToolResult(
                output=f"refused: {decision.reason}",
                is_error=True,
                metadata={"refused": True, "reason": decision.reason},
            )
            self._record(name, tool_use_id, inputs, result, "refused", 0.0)
            self._render_tool_result(name, result)
            return self._to_tool_result_block(tool_use_id, result)

        if decision.requires_prompt:
            approved = self._approve(name, inputs, decision)
            if not approved:
                result = ToolResult(
                    output="user denied this call",
                    is_error=True,
                    metadata={"denied": True},
                )
                self._record(name, tool_use_id, inputs, result, "denied", 0.0)
                self._render_tool_result(name, result)
                return self._to_tool_result_block(tool_use_id, result)

        start = time.monotonic()
        result = self._tools.dispatch(name, inputs)
        duration_ms = (time.monotonic() - start) * 1000.0
        status = "error" if result.is_error else "success"

        # Redact the user-visible result text too (defense in depth — the audit log
        # is redacted by the audit logger, but rendering and the message we hand
        # back to the model should also pass through).
        redacted_text = self._redactor.redact(result.output)
        rendered = ToolResult(
            output=redacted_text,
            is_error=result.is_error,
            metadata=result.metadata,
        )

        self._record(name, tool_use_id, inputs, rendered, status, duration_ms)
        self._render_tool_result(name, rendered)
        return self._to_tool_result_block(tool_use_id, rendered)

    def _record(
        self,
        name: str,
        tool_use_id: str,
        inputs: dict[str, Any],
        result: ToolResult,
        status: str,
        duration_ms: float,
    ) -> None:
        self._audit.log_tool_call(
            tool_name=name,
            tool_use_id=tool_use_id,
            inputs=inputs,
            result={
                "output": result.output,
                "is_error": result.is_error,
                "metadata": result.metadata,
            },
            duration_ms=duration_ms,
            status=status,
        )

    @staticmethod
    def _to_tool_result_block(tool_use_id: str, result: ToolResult) -> dict[str, Any]:
        return {
            "toolResult": {
                "toolUseId": tool_use_id,
                "content": [{"text": result.output}],
                "status": "error" if result.is_error else "success",
            }
        }
