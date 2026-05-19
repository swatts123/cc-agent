"""Permissions engine."""

from __future__ import annotations

from cc_agent.config import Config
from cc_agent.permissions import PermissionEngine


def test_bash_allowlist_auto_approves(base_config: Config) -> None:
    engine = PermissionEngine(base_config)
    decision = engine.evaluate("bash", {"command": "ls -la"})
    assert decision.allowed
    assert not decision.requires_prompt


def test_bash_unknown_binary_requires_prompt(base_config: Config) -> None:
    engine = PermissionEngine(base_config)
    decision = engine.evaluate("bash", {"command": "curl https://example.com"})
    assert decision.allowed
    assert decision.requires_prompt


def test_bash_denylist_refuses(base_config: Config) -> None:
    engine = PermissionEngine(base_config)
    decision = engine.evaluate("bash", {"command": "rm -rf /"})
    assert not decision.allowed
    assert "deny" in decision.reason.lower()


def test_bash_mkfs_denylist(base_config: Config) -> None:
    engine = PermissionEngine(base_config)
    decision = engine.evaluate("bash", {"command": "mkfs.ext4 /dev/sda1"})
    assert not decision.allowed


def test_aws_describe_auto_approves(base_config: Config) -> None:
    engine = PermissionEngine(base_config)
    decision = engine.evaluate(
        "aws_cli", {"profile": "default", "service": "ec2", "operation": "describe-instances"}
    )
    assert decision.allowed
    assert not decision.requires_prompt


def test_aws_mutation_requires_prompt(base_config: Config) -> None:
    engine = PermissionEngine(base_config)
    decision = engine.evaluate(
        "aws_cli", {"profile": "default", "service": "ec2", "operation": "terminate-instances"}
    )
    assert decision.allowed
    assert decision.requires_prompt


def test_aws_blocked_operation(base_config: Config) -> None:
    engine = PermissionEngine(base_config)
    decision = engine.evaluate(
        "aws_cli", {"profile": "default", "service": "iam", "operation": "delete-role"}
    )
    assert not decision.allowed


def test_aws_blocked_operation_normalized(base_config: Config) -> None:
    """iam:DeleteRole in config should match operation 'delete-role'."""
    engine = PermissionEngine(base_config)
    decision = engine.evaluate(
        "aws_cli", {"profile": "default", "service": "kms", "operation": "schedule-key-deletion"}
    )
    assert not decision.allowed


def test_file_tool_auto_approves(base_config: Config) -> None:
    engine = PermissionEngine(base_config)
    for tool in ("read", "write", "edit"):
        decision = engine.evaluate(tool, {"path": "foo.txt"})
        assert decision.allowed
        assert not decision.requires_prompt
