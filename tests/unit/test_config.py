"""Config loading and validation."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from cc_agent.config import (
    Config,
    default_config_template,
    default_system_prompt,
    load_config,
    resolve_config_path,
)


def test_default_config_parses() -> None:
    raw = yaml.safe_load(default_config_template())
    Config.model_validate(raw)


def test_default_system_prompt_nonempty() -> None:
    assert len(default_system_prompt().strip()) > 100


def test_resolve_config_explicit(tmp_path: Path) -> None:
    explicit = tmp_path / "x.yaml"
    assert resolve_config_path(explicit) == explicit.resolve()


def test_resolve_config_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    env_path = tmp_path / "env.yaml"
    monkeypatch.setenv("CC_AGENT_CONFIG", str(env_path))
    assert resolve_config_path(None) == env_path.resolve()


def test_missing_default_profile_fails(tmp_path: Path) -> None:
    cfg = yaml.safe_load(default_config_template())
    cfg["aws"]["profiles"].pop("default")
    out = tmp_path / "bad.yaml"
    out.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    with pytest.raises(Exception):
        load_config(out)
