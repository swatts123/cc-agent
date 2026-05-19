"""Secret redaction for transcripts and audit logs."""

from __future__ import annotations

import re
from collections.abc import Iterable


class Redactor:
    """Applies a list of regex patterns and replaces matches with [REDACTED]."""

    def __init__(self, patterns: Iterable[str]) -> None:
        self._patterns = [re.compile(p) for p in patterns]

    def redact(self, text: str) -> str:
        for pattern in self._patterns:
            text = pattern.sub("[REDACTED]", text)
        return text

    def redact_any(self, value: object) -> object:
        """Recursively redact strings inside dicts and lists."""
        if isinstance(value, str):
            return self.redact(value)
        if isinstance(value, dict):
            return {k: self.redact_any(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.redact_any(v) for v in value]
        return value
