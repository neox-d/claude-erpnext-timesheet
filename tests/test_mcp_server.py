import json
from pathlib import Path

import pytest

from mcp_server import get_status


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
