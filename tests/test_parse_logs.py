import os
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from mcp_server import (
    parse_content_blocks,
    get_today_messages,
)


# --- parse_content_blocks ---

def test_parse_content_blocks_plain_string():
    assert parse_content_blocks("hello world") == "hello world"


def test_parse_content_blocks_text_blocks():
    blocks = [{"type": "text", "text": "Fix the bug"}, {"type": "tool_use", "id": "t1"}]
    assert parse_content_blocks(blocks) == "Fix the bug"


def test_parse_content_blocks_multiple_text():
    blocks = [{"type": "text", "text": "foo"}, {"type": "text", "text": "bar"}]
    assert parse_content_blocks(blocks) == "foo bar"


def test_parse_content_blocks_empty_list():
    assert parse_content_blocks([]) == ""


def test_parse_content_blocks_no_text_type():
    blocks = [{"type": "tool_use", "id": "t1"}, {"type": "tool_result", "content": "x"}]
    assert parse_content_blocks(blocks) == ""


# --- get_today_messages ---

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sample_session.jsonl"


def test_get_today_messages_filters_today(tmp_path, monkeypatch):
    proj_dir = tmp_path / ".claude" / "projects" / "myproject"
    proj_dir.mkdir(parents=True)
    session_file = proj_dir / "abc-123.jsonl"
    session_file.write_text(FIXTURE_PATH.read_text())

    fixed_dt = datetime(2026, 3, 23, 12, 0, 0, tzinfo=timezone.utc)
    os.utime(session_file, (fixed_dt.timestamp(), fixed_dt.timestamp()))

    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    with patch("mcp_server.datetime") as mock_datetime, \
         patch("mcp_server.date_type") as mock_date:
        mock_datetime.now.return_value = fixed_dt
        mock_datetime.fromisoformat.side_effect = datetime.fromisoformat
        mock_datetime.fromtimestamp.side_effect = datetime.fromtimestamp
        mock_date.today.return_value = date(2026, 3, 23)
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
        messages = get_today_messages(tz=timezone.utc)

    assert len(messages) == 4
    roles = [m["role"] for m in messages]
    assert set(roles) == {"user", "assistant"}


def test_get_today_messages_sorted_by_timestamp(tmp_path, monkeypatch):
    proj_dir = tmp_path / ".claude" / "projects" / "myproject"
    proj_dir.mkdir(parents=True)
    session_file = proj_dir / "abc-123.jsonl"
    session_file.write_text(FIXTURE_PATH.read_text())

    fixed_ts = datetime(2026, 3, 23, 12, 0, 0, tzinfo=timezone.utc)
    os.utime(session_file, (fixed_ts.timestamp(), fixed_ts.timestamp()))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    messages = get_today_messages(tz=timezone.utc, target_date=date(2026, 3, 23))

    timestamps = [m["timestamp"] for m in messages]
    assert timestamps == sorted(timestamps)


def test_get_today_messages_no_projects_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    messages = get_today_messages()
    assert messages == []


def test_get_today_messages_skips_future_mtime_files(tmp_path, monkeypatch):
    proj_dir = tmp_path / ".claude" / "projects" / "myproject"
    proj_dir.mkdir(parents=True)
    session_file = proj_dir / "abc-123.jsonl"
    session_file.write_text(FIXTURE_PATH.read_text())

    after_target = datetime(2026, 3, 24, 0, 0, 0, tzinfo=timezone.utc)
    os.utime(session_file, (after_target.timestamp(), after_target.timestamp()))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    messages = get_today_messages(tz=timezone.utc, target_date=date(2026, 3, 23))
    assert messages == []


def test_get_messages_for_date_returns_messages_from_that_date(tmp_path, monkeypatch):
    proj_dir = tmp_path / ".claude" / "projects" / "myproject"
    proj_dir.mkdir(parents=True)
    session_file = proj_dir / "abc-123.jsonl"
    session_file.write_text(FIXTURE_PATH.read_text())

    fixed_ts = datetime(2026, 3, 23, 12, 0, 0, tzinfo=timezone.utc)
    os.utime(session_file, (fixed_ts.timestamp(), fixed_ts.timestamp()))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    messages = get_today_messages(tz=timezone.utc, target_date=date(2026, 3, 23))
    assert len(messages) == 4


def test_get_messages_for_date_includes_same_day_mtime(tmp_path, monkeypatch):
    proj_dir = tmp_path / ".claude" / "projects" / "myproject"
    proj_dir.mkdir(parents=True)
    session_file = proj_dir / "abc-123.jsonl"
    session_file.write_text(FIXTURE_PATH.read_text())

    same_day_ts = datetime(2026, 3, 23, 23, 59, 0, tzinfo=timezone.utc)
    os.utime(session_file, (same_day_ts.timestamp(), same_day_ts.timestamp()))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    messages = get_today_messages(tz=timezone.utc, target_date=date(2026, 3, 23))
    assert len(messages) == 4


def test_get_today_messages_no_date_arg_uses_today(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    messages = get_today_messages()
    assert messages == []
