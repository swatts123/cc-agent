"""Interactive REPL: input handling, rendering, and slash commands."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from .agent import Agent
from .config import Config, load_config
from .conversation import Conversation
from .permissions import Decision
from .tools import ToolResult


class Repl:
    """Owns terminal I/O, slash commands, and the conversation lifecycle."""

    def __init__(self, agent: Agent, config: Config, config_path: Path) -> None:
        self._agent = agent
        self._config = config
        self._config_path = config_path
        self._console = Console()
        self._conversation = Conversation(session_dir=config.agent.session_dir)
        history_file = config.agent.session_dir / ".prompt_history"
        self._session: PromptSession[str] = PromptSession(history=FileHistory(str(history_file)))

        # Plug rendering and approval callbacks into the agent.
        self._agent._render_text = self._render_text  # type: ignore[assignment]
        self._agent._render_tool_call = self._render_tool_call  # type: ignore[assignment]
        self._agent._render_tool_result = self._render_tool_result  # type: ignore[assignment]
        self._agent._approve = self._prompt_for_approval  # type: ignore[assignment]

    def run(self) -> int:
        self._print_banner()
        while True:
            try:
                user_input = self._session.prompt("you ▸ ")
            except (EOFError, KeyboardInterrupt):
                self._console.print("\n[dim]bye[/dim]")
                return 0

            if not user_input.strip():
                continue

            if user_input.startswith("/"):
                if self._handle_slash(user_input.strip()) is False:
                    return 0
                continue

            try:
                self._agent.run_turn(user_input, self._conversation)
            except KeyboardInterrupt:
                self._console.print("\n[yellow]interrupted[/yellow]")
                continue
            except Exception as exc:  # noqa: BLE001
                self._console.print(f"[red]error:[/red] {type(exc).__name__}: {exc}")

            self._maybe_show_token_footer()

    # --- slash commands -----------------------------------------------------

    def _handle_slash(self, line: str) -> bool:
        parts = line.split()
        cmd = parts[0]
        args = parts[1:]

        if cmd in {"/quit", "/exit"}:
            self._console.print("[dim]bye[/dim]")
            return False
        if cmd == "/help":
            self._print_help()
        elif cmd == "/clear":
            self._conversation.clear()
            self._console.print("[dim]conversation cleared[/dim]")
        elif cmd == "/tokens":
            self._console.print(
                f"input: {self._conversation.input_tokens}  "
                f"output: {self._conversation.output_tokens}  "
                f"total: {self._conversation.total_tokens()}"
            )
        elif cmd == "/model":
            if not args:
                self._console.print(f"current model: {self._agent.active_model_id}")
            else:
                self._agent.active_model_id = args[0]
                self._console.print(f"switched to model: {args[0]}")
        elif cmd == "/reload":
            try:
                new_config = load_config(self._config_path)
                self._console.print(
                    f"[green]reloaded[/green] config from {self._config_path}"
                )
                self._config = new_config
            except Exception as exc:  # noqa: BLE001
                self._console.print(f"[red]reload failed:[/red] {exc}")
        elif cmd == "/save":
            self._console.print(f"transcript at {self._conversation.session_file}")
        elif cmd == "/resume":
            if not args:
                self._console.print("usage: /resume <session-uuid>")
            else:
                try:
                    self._conversation = Conversation.resume(
                        self._config.agent.session_dir, args[0]
                    )
                    self._console.print(
                        f"resumed session {args[0]} with {len(self._conversation.messages)} messages"
                    )
                except FileNotFoundError as exc:
                    self._console.print(f"[red]not found:[/red] {exc}")
        elif cmd == "/profiles":
            for name, entry in self._config.aws.profiles.items():
                self._console.print(
                    f"  [bold]{name}[/bold] -> {entry.profile}    {entry.description}"
                )
        else:
            self._console.print(f"unknown command: {cmd} (try /help)")
        return True

    # --- rendering ----------------------------------------------------------

    def _render_text(self, text: str) -> None:
        self._console.print(Markdown(text))

    def _render_tool_call(self, name: str, inputs: dict[str, Any]) -> None:
        summary = self._summarize_inputs(name, inputs)
        self._console.print(f"[cyan]› tool {name}[/cyan] {summary}")

    def _render_tool_result(self, name: str, result: ToolResult) -> None:
        if result.is_error:
            self._console.print(Panel(result.output, title=f"{name} ERROR", border_style="red"))
        else:
            # For very long output, render in a panel but truncated.
            preview = result.output
            if len(preview) > 4000:
                preview = preview[:4000] + f"\n[... {len(result.output) - 4000} more chars ...]"
            self._console.print(Panel(preview, title=name, border_style="green"))

    def _maybe_show_token_footer(self) -> None:
        if self._config.ui.show_token_usage:
            self._console.print(
                f"[dim]tokens: in {self._conversation.input_tokens} "
                f"out {self._conversation.output_tokens}[/dim]"
            )

    # --- approval prompt ----------------------------------------------------

    def _prompt_for_approval(
        self, tool_name: str, inputs: dict[str, Any], decision: Decision
    ) -> bool:
        self._console.print(
            Panel(
                f"[bold]tool:[/bold] {tool_name}\n"
                f"[bold]reason:[/bold] {decision.reason}\n"
                f"[bold]inputs:[/bold]\n{json.dumps(inputs, indent=2)[:2000]}",
                title="approval required",
                border_style="yellow",
            )
        )
        try:
            answer = self._session.prompt("approve? [y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return False
        return answer in {"y", "yes"}

    # --- helpers ------------------------------------------------------------

    def _summarize_inputs(self, name: str, inputs: dict[str, Any]) -> str:
        if name == "bash":
            cmd = inputs.get("command", "")
            return f"`{cmd[:120]}{'…' if len(cmd) > 120 else ''}`"
        if name == "aws_cli":
            return (
                f"{inputs.get('profile', '?')} {inputs.get('service', '?')} "
                f"{inputs.get('operation', '?')}"
            )
        if name in {"read", "write", "edit"}:
            return f"path={inputs.get('path', '?')}"
        return ""

    def _print_help(self) -> None:
        self._console.print(
            "\n".join(
                [
                    "/help               show this help",
                    "/quit, /exit        leave the REPL",
                    "/clear              start a new conversation",
                    "/tokens             show running token usage",
                    "/model [id]         show or switch the active model",
                    "/reload             re-read the config file",
                    "/save               print the path of the current transcript",
                    "/resume <uuid>      resume a previous session by id",
                    "/profiles           list configured AWS profiles",
                ]
            )
        )

    def _print_banner(self) -> None:
        self._console.print(
            Panel(
                f"cc-agent  [dim]model {self._agent.active_model_id}[/dim]\n"
                f"session   [dim]{self._conversation.session_id}[/dim]\n"
                f"config    [dim]{self._config_path}[/dim]\n"
                f"workspace [dim]{self._config.agent.workspace_root}[/dim]\n"
                "type /help for commands, /quit to leave",
                border_style="blue",
            )
        )


def install_repl_callbacks(agent: Agent, repl: Repl) -> None:
    """Defensive helper if a future caller constructs Agent before Repl."""
    agent._render_text = repl._render_text  # type: ignore[assignment]
    agent._render_tool_call = repl._render_tool_call  # type: ignore[assignment]
    agent._render_tool_result = repl._render_tool_result  # type: ignore[assignment]
    agent._approve = repl._prompt_for_approval  # type: ignore[assignment]


def stderr_write(message: str) -> None:
    print(message, file=sys.stderr)
