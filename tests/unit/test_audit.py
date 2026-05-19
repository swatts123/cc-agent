"""Audit logger writes JSONL and redacts."""

from __future__ import annotations

import json
from pathlib import Path

from cc_agent.audit import AuditLogger
from cc_agent.config import AuditConfig, CloudWatchAuditConfig
from cc_agent.redact import Redactor


def _make_logger(tmp_path: Path) -> AuditLogger:
    cfg = AuditConfig(
        local_path=tmp_path / "audit.jsonl",
        cloudwatch=CloudWatchAuditConfig(enabled=False),
        redact_patterns=[r"AKIA[0-9A-Z]{16}"],
    )
    return AuditLogger(cfg, Redactor(cfg.redact_patterns))


def test_writes_jsonl(tmp_path: Path) -> None:
    logger = _make_logger(tmp_path)
    logger.log_tool_call(
        tool_name="bash",
        tool_use_id="t1",
        inputs={"command": "ls"},
        result={"output": "hi"},
        duration_ms=5.0,
        status="success",
    )
    line = (tmp_path / "audit.jsonl").read_text(encoding="utf-8").strip()
    record = json.loads(line)
    assert record["tool"] == "bash"
    assert record["status"] == "success"


def test_redacts_keys(tmp_path: Path) -> None:
    logger = _make_logger(tmp_path)
    logger.log_tool_call(
        tool_name="bash",
        tool_use_id="t2",
        inputs={"command": "echo AKIAABCDEFGHIJKLMNOP"},
        result={"output": "AKIAABCDEFGHIJKLMNOP"},
        duration_ms=1.0,
        status="success",
    )
    line = (tmp_path / "audit.jsonl").read_text(encoding="utf-8").strip()
    assert "AKIA" not in line
    assert "[REDACTED]" in line
