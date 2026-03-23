import json
import os
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.parse_logs import (
    parse_content_blocks,
    validate_config,
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


# --- validate_config ---

VALID_CONFIG = {
    "url": "https://erp.example.com",
    "username": "user@example.com",
    "password": "secret",
    "employee": "EMP-001",
    "company": "ACME Corp",
    "project": "PROJ-001",
    "default_activity": "Development",
    "work_hours": 8,
}


def test_validate_config_valid():
    assert validate_config(VALID_CONFIG) == []


def test_validate_config_missing_password():
    cfg = {**VALID_CONFIG, "password": ""}
    errors = validate_config(cfg)
    assert any("password" in e for e in errors)


def test_validate_config_missing_employee():
    cfg = {**VALID_CONFIG}
    del cfg["employee"]
    errors = validate_config(cfg)
    assert any("employee" in e for e in errors)


def test_validate_config_negative_work_hours():
    cfg = {**VALID_CONFIG, "work_hours": -2}
    errors = validate_config(cfg)
    assert any("work_hours" in e for e in errors)


def test_validate_config_zero_work_hours():
    cfg = {**VALID_CONFIG, "work_hours": 0}
    errors = validate_config(cfg)
    assert any("work_hours" in e for e in errors)


def test_validate_config_invalid_start_time():
    cfg = {**VALID_CONFIG, "start_time": "9am"}
    errors = validate_config(cfg)
    assert any("start_time" in e for e in errors)


def test_validate_config_valid_start_time():
    cfg = {**VALID_CONFIG, "start_time": "08:30"}
    assert validate_config(cfg) == []


# --- get_today_messages ---

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sample_session.jsonl"


def test_get_today_messages_filters_today(tmp_path, monkeypatch):
    """Messages from today are returned; yesterday and non-user/assistant are skipped."""
    proj_dir = tmp_path / ".claude" / "projects" / "myproject"
    proj_dir.mkdir(parents=True)
    session_file = proj_dir / "abc-123.jsonl"
    session_file.write_text(FIXTURE_PATH.read_text())

    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    fixed_date = date(2026, 3, 23)
    with patch("scripts.parse_logs.date") as mock_date:
        mock_date.today.return_value = fixed_date
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
        messages = get_today_messages(tz=timezone.utc)

    # Should have 4 messages (2 user + 2 assistant from 2026-03-23), not the yesterday one, not progress
    assert len(messages) == 4
    roles = [m["role"] for m in messages]
    assert set(roles) == {"user", "assistant"}


def test_get_today_messages_sorted_by_timestamp(tmp_path, monkeypatch):
    proj_dir = tmp_path / ".claude" / "projects" / "myproject"
    proj_dir.mkdir(parents=True)
    session_file = proj_dir / "abc-123.jsonl"
    session_file.write_text(FIXTURE_PATH.read_text())

    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    fixed_date = date(2026, 3, 23)
    with patch("scripts.parse_logs.date") as mock_date:
        mock_date.today.return_value = fixed_date
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
        messages = get_today_messages(tz=timezone.utc)

    timestamps = [m["timestamp"] for m in messages]
    assert timestamps == sorted(timestamps)


def test_get_today_messages_no_projects_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    messages = get_today_messages()
    assert messages == []


def test_get_today_messages_skips_old_mtime_files(tmp_path, monkeypatch):
    """Files with mtime before today are skipped (mtime pre-filter)."""
    proj_dir = tmp_path / ".claude" / "projects" / "myproject"
    proj_dir.mkdir(parents=True)
    session_file = proj_dir / "abc-123.jsonl"
    session_file.write_text(FIXTURE_PATH.read_text())

    # Set the file's mtime to yesterday
    import time
    yesterday_ts = time.time() - 86400
    os.utime(session_file, (yesterday_ts, yesterday_ts))

    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    fixed_date = date(2026, 3, 23)
    with patch("scripts.parse_logs.date") as mock_date:
        mock_date.today.return_value = fixed_date
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
        messages = get_today_messages(tz=timezone.utc)

    # File has old mtime so it should be skipped entirely
    assert messages == []
