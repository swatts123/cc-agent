"""Audit logger for tool calls. Writes JSONL locally; optionally mirrors to CloudWatch."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .config import AuditConfig
from .redact import Redactor


class AuditLogger:
    """Append structured tool-call events to a JSONL file and optionally CloudWatch."""

    def __init__(self, config: AuditConfig, redactor: Redactor) -> None:
        self._local_path: Path = config.local_path
        self._redactor = redactor
        self._cw_enabled = config.cloudwatch.enabled
        self._cw_log_group = config.cloudwatch.log_group
        self._cw_region = config.cloudwatch.region
        self._cw_client: Any = None
        self._cw_stream_name: str | None = None
        self._cw_sequence_token: str | None = None

        self._local_path.parent.mkdir(parents=True, exist_ok=True)

        if self._cw_enabled:
            self._init_cloudwatch()

    def _init_cloudwatch(self) -> None:
        """Lazily create the log group/stream. Failures degrade gracefully."""
        try:
            import boto3  # local import so the dep stays optional at runtime

            kwargs: dict[str, Any] = {}
            if self._cw_region:
                kwargs["region_name"] = self._cw_region
            self._cw_client = boto3.client("logs", **kwargs)

            try:
                self._cw_client.create_log_group(logGroupName=self._cw_log_group)
            except self._cw_client.exceptions.ResourceAlreadyExistsException:
                pass

            self._cw_stream_name = f"cc-agent-{int(time.time())}"
            try:
                self._cw_client.create_log_stream(
                    logGroupName=self._cw_log_group,
                    logStreamName=self._cw_stream_name,
                )
            except self._cw_client.exceptions.ResourceAlreadyExistsException:
                pass
        except Exception as exc:  # noqa: BLE001 — audit must never crash the agent
            self._cw_enabled = False
            self._fallback_warning(f"CloudWatch audit disabled: {exc}")

    def _fallback_warning(self, message: str) -> None:
        # Write a one-line warning to the local audit log itself.
        event = {
            "ts": time.time(),
            "type": "audit_warning",
            "message": message,
        }
        with self._local_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event) + "\n")

    def log(self, event: dict[str, Any]) -> None:
        """Log an event. Always writes locally; mirrors to CloudWatch if enabled."""
        redacted = self._redactor.redact_any(event)
        if not isinstance(redacted, dict):  # mypy/runtime guard
            redacted = {"event": redacted}
        if "ts" not in redacted:
            redacted["ts"] = time.time()

        line = json.dumps(redacted, default=str)
        with self._local_path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

        if self._cw_enabled and self._cw_client and self._cw_stream_name:
            self._put_cloudwatch(line)

    def _put_cloudwatch(self, message: str) -> None:
        try:
            kwargs: dict[str, Any] = {
                "logGroupName": self._cw_log_group,
                "logStreamName": self._cw_stream_name,
                "logEvents": [{"timestamp": int(time.time() * 1000), "message": message}],
            }
            if self._cw_sequence_token:
                kwargs["sequenceToken"] = self._cw_sequence_token
            response = self._cw_client.put_log_events(**kwargs)
            self._cw_sequence_token = response.get("nextSequenceToken")
        except Exception as exc:  # noqa: BLE001
            self._cw_enabled = False
            self._fallback_warning(f"CloudWatch put_log_events failed, disabling: {exc}")

    def log_tool_call(
        self,
        tool_name: str,
        tool_use_id: str,
        inputs: dict[str, Any],
        result: dict[str, Any],
        duration_ms: float,
        status: str,
    ) -> None:
        self.log(
            {
                "type": "tool_call",
                "tool": tool_name,
                "tool_use_id": tool_use_id,
                "inputs": inputs,
                "result": result,
                "duration_ms": duration_ms,
                "status": status,
            }
        )

    def log_turn(
        self,
        role: str,
        text: str | None = None,
        usage: dict[str, Any] | None = None,
    ) -> None:
        self.log(
            {
                "type": "turn",
                "role": role,
                "text": text,
                "usage": usage,
            }
        )
