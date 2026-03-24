import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

from scripts.setup import discover, write_config


def mock_response(status_code=200, json_data=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    if status_code >= 400:
        resp.raise_for_status.side_effect = requests.HTTPError(response=resp)
    else:
        resp.raise_for_status.return_value = None
    return resp


# --- discover ---

def test_discover_returns_expected_shape():
    """discover() returns a dict with employee, company, projects, activity_types, full_name."""
    with patch("scripts.setup.requests.Session") as mock_session_cls:
        session = MagicMock()
        mock_session_cls.return_value = session

        session.post.return_value = mock_response(200)

        session.get.side_effect = [
            mock_response(200, {"data": [{"name": "EMP-001", "company": "ACME Corp"}]}),  # employee
            mock_response(200, {"data": [{"name": "PROJ-001"}, {"name": "PROJ-002"}]}),   # projects
            mock_response(200, {"data": [{"name": "Development"}, {"name": "Design"}]}),   # activity types
            mock_response(200, {"data": {"full_name": "Jane Doe"}}),                       # user full_name
        ]

        result = discover("https://erp.example.com", "user@example.com", "pass")

    assert result["employee"] == "EMP-001"
    assert result["company"] == "ACME Corp"
    assert result["projects"] == ["PROJ-001", "PROJ-002"]
    assert result["activity_types"] == ["Development", "Design"]
    assert result["full_name"] == "Jane Doe"


def test_discover_raises_on_login_failure():
    with patch("scripts.setup.requests.Session") as mock_session_cls:
        session = MagicMock()
        mock_session_cls.return_value = session
        session.post.return_value = mock_response(401)

        with pytest.raises(requests.HTTPError):
            discover("https://erp.example.com", "user@example.com", "wrongpass")


def test_discover_raises_on_no_employee():
    """Raises ValueError if no employee record found for the logged-in user."""
    with patch("scripts.setup.requests.Session") as mock_session_cls:
        session = MagicMock()
        mock_session_cls.return_value = session
        session.post.return_value = mock_response(200)
        session.get.return_value = mock_response(200, {"data": []})  # no employee found

        with pytest.raises(ValueError, match="employee"):
            discover("https://erp.example.com", "user@example.com", "pass")


def test_discover_full_name_falls_back_on_http_error():
    """full_name falls back to username if the User GET raises HTTPError."""
    with patch("scripts.setup.requests.Session") as mock_session_cls:
        session = MagicMock()
        mock_session_cls.return_value = session

        session.post.return_value = mock_response(200)
        session.get.side_effect = [
            mock_response(200, {"data": [{"name": "EMP-001", "company": "ACME Corp"}]}),
            mock_response(200, {"data": [{"name": "PROJ-001"}]}),
            mock_response(200, {"data": [{"name": "Development"}]}),
            mock_response(403),  # User GET fails
        ]

        result = discover("https://erp.example.com", "user@example.com", "pass")

    assert result["full_name"] == "user@example.com"


def test_discover_full_name_falls_back_when_field_missing():
    """full_name falls back to username if full_name absent in response."""
    with patch("scripts.setup.requests.Session") as mock_session_cls:
        session = MagicMock()
        mock_session_cls.return_value = session

        session.post.return_value = mock_response(200)
        session.get.side_effect = [
            mock_response(200, {"data": [{"name": "EMP-001", "company": "ACME Corp"}]}),
            mock_response(200, {"data": [{"name": "PROJ-001"}]}),
            mock_response(200, {"data": [{"name": "Development"}]}),
            mock_response(200, {"data": {}}),  # full_name key absent
        ]

        result = discover("https://erp.example.com", "user@example.com", "pass")

    assert result["full_name"] == "user@example.com"


# --- main: --prompt-password ---

def _standard_session_mocks(session):
    session.post.return_value = mock_response(200)
    session.get.side_effect = [
        mock_response(200, {"data": [{"name": "EMP-001", "company": "ACME Corp"}]}),
        mock_response(200, {"data": [{"name": "PROJ-001"}]}),
        mock_response(200, {"data": [{"name": "Development"}]}),
        mock_response(200, {"data": {"full_name": "Jane Doe"}}),
    ]


def test_prompt_password_creates_temp_file_and_includes_in_output(capsys, monkeypatch):
    """--prompt-password captures password via getpass, writes temp file, adds _pwd_file to output."""
    monkeypatch.setattr(sys, "argv", [
        "setup.py", "--action", "discover",
        "--url", "https://erp.example.com",
        "--username", "user@example.com",
        "--prompt-password",
    ])
    with patch("scripts.setup.requests.Session") as mock_session_cls, \
         patch("scripts.setup.getpass.getpass", return_value="secret123"):
        session = MagicMock()
        mock_session_cls.return_value = session
        _standard_session_mocks(session)

        from scripts.setup import main
        main()

    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert "_pwd_file" in result
    pwd_path = Path(result["_pwd_file"])
    assert pwd_path.exists()
    assert pwd_path.read_text() == "secret123"
    pwd_path.unlink()


def test_prompt_password_temp_file_is_mode_600(capsys, monkeypatch):
    """Temp file created by --prompt-password is readable only by owner."""
    import os, stat as stat_mod
    monkeypatch.setattr(sys, "argv", [
        "setup.py", "--action", "discover",
        "--url", "https://erp.example.com",
        "--username", "user@example.com",
        "--prompt-password",
    ])
    with patch("scripts.setup.requests.Session") as mock_session_cls, \
         patch("scripts.setup.getpass.getpass", return_value="s3cr3t"):
        session = MagicMock()
        mock_session_cls.return_value = session
        _standard_session_mocks(session)

        from scripts.setup import main
        main()

    captured = capsys.readouterr()
    pwd_path = Path(json.loads(captured.out)["_pwd_file"])
    mode = os.stat(pwd_path).st_mode
    assert not (mode & stat_mod.S_IRGRP) and not (mode & stat_mod.S_IROTH), "file should not be group/world readable"
    pwd_path.unlink()


# --- main: --pwd-file in write-config ---

def test_write_config_pwd_file_merges_password_and_deletes_file(tmp_path, monkeypatch):
    """--pwd-file reads password into config and deletes the temp file."""
    pwd_file = tmp_path / "test.pwd"
    pwd_file.write_text("my_secret")

    config = {
        "url": "https://erp.example.com", "username": "u@example.com",
        "employee": "EMP-001", "company": "ACME Corp", "project": "PROJ-001",
        "default_activity": "Development", "work_hours": 8,
        "start_time": "09:00", "timezone": "Asia/Kolkata",
    }
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps(config))
    out_file = tmp_path / "timesheet.json"

    monkeypatch.setattr(sys, "argv", [
        "setup.py", "--action", "write-config",
        "--config-file", str(config_file),
        "--pwd-file", str(pwd_file),
        "--config-out", str(out_file),
    ])

    from scripts.setup import main
    main()

    assert not pwd_file.exists(), "password temp file should be deleted after use"
    loaded = json.loads(out_file.read_text())
    assert loaded["password"] == "my_secret"


# --- write_config ---

def test_write_config_creates_file(tmp_path):
    config = {
        "url": "https://erp.example.com",
        "username": "user@example.com",
        "password": "secret",
        "employee": "EMP-001",
        "company": "ACME Corp",
        "project": "PROJ-001",
        "default_activity": "Development",
        "work_hours": 8,
        "start_time": "09:00",
        "timezone": "Asia/Kolkata",
    }
    out = tmp_path / "timesheet.json"
    write_config(config, str(out))
    assert out.exists()
    loaded = json.loads(out.read_text())
    assert loaded == config


def test_write_config_overwrites_existing(tmp_path):
    out = tmp_path / "timesheet.json"
    out.write_text('{"old": "data"}')
    config = {"url": "https://new.example.com", "username": "u", "password": "p",
              "employee": "E", "company": "C", "project": "P",
              "default_activity": "D", "work_hours": 8}
    write_config(config, str(out))
    loaded = json.loads(out.read_text())
    assert loaded["url"] == "https://new.example.com"
    assert "old" not in loaded


def test_write_config_creates_parent_dirs(tmp_path):
    nested = tmp_path / ".claude" / "timesheet.json"
    assert not nested.parent.exists()
    config = {"url": "https://erp.example.com", "username": "u", "password": "p",
              "employee": "E", "company": "C", "project": "P",
              "default_activity": "D", "work_hours": 8}
    write_config(config, str(nested))
    assert nested.exists()
