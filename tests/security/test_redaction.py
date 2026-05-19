"""Redaction covers all configured secret patterns."""

from __future__ import annotations

import pytest

from cc_agent.redact import Redactor

pytestmark = pytest.mark.security

DEFAULT_PATTERNS = [
    r"AKIA[0-9A-Z]{16}",
    r"(?i)aws_secret_access_key\s*[:=]\s*\S+",
    r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}",
]


@pytest.fixture
def redactor() -> Redactor:
    return Redactor(DEFAULT_PATTERNS)


def test_access_key_redacted(redactor: Redactor) -> None:
    assert "AKIA" not in redactor.redact("AKIAABCDEFGHIJKLMNOP")


def test_secret_key_assignment_redacted(redactor: Redactor) -> None:
    sample = "AWS_SECRET_ACCESS_KEY = wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
    out = redactor.redact(sample)
    assert "wJalrXUtn" not in out


def test_jwt_redacted(redactor: Redactor) -> None:
    sample = (
        "token: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
        "eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIn0."
        "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
    )
    out = redactor.redact(sample)
    assert "eyJ" not in out
