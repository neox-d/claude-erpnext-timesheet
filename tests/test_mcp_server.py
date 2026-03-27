import json
from pathlib import Path

import pytest

from mcp_server import get_status, validate_config, read_messages, check_duplicate, submit_timesheet
import mcp_server


VALID_CONFIG = {
    "url": "https://erp.example.com",
    "username": "user@example.com",
    "password": "enc:someencryptedvalue",
    "employee": "EMP-001",
    "company": "ACME Corp",
    "project": "PROJ-001",
    "default_activity": "Development",
    "work_hours": 8,
}


def _write_config(tmp_path: Path, config: dict = None) -> None:
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    (claude_dir / "timesheet.json").write_text(json.dumps(config or VALID_CONFIG))


def test_get_status_not_configured(tmp_path, monkeypatch):
    """When timesheet.json is absent, configured=False and setup_command is returned."""
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))

    result = get_status()

    assert result["configured"] is False
    assert result["setup_command"] == "python3 ~/.claude/timesheet-setup"
    assert result.get("username") is None or "username" not in result
    assert result.get("url") is None or "url" not in result


def test_get_status_configured(tmp_path, monkeypatch):
    """When timesheet.json exists, configured=True and config fields are returned."""
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    _write_config(tmp_path)

    result = get_status()

    assert result["configured"] is True
    assert result["username"] == VALID_CONFIG["username"]
    assert result["url"] == VALID_CONFIG["url"]
    assert result["work_hours"] == VALID_CONFIG["work_hours"]
    assert result["project"] == VALID_CONFIG["project"]
    assert result["default_activity"] == VALID_CONFIG["default_activity"]


def test_get_status_writes_launcher_when_absent(tmp_path, monkeypatch):
    """get_status writes the launcher file when it does not already exist."""
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    _write_config(tmp_path)

    launcher_path = tmp_path / ".claude" / "timesheet-setup"
    assert not launcher_path.exists()

    get_status()

    assert launcher_path.exists()
    assert launcher_path.is_file()


def test_get_status_launcher_content_runs_setup_script(tmp_path, monkeypatch):
    """The launcher file content references timesheet_setup.py."""
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    _write_config(tmp_path)

    get_status()

    launcher_path = tmp_path / ".claude" / "timesheet-setup"
    content = launcher_path.read_text()
    assert "timesheet_setup.py" in content


# --- validate_config MCP tool ---

def test_validate_config_valid(tmp_path, monkeypatch):
    """validate_config returns valid=True and no errors for a complete config."""
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    _write_config(tmp_path)

    result = validate_config()

    assert result == {"valid": True, "errors": []}


def test_validate_config_missing_field(tmp_path, monkeypatch):
    """validate_config returns valid=False and errors mentioning the missing field."""
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    config_without_employee = {k: v for k, v in VALID_CONFIG.items() if k != "employee"}
    _write_config(tmp_path, config_without_employee)

    result = validate_config()

    assert result["valid"] is False
    assert any("employee" in e for e in result["errors"])


def test_validate_config_no_config_file(tmp_path, monkeypatch):
    """validate_config returns valid=False and non-empty errors when file is missing."""
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))

    result = validate_config()

    assert result["valid"] is False
    assert len(result["errors"]) > 0


# --- read_messages MCP tool ---

def test_read_messages_returns_list(tmp_path, monkeypatch):
    """read_messages returns an empty list when there is no projects dir."""
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    _write_config(tmp_path)

    result = read_messages("2026-03-27")

    assert result == []


# --- Helpers for check_duplicate / submit_timesheet tests ---

def make_config_file(tmp_path: Path) -> None:
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    config = {
        "url": "https://erp.example.com",
        "username": "user@example.com",
        "password": "testpass",
        "employee": "EMP-001",
        "company": "ACME Corp",
        "project": "PROJ-001",
        "default_activity": "Development",
        "work_hours": 8,
        "start_time": "09:00",
    }
    (claude_dir / "timesheet.json").write_text(json.dumps(config))


# --- check_duplicate MCP tool ---

def test_check_duplicate_exists(tmp_path, monkeypatch):
    """check_duplicate returns {"exists": True} when ERPNextClient.check_duplicate returns True."""
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    make_config_file(tmp_path)
    monkeypatch.setattr(mcp_server.ERPNextClient, "login", lambda self: None)
    monkeypatch.setattr(mcp_server.ERPNextClient, "check_duplicate", lambda self, employee, date_str: True)

    result = check_duplicate("2026-03-27")

    assert result == {"exists": True}


def test_check_duplicate_not_exists(tmp_path, monkeypatch):
    """check_duplicate returns {"exists": False} when ERPNextClient.check_duplicate returns False."""
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    make_config_file(tmp_path)
    monkeypatch.setattr(mcp_server.ERPNextClient, "login", lambda self: None)
    monkeypatch.setattr(mcp_server.ERPNextClient, "check_duplicate", lambda self, employee, date_str: False)

    result = check_duplicate("2026-03-27")

    assert result == {"exists": False}


# --- submit_timesheet MCP tool ---

def test_submit_timesheet_success(tmp_path, monkeypatch):
    """submit_timesheet returns {"success": True, "name": "TS-0001"} on success."""
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    make_config_file(tmp_path)
    monkeypatch.setattr(mcp_server.ERPNextClient, "login", lambda self: None)
    monkeypatch.setattr(mcp_server.ERPNextClient, "create_timesheet", lambda self, doc: "TS-0001")
    monkeypatch.setattr(mcp_server.ERPNextClient, "submit_timesheet", lambda self, name: None)

    entries = [{"description": "Work", "hours": 8.0, "activity_type": "Development"}]
    result = submit_timesheet("2026-03-27", entries)

    assert result == {"success": True, "name": "TS-0001"}
