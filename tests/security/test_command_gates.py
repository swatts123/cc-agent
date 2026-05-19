"""Verify bash denylist and AWS verb/operation gates."""

from __future__ import annotations

import pytest

from cc_agent.config import Config
from cc_agent.permissions import PermissionEngine

pytestmark = pytest.mark.security


@pytest.mark.parametrize(
    "command",
    [
        "rm -rf /",
        "rm -rf ~",
        "rm -rf  /home",
        "mkfs.ext4 /dev/sda1",
    ],
)
def test_bash_destructive_commands_refused(base_config: Config, command: str) -> None:
    engine = PermissionEngine(base_config)
    decision = engine.evaluate("bash", {"command": command})
    assert not decision.allowed, f"should refuse: {command}"


@pytest.mark.parametrize(
    "service,operation",
    [
        ("iam", "delete-role"),
        ("kms", "schedule-key-deletion"),
        ("s3", "delete-bucket"),
    ],
)
def test_aws_blocked_ops_refused(
    base_config: Config, service: str, operation: str
) -> None:
    engine = PermissionEngine(base_config)
    decision = engine.evaluate(
        "aws_cli", {"profile": "default", "service": service, "operation": operation}
    )
    assert not decision.allowed, f"should refuse {service}:{operation}"


@pytest.mark.parametrize(
    "operation",
    ["describe-instances", "list-buckets", "get-object", "head-bucket"],
)
def test_aws_read_verbs_auto_approve(base_config: Config, operation: str) -> None:
    engine = PermissionEngine(base_config)
    decision = engine.evaluate(
        "aws_cli", {"profile": "default", "service": "ec2", "operation": operation}
    )
    assert decision.allowed
    assert not decision.requires_prompt, f"{operation} should auto-approve"


@pytest.mark.parametrize(
    "operation",
    ["run-instances", "terminate-instances", "create-bucket", "put-object"],
)
def test_aws_mutations_require_approval(base_config: Config, operation: str) -> None:
    engine = PermissionEngine(base_config)
    decision = engine.evaluate(
        "aws_cli", {"profile": "default", "service": "ec2", "operation": operation}
    )
    assert decision.allowed
    assert decision.requires_prompt, f"{operation} should require approval"
