"""Command-line entrypoint: `cc-agent`."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pydantic import ValidationError

from .agent import Agent
from .audit import AuditLogger
from .bedrock_client import BedrockClient
from .config import (
    Config,
    default_system_prompt,
    ensure_directories,
    load_config,
    resolve_config_path,
    write_default_config,
)
from .permissions import PermissionEngine
from .redact import Redactor
from .repl import Repl
from .tools import build_registry


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cc-agent",
        description="Portable terminal agent powered by AWS Bedrock Claude models.",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to config file (default: $CC_AGENT_CONFIG or ~/.cc-agent/config.yaml).",
    )
    parser.add_argument(
        "--print-default-config",
        action="store_true",
        help="Print the bundled default config to stdout and exit.",
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="Print version and exit.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.version:
        from . import __version__
        print(__version__)
        return 0

    if args.print_default_config:
        from .config import default_config_template
        sys.stdout.write(default_config_template())
        return 0

    config_path = resolve_config_path(args.config)

    if not config_path.exists():
        write_default_config(config_path)
        print(f"Wrote default config to {config_path}.")
        print("Review it (in particular, add account profiles under aws.profiles if you need")
        print("cross-account reach), then run `cc-agent` again to start the REPL.")
        return 0

    try:
        config = load_config(config_path)
    except ValidationError as exc:
        print(f"Config validation failed at {config_path}:", file=sys.stderr)
        print(exc, file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001
        print(f"Could not load config at {config_path}: {exc}", file=sys.stderr)
        return 2

    ensure_directories(config)

    try:
        return _start_repl(config, config_path)
    except KeyboardInterrupt:
        print("\nbye")
        return 0


def _start_repl(config: Config, config_path: Path) -> int:
    redactor = Redactor(config.audit.redact_patterns)
    audit = AuditLogger(config.audit, redactor)

    system_prompt = (
        config.agent.system_prompt_file.read_text(encoding="utf-8")
        if config.agent.system_prompt_file is not None
        else default_system_prompt()
    )

    try:
        bedrock = BedrockClient(config.bedrock)
        tools = build_registry(config)
    except RuntimeError as exc:
        print(f"startup failed: {exc}", file=sys.stderr)
        return 2

    permissions = PermissionEngine(config)

    agent = Agent(
        config=config,
        bedrock=bedrock,
        tools=tools,
        permissions=permissions,
        audit=audit,
        redactor=redactor,
        system_prompt=system_prompt,
        # placeholder callbacks; REPL overwrites them in __init__
        approval_prompt=lambda *_: False,
        render_text=lambda _: None,
        render_tool_call=lambda *_: None,
        render_tool_result=lambda *_: None,
    )

    repl = Repl(agent=agent, config=config, config_path=config_path)
    return repl.run()


if __name__ == "__main__":
    raise SystemExit(main())
