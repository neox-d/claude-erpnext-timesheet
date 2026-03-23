import json
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
    """discover() returns a dict with employee, company, projects, activity_types."""
    with patch("scripts.setup.requests.Session") as mock_session_cls:
        session = MagicMock()
        mock_session_cls.return_value = session

        # login
        session.post.return_value = mock_response(200)

        # employee lookup
        session.get.side_effect = [
            mock_response(200, {"data": [{"name": "EMP-001", "company": "ACME Corp"}]}),  # employee
            mock_response(200, {"data": [{"name": "PROJ-001"}, {"name": "PROJ-002"}]}),   # projects
            mock_response(200, {"data": [{"name": "Development"}, {"name": "Design"}]}),   # activity types
        ]

        result = discover("https://erp.example.com", "user@example.com", "pass")

    assert result["employee"] == "EMP-001"
    assert result["company"] == "ACME Corp"
    assert result["projects"] == ["PROJ-001", "PROJ-002"]
    assert result["activity_types"] == ["Development", "Design"]


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
