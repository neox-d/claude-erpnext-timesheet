import json
from pathlib import Path

import pytest

from mcp_server import checkExisting, submitTimesheet, listTasks, createTask
import mcp_server


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


# --- checkExisting ---

def test_checkExisting_true(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    make_config_file(tmp_path)
    monkeypatch.setattr(mcp_server.ERPNextClient, "login", lambda self: None)
    monkeypatch.setattr(mcp_server.ERPNextClient, "check_duplicate",
                        lambda self, emp, date: True)
    assert checkExisting("2026-03-27") == {"exists": True}


def test_checkExisting_false(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    make_config_file(tmp_path)
    monkeypatch.setattr(mcp_server.ERPNextClient, "login", lambda self: None)
    monkeypatch.setattr(mcp_server.ERPNextClient, "check_duplicate",
                        lambda self, emp, date: False)
    assert checkExisting("2026-03-27") == {"exists": False}


# --- submitTimesheet ---

def test_submitTimesheet_success(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
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
    make_config_file(tmp_path)
    monkeypatch.setattr(mcp_server.ERPNextClient, "login", lambda self: None)
    monkeypatch.setattr(mcp_server.ERPNextClient, "list_tasks",
                        lambda self, project: [])
    assert listTasks("PROJ-001") == []


# --- createTask ---

def test_createTask_success(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    make_config_file(tmp_path)
    monkeypatch.setattr(mcp_server.ERPNextClient, "login", lambda self: None)
    monkeypatch.setattr(mcp_server.ERPNextClient, "create_task",
                        lambda self, inp: ("TASK-002", []))
    assert createTask("Fix bug", "Desc", "PROJ-001", 4.0, "2026-03-27") == {
        "name": "TASK-002", "notes": []
    }


def test_createTask_notes_on_project_extension(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
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
