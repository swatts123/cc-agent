"""Conversation history and persistence."""

from __future__ import annotations

from pathlib import Path

from cc_agent.conversation import Conversation


def test_append_persists_to_session_file(tmp_session_dir: Path) -> None:
    conv = Conversation(session_dir=tmp_session_dir)
    conv.append_user_text("hello")
    assert conv.session_file.exists()
    contents = conv.session_file.read_text(encoding="utf-8")
    assert "hello" in contents


def test_resume_round_trip(tmp_session_dir: Path) -> None:
    conv = Conversation(session_dir=tmp_session_dir)
    conv.append_user_text("first")
    conv.append_assistant([{"text": "reply"}])
    sid = conv.session_id

    resumed = Conversation.resume(tmp_session_dir, sid)
    assert resumed.session_id == sid
    assert len(resumed.messages) == 2
    assert resumed.messages[0]["role"] == "user"
    assert resumed.messages[1]["role"] == "assistant"


def test_update_usage_tracks_tokens(tmp_session_dir: Path) -> None:
    conv = Conversation(session_dir=tmp_session_dir)
    conv.update_usage({"inputTokens": 100, "outputTokens": 50})
    conv.update_usage({"inputTokens": 30, "outputTokens": 20})
    assert conv.input_tokens == 130
    assert conv.output_tokens == 70
    assert conv.total_tokens() == 200


def test_clear_resets_state(tmp_session_dir: Path) -> None:
    conv = Conversation(session_dir=tmp_session_dir)
    conv.append_user_text("hi")
    conv.update_usage({"inputTokens": 5, "outputTokens": 5})
    old_sid = conv.session_id
    conv.clear()
    assert conv.messages == []
    assert conv.input_tokens == 0
    assert conv.session_id != old_sid
