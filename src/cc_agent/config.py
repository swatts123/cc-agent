"""Configuration loading, validation, and default-config bootstrapping."""

from __future__ import annotations

import os
import shutil
from importlib import resources
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator


def _expand(path: str | None) -> Path | None:
    """Expand ~ and environment variables in a path; return None unchanged."""
    if path is None:
        return None
    return Path(os.path.expandvars(os.path.expanduser(path))).resolve()


class BedrockConfig(BaseModel):
    region: str | None = None
    model_id: str
    fallback_model_id: str | None = None
    max_tokens: int = Field(default=8192, ge=1, le=200_000)
    temperature: float = Field(default=0.2, ge=0.0, le=1.0)
    timeout_seconds: int = Field(default=60, ge=1, le=600)


class AgentConfig(BaseModel):
    workspace_root: Path
    session_dir: Path
    system_prompt_file: Path | None = None
    context_token_budget: int = Field(default=180_000, ge=1000)

    @field_validator("workspace_root", "session_dir", mode="before")
    @classmethod
    def _expand_required(cls, v: Any) -> Any:
        return _expand(v) if isinstance(v, str) else v

    @field_validator("system_prompt_file", mode="before")
    @classmethod
    def _expand_optional(cls, v: Any) -> Any:
        if v is None:
            return None
        return _expand(v) if isinstance(v, str) else v


class AwsProfileEntry(BaseModel):
    profile: str
    description: str = ""


class AwsConfig(BaseModel):
    default_cross_account_role: str = ""
    profiles: dict[str, AwsProfileEntry]

    @field_validator("profiles")
    @classmethod
    def _default_present(cls, v: dict[str, AwsProfileEntry]) -> dict[str, AwsProfileEntry]:
        if "default" not in v:
            raise ValueError("aws.profiles must contain a 'default' entry")
        return v


class FileToolConfig(BaseModel):
    enabled: bool = True
    max_read_bytes: int = Field(default=262_144, ge=1024)


class BashToolConfig(BaseModel):
    enabled: bool = True
    bash_path: str | None = None
    timeout_seconds: int = Field(default=30, ge=1, le=3600)
    max_output_bytes: int = Field(default=1_048_576, ge=1024)
    binary_allowlist: list[str] = Field(default_factory=list)
    command_denylist_patterns: list[str] = Field(default_factory=list)
    require_approval_for_unlisted: bool = True


class AwsCliToolConfig(BaseModel):
    enabled: bool = True
    aws_path: str | None = None
    timeout_seconds: int = Field(default=60, ge=1, le=600)
    auto_approve_verbs: list[str] = Field(default_factory=list)
    blocked_operations: list[str] = Field(default_factory=list)


class ToolsConfig(BaseModel):
    file: FileToolConfig = Field(default_factory=FileToolConfig)
    bash: BashToolConfig = Field(default_factory=BashToolConfig)
    aws_cli: AwsCliToolConfig = Field(default_factory=AwsCliToolConfig)


class CloudWatchAuditConfig(BaseModel):
    enabled: bool = False
    log_group: str = "/cc-agent/audit"
    region: str | None = None


class AuditConfig(BaseModel):
    local_path: Path
    cloudwatch: CloudWatchAuditConfig = Field(default_factory=CloudWatchAuditConfig)
    redact_patterns: list[str] = Field(default_factory=list)

    @field_validator("local_path", mode="before")
    @classmethod
    def _expand_local(cls, v: Any) -> Any:
        return _expand(v) if isinstance(v, str) else v


class UiConfig(BaseModel):
    theme: str = "dark"
    show_token_usage: bool = True


class Config(BaseModel):
    bedrock: BedrockConfig
    agent: AgentConfig
    aws: AwsConfig
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
    audit: AuditConfig
    ui: UiConfig = Field(default_factory=UiConfig)


DEFAULT_CONFIG_PATH = Path.home() / ".cc-agent" / "config.yaml"


def default_config_template() -> str:
    """Return the bundled default config as a YAML string."""
    return resources.files("cc_agent").joinpath("default_config.yaml").read_text(encoding="utf-8")


def default_system_prompt() -> str:
    """Return the bundled default system prompt."""
    return resources.files("cc_agent").joinpath("default_system_prompt.md").read_text(encoding="utf-8")


def resolve_config_path(cli_path: str | Path | None = None) -> Path:
    """Resolve the config path: CLI flag -> $CC_AGENT_CONFIG -> ~/.cc-agent/config.yaml."""
    if cli_path is not None:
        return Path(cli_path).expanduser().resolve()
    env_path = os.environ.get("CC_AGENT_CONFIG")
    if env_path:
        return Path(env_path).expanduser().resolve()
    return DEFAULT_CONFIG_PATH


def write_default_config(target: Path) -> None:
    """Write the bundled default config to `target`, creating parents."""
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfileobj(
        resources.files("cc_agent").joinpath("default_config.yaml").open("rb"),
        target.open("wb"),
    )


def load_config(path: Path) -> Config:
    """Load and validate config from disk."""
    with path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    if not isinstance(raw, dict):
        raise ValueError(f"Config at {path} did not parse to a mapping")
    return Config.model_validate(raw)


def ensure_directories(config: Config) -> None:
    """Create workspace, session, and audit directories if missing."""
    config.agent.workspace_root.mkdir(parents=True, exist_ok=True)
    config.agent.session_dir.mkdir(parents=True, exist_ok=True)
    config.audit.local_path.parent.mkdir(parents=True, exist_ok=True)
