"""Redactor patterns."""

from __future__ import annotations

from cc_agent.redact import Redactor


def test_redacts_aws_access_key() -> None:
    r = Redactor([r"AKIA[0-9A-Z]{16}"])
    out = r.redact("found AKIAABCDEFGHIJKLMNOP in logs")
    assert "AKIA" not in out
    assert "[REDACTED]" in out


def test_redacts_secret_key_assignment() -> None:
    r = Redactor([r"(?i)aws_secret_access_key\s*[:=]\s*\S+"])
    out = r.redact("aws_secret_access_key=abcdefghijklmnop/QRSTUV")
    assert "abcdefghijklmnop" not in out


def test_redacts_inside_dict() -> None:
    r = Redactor([r"AKIA[0-9A-Z]{16}"])
    result = r.redact_any({"creds": "AKIAABCDEFGHIJKLMNOP", "user": "scott"})
    assert isinstance(result, dict)
    assert result["creds"] == "[REDACTED]"
    assert result["user"] == "scott"


def test_redacts_inside_list() -> None:
    r = Redactor([r"AKIA[0-9A-Z]{16}"])
    result = r.redact_any(["safe", "AKIAABCDEFGHIJKLMNOP"])
    assert isinstance(result, list)
    assert result[0] == "safe"
    assert result[1] == "[REDACTED]"
