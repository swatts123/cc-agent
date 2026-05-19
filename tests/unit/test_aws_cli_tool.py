"""AWS CLI tool: argument construction and profile validation."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from cc_agent.config import Config
from cc_agent.tools.aws_cli import AwsCliTool


def _make_tool(base_config: Config) -> AwsCliTool:
    # Bypass shutil.which by patching at construction time.
    with patch("cc_agent.tools.aws_cli.shutil.which", return_value="/usr/local/bin/aws"):
        return AwsCliTool(base_config.aws, base_config.tools.aws_cli)


def test_rejects_unknown_profile(base_config: Config) -> None:
    tool = _make_tool(base_config)
    result = tool.run(profile="nope", service="ec2", operation="describe-instances")
    assert result.is_error
    assert "unknown profile" in result.output.lower()


def test_builds_expected_argv(base_config: Config) -> None:
    tool = _make_tool(base_config)
    mock_proc = MagicMock(returncode=0, stdout=b'{"Reservations": []}', stderr=b"")
    with patch("cc_agent.tools.aws_cli.subprocess.run", return_value=mock_proc) as runner:
        result = tool.run(
            profile="prod",
            service="ec2",
            operation="describe-instances",
            parameters=["--filters", "Name=tag:Env,Values=prod"],
            region="us-west-2",
        )
    assert not result.is_error
    argv = runner.call_args.args[0]
    # path, service, operation, parameter, parameter, --profile, value, --region, value, --output, json
    assert argv[1] == "ec2"
    assert argv[2] == "describe-instances"
    assert "--filters" in argv
    assert "Name=tag:Env,Values=prod" in argv
    assert "--profile" in argv
    assert "org-prod" in argv  # mapped from friendly name "prod"
    assert "--region" in argv
    assert "us-west-2" in argv
    assert argv[-2:] == ["--output", "json"]


def test_parses_json_output(base_config: Config) -> None:
    tool = _make_tool(base_config)
    mock_proc = MagicMock(returncode=0, stdout=b'{"x": 1}', stderr=b"")
    with patch("cc_agent.tools.aws_cli.subprocess.run", return_value=mock_proc):
        result = tool.run(profile="default", service="ec2", operation="describe-instances")
    assert not result.is_error
    assert "\"x\": 1" in result.output


def test_surfaces_nonzero_exit(base_config: Config) -> None:
    tool = _make_tool(base_config)
    mock_proc = MagicMock(returncode=255, stdout=b"", stderr=b"AccessDenied")
    with patch("cc_agent.tools.aws_cli.subprocess.run", return_value=mock_proc):
        result = tool.run(profile="default", service="ec2", operation="describe-instances")
    assert result.is_error
    assert "AccessDenied" in result.output
    assert "255" in result.output
