"""Conversation history with token accounting and persistence."""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any


class Conversation:
    """Maintains the message history in Bedrock Converse format.

    Bedrock Converse message format:
        {"role": "user"|"assistant", "content": [{"text": "..."}, {"toolUse": {...}}, ...]}
        Tool results from the user side:
        {"role": "user", "content": [{"toolResult": {"toolUseId": "...", "content": [{"text": "..."}], "status": "success"|"error"}}]}
    """

    def __init__(self, session_dir: Path, session_id: str | None = None) -> None:
        self.session_id = session_id or str(uuid.uuid4())
        self.session_dir = session_dir
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.messages: list[dict[str, Any]] = []
        self.input_tokens = 0
        self.output_tokens = 0
        self.created_at = time.time()

    @property
    def session_file(self) -> Path:
        return self.session_dir / f"{self.session_id}.jsonl"

    def append_user_text(self, text: str) -> None:
        self._append({"role": "user", "content": [{"text": text}]})

    def append_assistant(self, content_blocks: list[dict[str, Any]]) -> None:
        self._append({"role": "assistant", "content": content_blocks})

    def append_tool_result(
        self, tool_use_id: str, output_text: str, status: str = "success"
    ) -> None:
        block = {
            "toolResult": {
                "toolUseId": tool_use_id,
                "content": [{"text": output_text}],
                "status": status,
            }
        }
        self._append({"role": "user", "content": [block]})

    def append_tool_results_batch(self, results: list[dict[str, Any]]) -> None:
        """Append multiple tool results in a single user message (Bedrock requires batching)."""
        if not results:
            return
        self._append({"role": "user", "content": results})

    def _append(self, message: dict[str, Any]) -> None:
        self.messages.append(message)
        self._persist(message)

    def _persist(self, message: dict[str, Any]) -> None:
        record = {"ts": time.time(), "message": message}
        with self.session_file.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, default=str) + "\n")

    def update_usage(self, usage: dict[str, Any]) -> None:
        self.input_tokens += int(usage.get("inputTokens", 0))
        self.output_tokens += int(usage.get("outputTokens", 0))

    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def to_bedrock(self) -> list[dict[str, Any]]:
        return list(self.messages)

    def clear(self) -> None:
        self.messages.clear()
        self.input_tokens = 0
        self.output_tokens = 0
        self.session_id = str(uuid.uuid4())

    @classmethod
    def resume(cls, session_dir: Path, session_id: str) -> Conversation:
        """Load a previous session from its JSONL file."""
        conv = cls(session_dir=session_dir, session_id=session_id)
        if not conv.session_file.exists():
            raise FileNotFoundError(f"Session {session_id} not found at {conv.session_file}")
        # Re-read messages without re-persisting them.
        with conv.session_file.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                conv.messages.append(record["message"])
        return conv
