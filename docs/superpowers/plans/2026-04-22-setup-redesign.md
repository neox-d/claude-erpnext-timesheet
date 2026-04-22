# Setup Redesign: userConfig + uv — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the custom venv/credential stack with Claude Code's native `userConfig` dialog (masked password, keychain storage) and `uv` for Python dependency management.

**Architecture:** `plugin.json` declares three `userConfig` fields (url, username, password); Claude Code collects them at install time and passes them to the MCP server as `CLAUDE_PLUGIN_OPTION_*` env vars. The MCP server's `checkConfig` tool runs ERPNext discovery on first call and caches non-credential config to `~/.claude/timesheet.json`. The MCP server starts via `uv run --project ${CLAUDE_PLUGIN_ROOT}` — no venv scripts.

**Tech Stack:** Python 3.11+, uv, mcp[cli], requests, pytest

---

## File Map

| Action | Path | Change |
|---|---|---|
| Modify | `.claude-plugin/plugin.json` | Add `userConfig`; switch MCP command to `uv run` |
| Modify | `skills/timesheet/mcp_server.py` | Read creds from env vars; add `checkConfig`; remove crypto |
| Modify | `skills/timesheet/SKILL.md` | Rewrite Step 0 |
| Modify | `tests/test_mcp_server.py` | Add `set_env_creds`; drop creds from config fixture; add `checkConfig` tests |
| Modify | `pyproject.toml` | Remove `cryptography` dependency |
| Delete | `hooks/` (entire directory) | Replaced by `uv run` + `userConfig` |
| Delete | `skills/timesheet/scripts/` (entire directory) | Replaced by `userConfig` dialog |
| Delete | `config-template.json` | Replaced by `userConfig` schema |
| Modify | `README.md` | New installation instructions |

---

### Task 1: Update plugin.json

**Files:**
- Modify: `.claude-plugin/plugin.json`

- [ ] **Step 1: Replace plugin.json content**

Write `.claude-plugin/plugin.json`:

```json
{
  "name": "erpnext-timesheet",
  "description": "Automate daily ERPNext timesheet filling from your Claude conversation history",
  "version": "2.1.0",
  "author": {
    "name": "neox-d"
  },
  "repository": "https://github.com/neox-d/claude-erpnext-timesheet",
  "homepage": "https://github.com/neox-d/claude-erpnext-timesheet",
  "license": "MIT",
  "keywords": ["erpnext", "timesheet", "frappe", "productivity", "time-tracking"],
  "userConfig": {
    "url": {
      "type": "string",
      "title": "ERPNext URL",
      "description": "Your ERPNext instance URL, e.g. https://erpnext.example.com",
      "required": true
    },
    "username": {
      "type": "string",
      "title": "Username (Email)",
      "description": "Your ERPNext login email address",
      "required": true
    },
    "password": {
      "type": "string",
      "title": "Password",
      "description": "Your ERPNext password",
      "sensitive": true,
      "required": true
    }
  },
  "mcpServers": {
    "erpnext-timesheet": {
      "command": "uv",
      "args": [
        "run",
        "--project", "${CLAUDE_PLUGIN_ROOT}",
        "${CLAUDE_PLUGIN_ROOT}/skills/timesheet/mcp_server.py"
      ]
    }
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add .claude-plugin/plugin.json
git commit -m "feat: add userConfig credentials dialog; switch MCP to uv run"
```

---

### Task 2: Refactor credential loading in mcp_server.py

Credentials move from `~/.claude/timesheet.json` into env vars set by Claude Code. `_get_client()` no longer takes a `config` argument — it reads directly from env. `timesheet.json` keeps only non-credential fields; `username` (email, non-sensitive) is stored there for use in the timesheet document.

**Files:**
- Modify: `skills/timesheet/mcp_server.py`
- Modify: `tests/test_mcp_server.py`

- [ ] **Step 1: Write failing tests — update fixtures and all existing tests**

Replace the entire content of `tests/test_mcp_server.py` with the following (adds `set_env_creds`, removes credentials from config fixture, adds autouse reset, adds `set_env_creds` call to every test):

```python
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
```

- [ ] **Step 2: Run tests — expect failures**

```bash
cd /home/neox/Work/erpnext-timesheet
python -m pytest tests/test_mcp_server.py -v 2>&1 | head -40
```

Expected: `ImportError` on `checkConfig` (doesn't exist yet) — that's the right failure.

- [ ] **Step 3: Update mcp_server.py — add `import os`, add `_load_credentials`, update `_get_client`, remove crypto, update `_AUTH_ERROR`, remove `_validate_config_fields`**

At the top of `skills/timesheet/mcp_server.py`, change the imports block:

Remove line:
```python
from scripts.crypto import decrypt_password, encrypt_password
```

Add `import os` to the stdlib imports block (alphabetically after `import json`):
```python
import os
```

Replace the entire client cache section (lines 197–235, from `_client: ERPNextClient | None = None` through `def _load_config() -> dict:`) with:

```python
# ---------------------------------------------------------------------------
# Client cache — one login per MCP server session
# ---------------------------------------------------------------------------

_client: ERPNextClient | None = None
_client_url: str | None = None
_client_username: str | None = None

_AUTH_ERROR = {
    "error": "auth_failed",
    "message": "ERPNext authentication failed. Run `/plugin config erpnext-timesheet` to update your credentials, then re-invoke the skill.",
}


def _load_credentials() -> dict | None:
    url = os.environ.get("CLAUDE_PLUGIN_OPTION_url", "").rstrip("/")
    username = os.environ.get("CLAUDE_PLUGIN_OPTION_username", "")
    password = os.environ.get("CLAUDE_PLUGIN_OPTION_password", "")
    if not all([url, username, password]):
        return None
    return {"url": url, "username": username, "password": password}


def _get_client() -> ERPNextClient:
    global _client, _client_url, _client_username
    creds = _load_credentials()
    if creds is None:
        raise RuntimeError("ERPNext credentials not configured")
    url, username, password = creds["url"], creds["username"], creds["password"]
    if _client is None or _client_url != url or _client_username != username:
        if _client is not None:
            _client.logout()
        _client = ERPNextClient(url, username, password)
        _client_url = url
        _client_username = username
    return _client


def _clear_client():
    global _client, _client_url, _client_username
    if _client is not None:
        _client.logout()
    _client = None
    _client_url = None
    _client_username = None


atexit.register(_clear_client)
signal.signal(signal.SIGTERM, lambda *_: (_clear_client(), sys.exit(0)))


def _load_config() -> dict:
    return json.loads((Path.home() / ".claude" / "timesheet.json").read_text())


def _is_auth_error(e: requests.HTTPError) -> bool:
    return e.response is not None and e.response.status_code in (401, 403)
```

Delete the `_validate_config_fields` function entirely (lines 292–312 in the original).

Update the five MCP tools that call `_get_client(config)` — remove the `config` argument and drop the `_load_config()` call where config is only used for the client:

`checkExisting` (keep `_load_config()` — still needs `config["employee"]`):
```python
@mcp.tool()
def checkExisting(date: str) -> dict:
    """Check whether a timesheet already exists for the given date (YYYY-MM-DD)."""
    config = _load_config()
    try:
        client = _get_client()
        return {"exists": client.check_duplicate(config["employee"], date)}
    except requests.HTTPError as e:
        if _is_auth_error(e):
            _clear_client()
            return _AUTH_ERROR
        raise
```

`submitTimesheet` (keep `_load_config()` — still needs config for `build_timesheet_doc`):
```python
@mcp.tool()
def submitTimesheet(date: str, entries: list) -> dict:
    """Build and submit a timesheet for the given date (YYYY-MM-DD) with the provided entries."""
    config = _load_config()
    try:
        client = _get_client()
        doc = build_timesheet_doc(config, entries, date_str=date)
        name = client.create_timesheet(doc)
        client.submit_timesheet(name)
        _clear_client()
        return {"success": True, "name": name}
    except requests.HTTPError as e:
        if _is_auth_error(e):
            _clear_client()
            return _AUTH_ERROR
        raise
```

`listTasks` (drop `_load_config()` — config only used for client):
```python
@mcp.tool()
def listTasks(project: str) -> list:
    """Return active tasks for the given project as a nested tree (groups contain children)."""
    try:
        flat = _get_client().list_tasks(project)
        return _build_tree(flat)
    except requests.HTTPError as e:
        if _is_auth_error(e):
            _clear_client()
            return [_AUTH_ERROR]
        raise
```

`listProjects` (drop `_load_config()`):
```python
@mcp.tool()
def listProjects() -> list:
    """Return all non-Completed/non-Cancelled projects as [{id, label}]."""
    try:
        return _get_client().list_projects()
    except requests.HTTPError as e:
        if _is_auth_error(e):
            _clear_client()
            return [_AUTH_ERROR]
        raise
```

`createTask` (drop `_load_config()`):
```python
@mcp.tool()
def createTask(subject: str, description: str, project: str, hours: float, date: str,
               parent_task: str = None, is_group: bool = False) -> dict:
    """Create a task in ERPNext. Auto-extends project end date on InvalidDates errors."""
    try:
        name, notes = _get_client().create_task({
            "subject": subject,
            "description": description,
            "project": project,
            "hours": hours,
            "date": date,
            "parent_task": parent_task,
            "is_group": is_group,
        })
        return {"name": name, "notes": notes}
    except requests.HTTPError as e:
        if _is_auth_error(e):
            _clear_client()
            return _AUTH_ERROR
        raise
```

- [ ] **Step 4: Run tests — expect passing**

```bash
python -m pytest tests/test_mcp_server.py -v -k "not checkConfig and not updateSettings"
```

Expected: All existing tests PASS. `checkConfig` tests still fail (not yet implemented).

- [ ] **Step 5: Commit**

```bash
git add skills/timesheet/mcp_server.py tests/test_mcp_server.py
git commit -m "refactor: read credentials from env vars; remove crypto dependency"
```

---

### Task 3: Add checkConfig MCP tool

`checkConfig` is the first call in Step 0. It checks env vars, runs ERPNext discovery if `timesheet.json` is missing, and returns a full status dict.

**Files:**
- Modify: `skills/timesheet/mcp_server.py`
- Modify: `tests/test_mcp_server.py`

- [ ] **Step 1: Add checkConfig tests to test_mcp_server.py**

Append to `tests/test_mcp_server.py`:

```python
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
```

- [ ] **Step 2: Run tests — expect checkConfig tests to fail**

```bash
python -m pytest tests/test_mcp_server.py -v -k "checkConfig"
```

Expected: All 5 `checkConfig` tests FAIL with `ImportError` or `AttributeError`.

- [ ] **Step 3: Add checkConfig tool to mcp_server.py**

In `skills/timesheet/mcp_server.py`, add the `checkConfig` tool immediately before `readHistory` (i.e., as the first MCP tool):

```python
@mcp.tool()
def checkConfig() -> dict:
    """Check plugin configuration. Runs ERPNext discovery on first call if timesheet.json is missing."""
    creds = _load_credentials()
    if creds is None:
        return {"configured": False, "reason": "credentials_missing"}

    config_path = Path.home() / ".claude" / "timesheet.json"
    if not config_path.exists():
        try:
            result = discover(creds["url"], creds["username"], creds["password"])
        except requests.HTTPError as e:
            if _is_auth_error(e):
                return {"configured": False, "reason": "auth_failed"}
            raise
        except Exception:
            return {"configured": False, "reason": "auth_failed"}

        config = {
            "username": creds["username"],
            "employee": result["employee"],
            "company": result["company"],
            "project": "",
            "default_activity": "",
            "work_hours": 8.0,
            "start_time": "09:00",
            "timezone": "",
            "_projects": result["projects"],
            "_activity_types": result["activity_types"],
        }
        write_config(config, str(config_path))
    else:
        config = json.loads(config_path.read_text())

    return {
        "configured": True,
        "username": config.get("username", creds["username"]),
        "url": creds["url"],
        "work_hours": config.get("work_hours", 8),
        "project": config.get("project", ""),
        "default_activity": config.get("default_activity", ""),
        "employee": config.get("employee", ""),
        "company": config.get("company", ""),
        "_projects": config.get("_projects", []),
        "_activity_types": config.get("_activity_types", []),
    }
```

- [ ] **Step 4: Run tests — expect passing**

```bash
python -m pytest tests/test_mcp_server.py -v -k "checkConfig"
```

Expected: All 5 `checkConfig` tests PASS.

- [ ] **Step 5: Run full suite**

```bash
python -m pytest tests/test_mcp_server.py -v
```

Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
git add skills/timesheet/mcp_server.py tests/test_mcp_server.py
git commit -m "feat: add checkConfig MCP tool with lazy ERPNext discovery"
```

---

### Task 4: Update updateSettings return value

`updateSettings` currently returns `url`/`username` from `timesheet.json` (where they no longer live) and a stale `setup_command` field. Fix it to read `url` from env vars.

**Files:**
- Modify: `skills/timesheet/mcp_server.py`
- Modify: `tests/test_mcp_server.py`

- [ ] **Step 1: Add failing test for updateSettings**

Append to `tests/test_mcp_server.py`:

```python
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
```

- [ ] **Step 2: Run test — expect failure**

```bash
python -m pytest tests/test_mcp_server.py::test_updateSettings_writes_project_and_activity -v
```

Expected: FAIL — `setup_command` present in return, and `url` from old config (not env var).

- [ ] **Step 3: Update updateSettings in mcp_server.py**

Replace the `updateSettings` tool:

```python
@mcp.tool()
def updateSettings(project: str = None, activity_type: str = None,
                   work_hours: float = None, start_time: str = None,
                   timezone: str = None) -> dict:
    """Update one or more config settings. Clears temporary _projects/_activity_types lists."""
    config_path = Path.home() / ".claude" / "timesheet.json"
    config = json.loads(config_path.read_text())
    creds = _load_credentials()

    if project is not None:
        config["project"] = project
    if activity_type is not None:
        config["default_activity"] = activity_type
    if work_hours is not None:
        config["work_hours"] = work_hours
    if start_time is not None:
        config["start_time"] = start_time
    if timezone is not None:
        config["timezone"] = timezone

    config.pop("_projects", None)
    config.pop("_activity_types", None)

    config_path.write_text(json.dumps(config, indent=2))
    return {
        "configured": True,
        "username": config.get("username", creds["username"] if creds else ""),
        "url": creds["url"] if creds else "",
        "work_hours": config.get("work_hours", 8),
        "project": config.get("project"),
        "default_activity": config.get("default_activity"),
    }
```

- [ ] **Step 4: Run full test suite**

```bash
python -m pytest tests/test_mcp_server.py -v
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add skills/timesheet/mcp_server.py tests/test_mcp_server.py
git commit -m "fix: updateSettings reads url from env vars; remove stale setup_command field"
```

---

### Task 5: Rewrite SKILL.md Step 0

Replace direct file read with `checkConfig` MCP call.

**Files:**
- Modify: `skills/timesheet/SKILL.md`

- [ ] **Step 1: Replace Step 0 in SKILL.md**

In `skills/timesheet/SKILL.md`, replace the entire `## Step 0: Setup and Date Resolution` section with:

```markdown
## Step 0: Setup and Date Resolution

**Resolve the target date.** Read the invocation message:
- If it specifies a past date (e.g. "for yesterday", "for 2026-03-24", "last Friday") — resolve it to `YYYY-MM-DD` and store as `TARGET_DATE`.
- Otherwise use today's date.

**Call `checkConfig` silently.** Store the result as `CONFIG`.

**If `CONFIG.configured` is `false` and `reason` is `credentials_missing`:**

> Your ERPNext credentials aren't configured. Run `/plugin config erpnext-timesheet` to enter your URL, username, and password, then re-run `/timesheet`.

Stop here.

**If `CONFIG.configured` is `false` and `reason` is `auth_failed`:**

> ERPNext authentication failed. Run `/plugin config erpnext-timesheet` to update your credentials, then re-run `/timesheet`.

Stop here.

**If `project` or `default_activity` is empty:**

Credentials are saved but defaults are missing. Use `AskUserQuestion` with two questions using `CONFIG._projects` and `CONFIG._activity_types`:
- **Default Project**: up to 4 options from `_projects` (show `label`, value is `id`); mark current default as "(Selected)"
- **Default Activity**: always offer these 4 options: Development, Development Testing, Debugging, Debug & Fix — plus the user can type Other for anything else

Call `updateSettings` with the selected `project` and `activity_type`. Store the return value as `STATUS` — it has the full configured shape. Proceed to Step 1.

**Otherwise** build `STATUS` directly from `CONFIG`:
```
STATUS = {
  configured: true,
  username: CONFIG.username,
  url: CONFIG.url,
  work_hours: CONFIG.work_hours (default 8),
  project: CONFIG.project,
  default_activity: CONFIG.default_activity,
}
```

**If user mentioned reconfiguring:** tell the user to run `/plugin config erpnext-timesheet`, then re-run `/timesheet`. Stop here.

Announce: `Logging work for TARGET_DATE — <username> on <url>`

Proceed to Step 1.
```

Also update the version in the frontmatter from `2.0.11` to `2.1.0`.

- [ ] **Step 2: Commit**

```bash
git add skills/timesheet/SKILL.md
git commit -m "feat: SKILL.md Step 0 uses checkConfig MCP tool; remove file-read approach"
```

---

### Task 6: Delete dead files and clean pyproject.toml

**Files:**
- Delete: `hooks/` directory
- Delete: `skills/timesheet/scripts/` directory
- Delete: `config-template.json`
- Modify: `pyproject.toml`

- [ ] **Step 1: Delete dead files**

```bash
rm -rf /home/neox/Work/erpnext-timesheet/hooks
rm -rf /home/neox/Work/erpnext-timesheet/skills/timesheet/scripts
rm -f /home/neox/Work/erpnext-timesheet/config-template.json
```

- [ ] **Step 2: Remove cryptography from pyproject.toml**

In `pyproject.toml`, change the `dependencies` line from:
```toml
dependencies = ["requests>=2.31", "cryptography>=41.0", "mcp[cli]>=1.0"]
```
to:
```toml
dependencies = ["requests>=2.31", "mcp[cli]>=1.0"]
```

- [ ] **Step 3: Run full test suite**

```bash
python -m pytest tests/ -v
```

Expected: All tests PASS. (The deleted scripts had no remaining imports in `mcp_server.py` since Task 2 removed them.)

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "chore: delete hooks/, scripts/, config-template.json; remove cryptography dep"
```

---

### Task 7: Update README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Rewrite README.md**

Replace the entire content of `README.md`:

```markdown
# claude-erpnext-timesheet

A Claude Code plugin that automatically fills your daily ERPNext timesheet from your Claude conversation history.

Run `/timesheet` at the end of the day and Claude will:
1. Read your conversations from the day
2. Synthesise billable task entries with descriptions and hours
3. Let you review and edit them (add, delete, edit, assign tasks, adjust hours)
4. Submit the approved timesheet to ERPNext

## Requirements

- [Claude Code](https://claude.ai/claude-code) CLI
- [uv](https://docs.astral.sh/uv/) — install once per machine:
  ```
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```
- ERPNext / Frappe v15 instance with API access

## Installation

```
/plugin install erpnext-timesheet@neox-d-plugins
```

Claude Code will prompt for your ERPNext credentials:

```
ERPNext URL   _______________
Username      _______________
Password      •••••••••••••••
```

Credentials are stored securely in your system keychain — never in a plain text file.

## First run

```
/timesheet
```

On first use, Claude connects to your ERPNext instance and prompts you to select a default project and activity type. After that, `/timesheet` runs without any setup.

## Usage

```
/timesheet              — fill today's timesheet
/timesheet yesterday    — fill yesterday's
/timesheet 2026-04-21  — fill a specific date
```

## Updating credentials

If your ERPNext password changes:

```
/plugin config erpnext-timesheet
```

## License

MIT
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: rewrite README for userConfig + uv installation flow"
```

---

## Self-Review

**Spec coverage:**
- `userConfig` in `plugin.json` ✓ Task 1
- `uv run` MCP command ✓ Task 1
- `mcp_server.py` reads env vars ✓ Task 2
- `checkConfig` tool with lazy discovery ✓ Task 3
- `~/.claude/timesheet.json` credentials-free ✓ Tasks 2 + 3
- `updateSettings` reads url from env ✓ Task 4
- SKILL.md Step 0 rewrite ✓ Task 5
- Delete `hooks/`, `scripts/`, `config-template.json` ✓ Task 6
- Remove `cryptography` dep ✓ Task 6
- README updated ✓ Task 7

**No placeholders found.**

**Type consistency:** `checkConfig` returns `configured`, `username`, `url`, `work_hours`, `project`, `default_activity`, `employee`, `company`, `_projects`, `_activity_types`. SKILL.md Step 0 reads `CONFIG.configured`, `CONFIG.project`, `CONFIG.default_activity`, `CONFIG._projects`, `CONFIG._activity_types`, `CONFIG.username`, `CONFIG.url` — all match. `updateSettings` returns same shape minus `employee`/`company`/`_projects`/`_activity_types` — matches SKILL.md which stores the return as `STATUS` with only `configured`, `username`, `url`, `work_hours`, `project`, `default_activity`.
