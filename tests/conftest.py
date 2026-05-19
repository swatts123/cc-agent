"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

from cc_agent.config import (
    AgentConfig,
    AuditConfig,
    AwsCliToolConfig,
    AwsConfig,
    AwsProfileEntry,
    BashToolConfig,
    BedrockConfig,
    CloudWatchAuditConfig,
    Config,
    FileToolConfig,
    ToolsConfig,
    UiConfig,
)


@pytest.fixture
def tmp_workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "workspace"
    ws.mkdir()
    return ws


@pytest.fixture
def tmp_session_dir(tmp_path: Path) -> Path:
    d = tmp_path / "sessions"
    d.mkdir()
    return d


@pytest.fixture
def base_config(tmp_workspace: Path, tmp_session_dir: Path, tmp_path: Path) -> Config:
    return Config(
        bedrock=BedrockConfig(
            region="us-east-1",
            model_id="anthropic.claude-sonnet-4-6-v1:0",
            fallback_model_id="anthropic.claude-haiku-4-5-v1:0",
            max_tokens=4096,
            temperature=0.2,
            timeout_seconds=60,
        ),
        agent=AgentConfig(
            workspace_root=tmp_workspace,
            session_dir=tmp_session_dir,
            system_prompt_file=None,
            context_token_budget=180_000,
        ),
        aws=AwsConfig(
            default_cross_account_role="arn:aws:iam::*:role/Test",
            profiles={
                "default": AwsProfileEntry(profile="default", description="default"),
                "prod": AwsProfileEntry(profile="org-prod", description="prod"),
            },
        ),
        tools=ToolsConfig(
            file=FileToolConfig(enabled=True, max_read_bytes=65536),
            bash=BashToolConfig(
                enabled=True,
                bash_path=None,
                timeout_seconds=10,
                max_output_bytes=65536,
                binary_allowlist=["ls", "cat", "echo", "pwd", "grep"],
                command_denylist_patterns=[
                    r"rm\s+-rf\s+[/~]",
                    r"mkfs",
                ],
                require_approval_for_unlisted=True,
            ),
            aws_cli=AwsCliToolConfig(
                enabled=True,
                aws_path=None,
                timeout_seconds=30,
                auto_approve_verbs=["get", "describe", "list", "head"],
                blocked_operations=[
                    "iam:DeleteRole",
                    "kms:ScheduleKeyDeletion",
                    "s3:DeleteBucket",
                ],
            ),
        ),
        audit=AuditConfig(
            local_path=tmp_path / "audit.jsonl",
            cloudwatch=CloudWatchAuditConfig(enabled=False),
            redact_patterns=[
                r"AKIA[0-9A-Z]{16}",
                r"(?i)aws_secret_access_key\s*[:=]\s*\S+",
            ],
        ),
        ui=UiConfig(theme="dark", show_token_usage=False),
    )
