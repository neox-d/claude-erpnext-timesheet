import json
from pathlib import Path

import pytest

from mcp_server import (
    checkExisting, submitTimesheet, listTasks, createTask,
    listProjects, checkConfig, updateSettings,
)
import mcp_server


def make_config_file(tmp_path: Path) -> None:
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    config = {
        "username": "user@example.com",
        "employee": "EMP-001",
        "company": "ACME Corp",
        "project": "PROJ-001",
        "default_activity": "Development",
        "work_hours": 8,
        "start_time": "09:00",
    }
    (claude_dir / "timesheet.json").write_text(json.dumps(config))


def set_env_creds(monkeypatch) -> None:
    monkeypatch.setenv("CLAUDE_PLUGIN_OPTION_url", "https://erp.example.com")
    monkeypatch.setenv("CLAUDE_PLUGIN_OPTION_username", "user@example.com")
    monkeypatch.setenv("CLAUDE_PLUGIN_OPTION_password", "testpass")


@pytest.fixture(autouse=True)
def reset_client():
    mcp_server._client = None
    mcp_server._client_url = None
    mcp_server._client_username = None
    yield
    mcp_server._client = None
    mcp_server._client_url = None
    mcp_server._client_username = None


# --- checkExisting ---

def test_checkExisting_true(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    set_env_creds(monkeypatch)
    make_config_file(tmp_path)
    monkeypatch.setattr(mcp_server.ERPNextClient, "login", lambda self: None)
    monkeypatch.setattr(mcp_server.ERPNextClient, "check_duplicate",
                        lambda self, emp, date: True)
    assert checkExisting("2026-03-27") == {"exists": True}


def test_checkExisting_false(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    set_env_creds(monkeypatch)
    make_config_file(tmp_path)
    monkeypatch.setattr(mcp_server.ERPNextClient, "login", lambda self: None)
    monkeypatch.setattr(mcp_server.ERPNextClient, "check_duplicate",
                        lambda self, emp, date: False)
    assert checkExisting("2026-03-27") == {"exists": False}


# --- submitTimesheet ---

def test_submitTimesheet_success(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    set_env_creds(monkeypatch)
    make_config_file(tmp_path)
    monkeypatch.setattr(mcp_server.ERPNextClient, "login", lambda self: None)
    monkeypatch.setattr(mcp_server.ERPNextClient, "create_timesheet",
                        lambda self, doc: "TS-0001")
    monkeypatch.setattr(mcp_server.ERPNextClient, "submit_timesheet",
                        lambda self, name: None)
    entries = [{"description": "Work", "hours": 8.0, "activity_type": "Development"}]
    assert submitTimesheet("2026-03-27", entries) == {"success": True, "name": "TS-0001"}


# --- listTasks (tree structure) ---

def test_listTasks_returns_tree_structure(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    set_env_creds(monkeypatch)
    make_config_file(tmp_path)
    monkeypatch.setattr(mcp_server.ERPNextClient, "login", lambda self: None)
    flat = [
        {"name": "T-1", "subject": "Group", "is_group": 1, "status": "Open",
         "exp_end_date": "", "parent_task": None},
        {"name": "T-2", "subject": "Leaf", "is_group": 0, "status": "Open",
         "exp_end_date": "", "parent_task": "T-1"},
    ]
    monkeypatch.setattr(mcp_server.ERPNextClient, "list_tasks",
                        lambda self, project: flat)
    result = listTasks("PROJ-001")
    assert len(result) == 1
    assert result[0]["name"] == "T-1"
    assert result[0]["children"][0]["name"] == "T-2"


def test_listTasks_empty_project(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    set_env_creds(monkeypatch)
    make_config_file(tmp_path)
    monkeypatch.setattr(mcp_server.ERPNextClient, "login", lambda self: None)
    monkeypatch.setattr(mcp_server.ERPNextClient, "list_tasks",
                        lambda self, project: [])
    assert listTasks("PROJ-001") == []


# --- createTask ---

def test_createTask_success(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    set_env_creds(monkeypatch)
    make_config_file(tmp_path)
    monkeypatch.setattr(mcp_server.ERPNextClient, "login", lambda self: None)
    monkeypatch.setattr(mcp_server.ERPNextClient, "create_task",
                        lambda self, inp: ("TASK-002", []))
    assert createTask("Fix bug", "Desc", "PROJ-001", 4.0, "2026-03-27") == {
        "name": "TASK-002", "notes": []
    }


def test_createTask_notes_on_project_extension(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    set_env_creds(monkeypatch)
    make_config_file(tmp_path)
    monkeypatch.setattr(mcp_server.ERPNextClient, "login", lambda self: None)
    monkeypatch.setattr(mcp_server.ERPNextClient, "create_task",
                        lambda self, inp: ("TASK-003",
                                           ["Note: project end date extended to 2026-04-30"]))
    result = createTask("Fix bug", "Desc", "PROJ-001", 4.0, "2026-03-27")
    assert result["name"] == "TASK-003"
    assert "extended" in result["notes"][0]


def test_createTask_passes_parent_task(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    set_env_creds(monkeypatch)
    make_config_file(tmp_path)
    monkeypatch.setattr(mcp_server.ERPNextClient, "login", lambda self: None)

    received = []
    def fake_create_task(self, inp):
        received.append(inp)
        return ("TASK-001", [])
    monkeypatch.setattr(mcp_server.ERPNextClient, "create_task", fake_create_task)

    createTask("Subject", "Desc", "PROJ-001", 2.0, "2026-04-20",
                parent_task="T-GROUP-001")
    assert received[0]["parent_task"] == "T-GROUP-001"


def test_createTask_passes_is_group(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    set_env_creds(monkeypatch)
    make_config_file(tmp_path)
    monkeypatch.setattr(mcp_server.ERPNextClient, "login", lambda self: None)

    received = []
    def fake_create_task(self, inp):
        received.append(inp)
        return ("TASK-GRP-001", [])
    monkeypatch.setattr(mcp_server.ERPNextClient, "create_task", fake_create_task)

    createTask("Group Name", "Desc", "PROJ-001", 0.0, "2026-04-20",
                is_group=True)
    assert received[0]["is_group"] is True


# --- listProjects ---

def test_listProjects_returns_project_list(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    set_env_creds(monkeypatch)
    make_config_file(tmp_path)
    monkeypatch.setattr(mcp_server.ERPNextClient, "login", lambda self: None)
    projects = [
        {"id": "PROJ-0001", "label": "PROJ-0001 — My Project"},
        {"id": "PROJ-0050", "label": "PROJ-0050"},
    ]
    monkeypatch.setattr(mcp_server.ERPNextClient, "list_projects",
                        lambda self: projects)
    assert listProjects() == projects


def test_listProjects_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    set_env_creds(monkeypatch)
    make_config_file(tmp_path)
    monkeypatch.setattr(mcp_server.ERPNextClient, "login", lambda self: None)
    monkeypatch.setattr(mcp_server.ERPNextClient, "list_projects",
                        lambda self: [])
    assert listProjects() == []


# --- checkConfig ---

def test_checkConfig_credentials_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    monkeypatch.delenv("CLAUDE_PLUGIN_OPTION_url", raising=False)
    monkeypatch.delenv("CLAUDE_PLUGIN_OPTION_username", raising=False)
    monkeypatch.delenv("CLAUDE_PLUGIN_OPTION_password", raising=False)
    assert checkConfig() == {"configured": False, "reason": "credentials_missing"}


def test_checkConfig_auth_failed(tmp_path, monkeypatch):
    import requests as req
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    set_env_creds(monkeypatch)

    def fake_discover(url, username, password):
        resp = req.Response()
        resp.status_code = 401
        raise req.HTTPError(response=resp)

    monkeypatch.setattr(mcp_server, "discover", fake_discover)
    assert checkConfig() == {"configured": False, "reason": "auth_failed"}


def test_checkConfig_fresh_install_discovers_and_writes(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    set_env_creds(monkeypatch)

    discover_result = {
        "employee": "EMP-001",
        "company": "ACME Corp",
        "projects": [{"id": "PROJ-001", "label": "Project 1"}],
        "activity_types": ["Development", "Debugging"],
        "full_name": "Test User",
    }
    monkeypatch.setattr(mcp_server, "discover", lambda url, u, p: discover_result)

    result = checkConfig()
    assert result["configured"] is True
    assert result["employee"] == "EMP-001"
    assert result["company"] == "ACME Corp"
    assert result["url"] == "https://erp.example.com"
    assert result["_projects"] == [{"id": "PROJ-001", "label": "Project 1"}]
    assert result["_activity_types"] == ["Development", "Debugging"]

    config_path = tmp_path / ".claude" / "timesheet.json"
    assert config_path.exists()
    saved = json.loads(config_path.read_text())
    assert saved["employee"] == "EMP-001"
    assert "password" not in saved
    assert "url" not in saved


def test_checkConfig_already_configured(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    set_env_creds(monkeypatch)
    make_config_file(tmp_path)

    result = checkConfig()
    assert result["configured"] is True
    assert result["project"] == "PROJ-001"
    assert result["default_activity"] == "Development"
    assert result["url"] == "https://erp.example.com"
    assert result["employee"] == "EMP-001"


def test_checkConfig_missing_defaults_returns_empty_strings(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    set_env_creds(monkeypatch)

    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    config = {
        "username": "user@example.com",
        "employee": "EMP-001",
        "company": "ACME Corp",
        "project": "",
        "default_activity": "",
        "work_hours": 8,
        "_projects": [{"id": "PROJ-001", "label": "P1"}],
        "_activity_types": ["Development"],
    }
    (claude_dir / "timesheet.json").write_text(json.dumps(config))

    result = checkConfig()
    assert result["configured"] is True
    assert result["project"] == ""
    assert result["default_activity"] == ""
    assert result["_projects"] == [{"id": "PROJ-001", "label": "P1"}]


# --- updateSettings ---

def test_updateSettings_writes_project_and_activity(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    set_env_creds(monkeypatch)
    make_config_file(tmp_path)

    result = updateSettings(project="PROJ-002", activity_type="Debugging")

    assert result["configured"] is True
    assert result["project"] == "PROJ-002"
    assert result["default_activity"] == "Debugging"
    assert result["url"] == "https://erp.example.com"
    assert result["username"] == "user@example.com"
    assert "setup_command" not in result

    saved = json.loads((tmp_path / ".claude" / "timesheet.json").read_text())
    assert saved["project"] == "PROJ-002"
    assert saved["default_activity"] == "Debugging"


def test_updateSettings_strips_staging_lists(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    set_env_creds(monkeypatch)

    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    config = {
        "username": "user@example.com",
        "employee": "EMP-001",
        "company": "ACME Corp",
        "project": "",
        "default_activity": "",
        "work_hours": 8,
        "_projects": [{"id": "PROJ-001", "label": "P1"}],
        "_activity_types": ["Development"],
    }
    (claude_dir / "timesheet.json").write_text(json.dumps(config))

    updateSettings(project="PROJ-001", activity_type="Development")

    saved = json.loads((claude_dir / "timesheet.json").read_text())
    assert "_projects" not in saved
    assert "_activity_types" not in saved
