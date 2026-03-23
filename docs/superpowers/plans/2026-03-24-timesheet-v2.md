# Timesheet v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add task field support, hours override, and interactive setup to the ERPNext timesheet skill.

**Architecture:** Four independent changes: new `task_manager.py` CLI for task/project operations; `setup.py` gains `full_name` in discover(); `erpnext_client.py` passes through optional `task` field; `timesheet.md` skill updated for interactive setup wizard (Step 0), TUI task management and hours override (Step 5), and updated entries format (Step 6).

**Tech Stack:** Python 3.11+, requests, pytest, pytest-mock. All scripts are CLI tools invoked by the Claude Code skill via bash.

**Spec:** `docs/superpowers/specs/2026-03-24-timesheet-v2-design.md`

**Run all tests:** `cd /home/neox/Work/erpnext-timesheet && python -m pytest tests/ -v`

---

## File Map

| File | Change |
|---|---|
| `scripts/task_manager.py` | **Create** — `get_tasks()`, `create_task()`, `extend_project_end_date()`, `main()` |
| `scripts/setup.py` | **Modify** — `discover()` fetches and returns `full_name` |
| `scripts/erpnext_client.py` | **Modify** — `build_timesheet_doc()` passes through optional `task` per entry |
| `skills/timesheet/timesheet.md` | **Modify** — Step 0 (interactive wizard), Step 5 (task TUI + hours override), Step 6 (task in entries) |
| `tests/test_task_manager.py` | **Create** — 6 test cases for all three operations |
| `tests/test_setup.py` | **Modify** — extend existing shape test; add 2 full_name fallback tests |
| `tests/test_erpnext_client.py` | **Modify** — add 3 task-field test cases to build_timesheet_doc |

---

## Task 1: `task_manager.py` — task and project operations

**Files:**
- Create: `scripts/task_manager.py`
- Create: `tests/test_task_manager.py`

---

- [ ] **Step 1: Create the test file with the get_tasks tests**

Create `tests/test_task_manager.py`:

```python
import json
import sys
from unittest.mock import MagicMock, patch, call

import pytest
import requests

from scripts.task_manager import get_tasks, create_task, extend_project_end_date


def mock_response(status_code=200, json_data=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.ok = status_code < 400
    resp.json.return_value = json_data or {}
    if status_code >= 400:
        resp.raise_for_status.side_effect = requests.HTTPError(response=resp)
    else:
        resp.raise_for_status.return_value = None
    return resp


BASE_CONFIG = {
    "url": "https://erp.example.com",
    "username": "user@example.com",
    "password": "pass",
    "project": "PROJ-001",
}


# --- get_tasks ---

def test_get_tasks_returns_list():
    """get_tasks() returns a list of task dicts."""
    task_data = [
        {"name": "TASK-001", "subject": "Fix login", "status": "Open"},
        {"name": "TASK-002", "subject": "Add tests", "status": "Overdue"},
    ]
    with patch("scripts.task_manager.requests.Session") as mock_cls:
        session = MagicMock()
        mock_cls.return_value = session
        session.post.return_value = mock_response(200)
        session.get.return_value = mock_response(200, {"data": task_data})

        result = get_tasks(BASE_CONFIG, "PROJ-001")

    assert result == task_data


def test_get_tasks_returns_empty_list():
    """get_tasks() returns [] when no tasks found."""
    with patch("scripts.task_manager.requests.Session") as mock_cls:
        session = MagicMock()
        mock_cls.return_value = session
        session.post.return_value = mock_response(200)
        session.get.return_value = mock_response(200, {"data": []})

        result = get_tasks(BASE_CONFIG, "PROJ-001")

    assert result == []


def test_get_tasks_raises_on_http_error():
    """get_tasks() raises HTTPError on failed request."""
    with patch("scripts.task_manager.requests.Session") as mock_cls:
        session = MagicMock()
        mock_cls.return_value = session
        session.post.return_value = mock_response(200)
        session.get.return_value = mock_response(403)

        with pytest.raises(requests.HTTPError):
            get_tasks(BASE_CONFIG, "PROJ-001")


# --- create_task ---

def test_create_task_success():
    """create_task() returns task name on success."""
    task_input = {
        "subject": "Build feature",
        "description": "Details here",
        "project": "PROJ-001",
        "hours": 4.0,
        "date": "2026-03-24",
    }
    with patch("scripts.task_manager.requests.Session") as mock_cls:
        session = MagicMock()
        mock_cls.return_value = session
        session.post.return_value = mock_response(200)
        session.request.return_value = mock_response(200, {"data": {"name": "TASK-999"}})

        name, notes = create_task(BASE_CONFIG, task_input)

    assert name == "TASK-999"
    assert notes == []


def test_create_task_auto_extends_on_invalid_dates(capsys):
    """create_task() extends project end date when ERPNext returns InvalidDates, then retries."""
    task_input = {
        "subject": "Build feature",
        "description": "Details",
        "project": "PROJ-001",
        "hours": 4.0,
        "date": "2026-03-24",
    }
    invalid_dates_resp = MagicMock()
    invalid_dates_resp.status_code = 417
    invalid_dates_resp.ok = False
    invalid_dates_resp.json.return_value = {"exc_type": "InvalidDates"}
    invalid_dates_resp.raise_for_status.side_effect = requests.HTTPError(response=invalid_dates_resp)

    success_resp = mock_response(200, {"data": {"name": "TASK-999"}})
    extend_resp = mock_response(200, {"data": {}})

    with patch("scripts.task_manager.requests.Session") as mock_cls:
        session = MagicMock()
        mock_cls.return_value = session
        session.post.return_value = mock_response(200)
        session.request.side_effect = [
            invalid_dates_resp,  # first create attempt
            extend_resp,          # extend project
            success_resp,         # retry create
        ]

        name, notes = create_task(BASE_CONFIG, task_input)

    assert name == "TASK-999"
    assert any("extended" in n for n in notes)


def test_create_task_exits_nonzero_on_unrecoverable_error():
    """create_task() raises SystemExit when retry also fails."""
    task_input = {
        "subject": "Build feature",
        "description": "Details",
        "project": "PROJ-001",
        "hours": 4.0,
        "date": "2026-03-24",
    }
    invalid_dates_resp = MagicMock()
    invalid_dates_resp.status_code = 417
    invalid_dates_resp.ok = False
    invalid_dates_resp.json.return_value = {"exc_type": "InvalidDates"}
    invalid_dates_resp.raise_for_status.side_effect = requests.HTTPError(response=invalid_dates_resp)

    extend_resp = mock_response(200, {"data": {}})

    with patch("scripts.task_manager.requests.Session") as mock_cls:
        session = MagicMock()
        mock_cls.return_value = session
        session.post.return_value = mock_response(200)
        # Both create attempts fail with InvalidDates; extend succeeds
        session.request.side_effect = [
            invalid_dates_resp,
            extend_resp,
            invalid_dates_resp,
        ]

        with pytest.raises(SystemExit) as exc_info:
            create_task(BASE_CONFIG, task_input)

    assert exc_info.value.code != 0


# --- extend_project_end_date ---

def test_extend_project_end_date_success():
    """extend_project_end_date() returns success dict."""
    with patch("scripts.task_manager.requests.Session") as mock_cls:
        session = MagicMock()
        mock_cls.return_value = session
        session.post.return_value = mock_response(200)
        session.request.return_value = mock_response(200, {"data": {}})

        result = extend_project_end_date(BASE_CONFIG, "PROJ-001", "2026-04-30")

    assert result == {"success": True}


def test_extend_project_end_date_raises_on_failure():
    """extend_project_end_date() raises HTTPError on failure."""
    with patch("scripts.task_manager.requests.Session") as mock_cls:
        session = MagicMock()
        mock_cls.return_value = session
        session.post.return_value = mock_response(200)
        session.request.return_value = mock_response(500)

        with pytest.raises(requests.HTTPError):
            extend_project_end_date(BASE_CONFIG, "PROJ-001", "2026-04-30")
```

- [ ] **Step 2: Run the tests to confirm they fail**

```bash
cd /home/neox/Work/erpnext-timesheet && python -m pytest tests/test_task_manager.py -v
```

Expected: `ModuleNotFoundError` or `ImportError` — `task_manager` does not exist yet.

- [ ] **Step 3: Create `scripts/task_manager.py`**

```python
#!/usr/bin/env python3
"""
ERPNext task and project management.

Usage:
  python3 task_manager.py --config ~/.claude/timesheet.json --action get-tasks --project PROJ-XXXX
  python3 task_manager.py --config ~/.claude/timesheet.json --action create-task --task-file /tmp/task.json
  python3 task_manager.py --config ~/.claude/timesheet.json --action extend-project --project PROJ-XXXX --date YYYY-MM-DD
"""
import argparse
import calendar
import json
import sys
from datetime import date
from pathlib import Path

import requests


def _login(config: dict) -> requests.Session:
    """Create an authenticated session."""
    session = requests.Session()
    base = config["url"].rstrip("/")
    resp = session.post(
        f"{base}/api/method/login",
        data={"usr": config["username"], "pwd": config["password"]},
    )
    resp.raise_for_status()
    return session


def get_tasks(config: dict, project: str) -> list:
    """Fetch all non-cancelled tasks for a project."""
    base = config["url"].rstrip("/")
    session = _login(config)
    resp = session.get(
        f"{base}/api/resource/Task",
        params={
            "filters": json.dumps([
                ["project", "=", project],
                ["status", "!=", "Cancelled"],
            ]),
            "fields": json.dumps(["name", "subject", "status"]),
            "limit": 50,
        },
    )
    resp.raise_for_status()
    return resp.json().get("data", [])


def _next_month_end(today: date) -> str:
    """Return last calendar day of the month following today, as YYYY-MM-DD."""
    if today.month == 12:
        next_year, next_month = today.year + 1, 1
    else:
        next_year, next_month = today.year, today.month + 1
    last_day = calendar.monthrange(next_year, next_month)[1]
    return date(next_year, next_month, last_day).isoformat()


def extend_project_end_date(config: dict, project: str, new_date: str) -> dict:
    """Extend a project's expected end date."""
    base = config["url"].rstrip("/")
    session = _login(config)
    resp = session.request(
        "PUT",
        f"{base}/api/resource/Project/{project}",
        json={"expected_end_date": new_date},
    )
    resp.raise_for_status()
    return {"success": True}


def create_task(config: dict, task_input: dict) -> tuple[str, list[str]]:
    """
    Create a task in ERPNext. Returns (task_name, notes).
    notes is a list of informational strings (e.g. about project extension).
    Auto-extends project end date on InvalidDates, then retries once.
    Raises SystemExit(1) on unrecoverable error.
    """
    base = config["url"].rstrip("/")
    session = _login(config)
    notes = []

    doc = {
        "subject": task_input["subject"],
        "description": task_input["description"],
        "project": task_input["project"],
        "expected_time": task_input["hours"],
        "exp_start_date": task_input["date"],
        "exp_end_date": task_input["date"],
        "custom_planned_completion_date": task_input["date"],
        "status": "Completed",
    }

    def _attempt_create():
        return session.request("POST", f"{base}/api/resource/Task", json=doc)

    resp = _attempt_create()

    if resp.status_code == 417 and resp.json().get("exc_type") == "InvalidDates":
        # Auto-extend project end date to end of next month
        new_end = _next_month_end(date.today())
        ext_resp = session.request(
            "PUT",
            f"{base}/api/resource/Project/{config['project']}",
            json={"expected_end_date": new_end},
        )
        ext_resp.raise_for_status()
        notes.append(f"Note: project end date extended to {new_end}")

        # Retry once
        resp = _attempt_create()

    if not resp.ok:
        print(f"ERROR: Failed to create task: {resp.text[:300]}", file=sys.stderr)
        sys.exit(1)

    task_name = resp.json()["data"]["name"]
    return task_name, notes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--action", choices=["get-tasks", "create-task", "extend-project"], required=True)
    parser.add_argument("--project")
    parser.add_argument("--task-file")
    parser.add_argument("--date")
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.exists():
        print(f"ERROR: Config file not found: {args.config}", file=sys.stderr)
        sys.exit(1)
    try:
        config = json.loads(config_path.read_text())
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON in config: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        if args.action == "get-tasks":
            if not args.project:
                print("ERROR: --project required for get-tasks", file=sys.stderr)
                sys.exit(1)
            tasks = get_tasks(config, args.project)
            print(json.dumps(tasks))

        elif args.action == "create-task":
            if not args.task_file:
                print("ERROR: --task-file required for create-task", file=sys.stderr)
                sys.exit(1)
            try:
                task_input = json.loads(Path(args.task_file).read_text())
            except (OSError, json.JSONDecodeError) as e:
                print(f"ERROR: Could not read task file: {e}", file=sys.stderr)
                sys.exit(1)
            task_name, notes = create_task(config, task_input)
            for note in notes:
                print(note)
            print(json.dumps({"name": task_name}))

        elif args.action == "extend-project":
            if not args.project or not args.date:
                print("ERROR: --project and --date required for extend-project", file=sys.stderr)
                sys.exit(1)
            result = extend_project_end_date(config, args.project, args.date)
            print(json.dumps(result))

    except requests.HTTPError as e:
        print(f"ERROR: HTTP {e.response.status_code}: {e.response.text[:200]}", file=sys.stderr)
        sys.exit(1)
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
        print("ERROR: Could not connect to ERPNext.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the tests**

```bash
cd /home/neox/Work/erpnext-timesheet && python -m pytest tests/test_task_manager.py -v
```

Expected: all 8 tests pass.

- [ ] **Step 5: Run the full test suite to check for regressions**

```bash
cd /home/neox/Work/erpnext-timesheet && python -m pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
cd /home/neox/Work/erpnext-timesheet && git add scripts/task_manager.py tests/test_task_manager.py && git commit -m "feat: add task_manager.py with get_tasks, create_task, extend_project_end_date"
```

---

## Task 2: `setup.py` — add `full_name` to discover()

**Files:**
- Modify: `scripts/setup.py:18-74`
- Modify: `tests/test_setup.py:24-45`

---

- [ ] **Step 1: Update `test_discover_returns_expected_shape` and add two new tests**

In `tests/test_setup.py`, replace only `test_discover_returns_expected_shape` (keep `test_discover_raises_on_login_failure` and `test_discover_raises_on_no_employee` unchanged) and append the two new tests at the end of the discover section:

```python
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
```

- [ ] **Step 2: Run the tests to confirm the new tests fail**

```bash
cd /home/neox/Work/erpnext-timesheet && python -m pytest tests/test_setup.py -v
```

Expected: `test_discover_returns_expected_shape` and the two new tests fail (discover() doesn't return `full_name` yet).

- [ ] **Step 3: Update `discover()` in `scripts/setup.py`**

After the activity types block (line ~62), before building the `result` dict, add:

```python
    # Fetch full_name for identity confirmation
    encoded_username = quote(username, safe="")
    try:
        resp = session.get(
            f"{base}/api/resource/User/{encoded_username}",
            params={"fields": json.dumps(["full_name"])},
        )
        resp.raise_for_status()
        full_name = resp.json().get("data", {}).get("full_name") or username
    except requests.RequestException:
        full_name = username
```

Then add `"full_name": full_name` to the `result` dict.

The full updated `discover()` function body (replace lines 18–74 in setup.py):

```python
def discover(url: str, username: str, password: str) -> dict:
    """
    Login to ERPNext and discover employee, company, projects, activity types, and full name.
    Returns dict with keys: employee, company, projects, activity_types, full_name.
    Raises requests.HTTPError on login failure.
    Raises ValueError if no employee record found for the user.
    """
    base = url.rstrip("/")
    session = requests.Session()

    # Login
    resp = session.post(f"{base}/api/method/login", data={"usr": username, "pwd": password})
    resp.raise_for_status()

    # Discover employee
    resp = session.get(
        f"{base}/api/resource/Employee",
        params={
            "filters": json.dumps([["user_id", "=", username]]),
            "fields": json.dumps(["name", "company"]),
            "limit": 1,
        },
    )
    resp.raise_for_status()
    employees = resp.json().get("data", [])
    if not employees:
        raise ValueError(f"No employee record found for {username}. Ask your ERPNext admin to link your user to an Employee.")
    employee = employees[0]["name"]
    company = employees[0]["company"]

    # Discover projects
    resp = session.get(
        f"{base}/api/resource/Project",
        params={"fields": json.dumps(["name"]), "limit": 50},
    )
    resp.raise_for_status()
    projects = [p["name"] for p in resp.json().get("data", [])]

    # Discover activity types
    resp = session.get(
        f"{base}/api/resource/{quote('Activity Type')}",
        params={"fields": json.dumps(["name"]), "limit": 50},
    )
    resp.raise_for_status()
    activity_types = [a["name"] for a in resp.json().get("data", [])]

    # Fetch user's full name for identity confirmation
    encoded_username = quote(username, safe="")
    try:
        resp = session.get(
            f"{base}/api/resource/User/{encoded_username}",
            params={"fields": json.dumps(["full_name"])},
        )
        resp.raise_for_status()
        full_name = resp.json().get("data", {}).get("full_name") or username
    except requests.RequestException:
        full_name = username

    result = {
        "employee": employee,
        "company": company,
        "projects": projects,
        "activity_types": activity_types,
        "full_name": full_name,
    }
    if len(projects) == 50:
        result["projects_truncated"] = True
    if len(activity_types) == 50:
        result["activity_types_truncated"] = True
    return result
```

- [ ] **Step 4: Run the setup tests**

```bash
cd /home/neox/Work/erpnext-timesheet && python -m pytest tests/test_setup.py -v
```

Expected: all 8 tests pass (1 updated shape test + 2 new fallback tests + 2 unchanged discover tests + 3 write_config tests).

- [ ] **Step 5: Run the full suite**

```bash
cd /home/neox/Work/erpnext-timesheet && python -m pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
cd /home/neox/Work/erpnext-timesheet && git add scripts/setup.py tests/test_setup.py && git commit -m "feat: discover() returns full_name for identity confirmation in setup wizard"
```

---

## Task 3: `erpnext_client.py` — pass-through `task` field

**Files:**
- Modify: `scripts/erpnext_client.py:83-90`
- Modify: `tests/test_erpnext_client.py`

---

- [ ] **Step 1: Add the three new test cases to `tests/test_erpnext_client.py`**

Append to the end of the file:

```python
def test_build_timesheet_doc_includes_task_when_present():
    """task field is included in time log row when entry has a non-empty task key."""
    entries = [{"description": "Task A", "hours": 4.0, "task": "TASK-2026-01052"}]
    doc = build_timesheet_doc(BASE_CONFIG, entries)
    assert doc["time_logs"][0]["task"] == "TASK-2026-01052"


def test_build_timesheet_doc_omits_task_when_absent():
    """task field is absent in time log row when entry has no task key."""
    entries = [{"description": "Task A", "hours": 4.0}]
    doc = build_timesheet_doc(BASE_CONFIG, entries)
    assert "task" not in doc["time_logs"][0]


def test_build_timesheet_doc_omits_task_when_empty_string():
    """task field is omitted when entry has task key set to empty string."""
    entries = [{"description": "Task A", "hours": 4.0, "task": ""}]
    doc = build_timesheet_doc(BASE_CONFIG, entries)
    assert "task" not in doc["time_logs"][0]
```

- [ ] **Step 2: Run the tests to confirm they fail**

```bash
cd /home/neox/Work/erpnext-timesheet && python -m pytest tests/test_erpnext_client.py::test_build_timesheet_doc_includes_task_when_present tests/test_erpnext_client.py::test_build_timesheet_doc_omits_task_when_absent tests/test_erpnext_client.py::test_build_timesheet_doc_omits_task_when_empty_string -v
```

Expected: all 3 fail — task key never appears or always absent.

- [ ] **Step 3: Update `build_timesheet_doc()` in `scripts/erpnext_client.py`**

Inside the `time_logs.append({...})` block, after the existing fields, add the task field conditionally. Replace the `time_logs.append` call (lines ~83–90):

```python
        log = {
            "activity_type": entry.get("activity_type", config["default_activity"]),
            "description": entry["description"],
            "hours": hours,
            "from_time": from_time,
            "to_time": to_time,
            "project": config["project"],
        }
        if entry.get("task"):
            log["task"] = entry["task"]
        time_logs.append(log)
```

- [ ] **Step 4: Run the erpnext_client tests**

```bash
cd /home/neox/Work/erpnext-timesheet && python -m pytest tests/test_erpnext_client.py -v
```

Expected: all 14 tests pass (11 existing + 3 new).

- [ ] **Step 5: Run the full suite**

```bash
cd /home/neox/Work/erpnext-timesheet && python -m pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
cd /home/neox/Work/erpnext-timesheet && git add scripts/erpnext_client.py tests/test_erpnext_client.py && git commit -m "feat: build_timesheet_doc passes through optional task field per entry"
```

---

## Task 4: `timesheet.md` — update skill (Steps 0, 5, 6)

**Files:**
- Modify: `skills/timesheet/timesheet.md`

No tests — the skill is a prompt. Verify by reading the updated file for correctness.

---

- [ ] **Step 1: Replace the entire `timesheet.md` with the updated version**

Write `skills/timesheet/timesheet.md` with the following content (complete file — replaces all existing content):

````markdown
# ERPNext Timesheet

Automate daily ERPNext timesheet filling from your Claude conversation history.

---

When this skill is invoked, follow these steps exactly. Do not skip steps.

## Step 0: First-Time Setup

Check if `~/.claude/timesheet.json` exists:
```bash
test -f ~/.claude/timesheet.json && echo "EXISTS" || echo "MISSING"
```

If `MISSING`, run the interactive setup wizard:

### Setup Wizard

Tell the user:
```
Welcome! Let's connect to your ERPNext instance.
This will create ~/.claude/timesheet.json with your credentials and preferences.
Note: credentials are stored in plaintext — ensure your home directory is appropriately secured.
```

Ask the following questions one at a time:

1. **ERPNext URL** — e.g. `https://yourcompany.erpnext.com`
2. **Username** — your ERPNext login email
3. **Password**

Then test login and discover configuration:
```bash
python3 "$CLAUDE_PLUGIN_ROOT/scripts/setup.py" \
  --action discover \
  --url "<URL>" \
  --username "<USERNAME>" \
  --password "<PASSWORD>"
```

If the command fails, show the error and ask the user to correct their credentials. Re-ask steps 1–3.

If it succeeds, the output contains `employee`, `company`, `full_name`, `projects` (list), `activity_types` (list).

Show the identity confirmation block and ask:
```
Logged in as: <full_name>
Employee:     <employee>
Company:      <company>

Is this the right account? [y/n]
```

If `n`, re-ask steps 1–3 and re-run discover.

Then present each setting with the discovered or default value in brackets. The user presses Enter to accept, or types a new value to override:

```
Default project [<first project from discovered list>]:
Default activity type [<first activity type from discovered list>]:
Work hours per day [8]:
Workday start time [09:00]:
Timezone [<system timezone — run: timedatectl show --property=Timezone --value>]:
```

If the output shows `projects_truncated` or `activity_types_truncated`, note to the user that the list may be incomplete and they can type a name manually.

Before saving, show a summary and ask for confirmation:
```
About to save:
  URL:           <url>
  User:          <username>
  Employee:      <employee>
  Project:       <project>
  Activity type: <default_activity>
  Work hours:    <work_hours>
  Start time:    <start_time>
  Timezone:      <timezone>

Save to ~/.claude/timesheet.json? [y/n]
```

If `n`, restart from the beginning (re-ask URL, username, password).

If `y`, build the config JSON and write it:

Substitute `CONFIG_PLACEHOLDER` with the Python dict literal for the assembled config. This avoids passing credentials as shell arguments.

```bash
CONFIG_TMPFILE=$(mktemp /tmp/timesheet-setup-XXXXXX.json)
python3 -c "import json, sys; json.dump(CONFIG_PLACEHOLDER, open(sys.argv[1], 'w'))" "$CONFIG_TMPFILE"
python3 "$CLAUDE_PLUGIN_ROOT/scripts/setup.py" \
  --action write-config \
  --config-file "$CONFIG_TMPFILE" \
  --config-out ~/.claude/timesheet.json
rm -f "$CONFIG_TMPFILE"
```

Where `CONFIG_PLACEHOLDER` is the Python dict literal for:
```json
{
  "url": "<URL>",
  "username": "<USERNAME>",
  "password": "<PASSWORD>",
  "employee": "<discovered employee>",
  "company": "<discovered company>",
  "project": "<chosen project>",
  "default_activity": "<chosen activity type>",
  "work_hours": <work_hours>,
  "start_time": "<start_time>",
  "timezone": "<timezone>"
}
```

Tell the user: `Setup complete! Config saved to ~/.claude/timesheet.json`

Then continue to Step 1 (config validation) to confirm everything is in order.

If `EXISTS`, skip to Step 1.

## Step 1: Validate Config

Run:
```bash
python3 "$CLAUDE_PLUGIN_ROOT/scripts/parse_logs.py" --config ~/.claude/timesheet.json --validate-only
```

If the command exits non-zero or output is not `OK`, print the error and stop. Do not proceed.

## Step 2: Read Today's Conversations

Tell the user: `Reading today's Claude conversations...`

Run:
```bash
python3 "$CLAUDE_PLUGIN_ROOT/scripts/parse_logs.py" --config ~/.claude/timesheet.json
```

This returns a JSON array of messages `[{role, text, cwd, timestamp}]`. Store this as your context.

Parse `work_hours` from `~/.claude/timesheet.json` for use in Step 3 and Step 5.

## Step 3: Synthesize Task Entries

Tell the user: `Summarizing work done...`

From the conversation messages, identify distinct work themes. Create task entries where:
- **description**: short professional summary of the work, max 80 characters, no filler ("worked on", "helped with")
- **hours**: `work_hours / number_of_tasks`, rounded to 1 decimal. Last task absorbs rounding remainder so total equals work_hours exactly.
- **activity_type**: read `default_activity` from `~/.claude/timesheet.json`
- **task**: not set at synthesis time — assigned in Step 5 via `[t]`

Rules:
- Group closely related messages into one task (e.g. "fix bug" + "write test for fix" = one task)
- Ignore meta-conversation (greetings, "thanks", off-topic chat)
- Focus on deliverables: what was built, fixed, reviewed, or designed
- Minimum 1 task, maximum 8 tasks

If no messages were found, tell the user and skip to Step 5 with an empty list.

## Step 4: Check for Duplicate

Run:
```bash
python3 "$CLAUDE_PLUGIN_ROOT/scripts/erpnext_client.py" --config ~/.claude/timesheet.json --action check-duplicate
```

If the output contains `"exists": true`, ask:
`Warning: A timesheet already exists for today. Continue anyway? [y/n]`
If user answers `n`, stop.

## Step 5: Present Draft TUI

Read today's date. Read `project` from `~/.claude/timesheet.json`. Display:

```
Draft timesheet for YYYY-MM-DD (Xh total):
──────────────────────────────────────────
1. [Xh] Description of task one          [no task]
2. [Xh] Description of task two          [TASK-2026-01052]
...
──────────────────────────────────────────

[a] Approve and submit
[e] Edit an entry
[d] Delete an entry
[+] Add an entry (for work done outside Claude)
[h] Change hours for today
[t] Assign task to an entry
[q] Quit without submitting

>
```

Each entry shows its assigned task in brackets at the right: `[no task]` if none, or the task ID if assigned.

Handle the user's response:

### [a] Approve

If the entry list is empty, say: `No entries to submit. Use [+] to add entries first.` Re-display menu.

Otherwise, perform these checks in order:

1. **Task warning** — if any entry has no task assigned, warn:
   `Warning: X entries have no task assigned. Your ERPNext instance may require a task on each row. Continue? [y/n]`
   If `n`, re-display TUI.

2. **Hours mismatch warning** — if total hours ≠ work_hours:
   `Warning: total hours = Xh (expected Yh). Submit anyway? [y/n]`
   If `n`, re-display TUI. If `y` (or no mismatch), proceed to Step 6.

### [e] Edit

Ask: `Which entry number?`
For the chosen entry, prompt each field with its current value in brackets (press Enter to keep):
```
  Description [current value]:
  Hours [current value]:
  Activity type [current value]:
  Task [current task ID or blank to clear]:
```
After edit, check if total hours still equals work_hours. If not, show:
`Warning: total hours = Xh (expected Yh).`
This is informational only. Re-display TUI.

### [d] Delete

Ask: `Which entry number?`
Remove that entry. Re-display TUI.

### [+] Add entry

Prompt freehand (for work done outside Claude — meetings, calls, etc.):
```
  Description:
  Hours:
  Activity type [default_activity]:
```
Add to list with no task assigned. Use `[t]` to assign a task to it afterwards. Re-display TUI.

### [h] Change hours for today

Prompt: `New total hours [<current total>]:`

Parse the input as a float, round to 1 decimal. Re-distribute hours evenly across all current entries in-place:
- `per_entry = round(total / count, 1)`
- Last entry = `round(total - sum(all other entries), 1)`

Show: `Note: total is Xh (configured default is Yh).` if different from config work_hours — informational only.

Re-display TUI.

### [t] Assign task to an entry

Ask: `Which entry number?`

Fetch tasks from the configured project:
```bash
python3 "$CLAUDE_PLUGIN_ROOT/scripts/task_manager.py" \
  --config ~/.claude/timesheet.json \
  --action get-tasks \
  --project "<project from config>"
```

Display the list:
```
Entry N: <description>

  Existing tasks in <project>:
  1. <subject> (<name>, <status>)
  2. ...
  [n] Create new task
  [s] Skip (no task)
  >
```

**Select a number** — assign that task to the entry. Re-display TUI.

**`[s]` Skip** — entry remains `[no task]`. Re-display TUI.

**`[n]` Create new task:**

Show pre-filled subject and description. User presses Enter to accept or types a new value:
```
  Subject [<entry description, max 140 chars>]:
  Description [<full entry description>]:
```

Write a temp file and run create-task:
```bash
TASK_FILE=$(mktemp /tmp/timesheet-task-XXXXXX.json)
python3 -c "import json, sys; json.dump(TASK_PLACEHOLDER, open(sys.argv[1], 'w'))" "$TASK_FILE"
python3 "$CLAUDE_PLUGIN_ROOT/scripts/task_manager.py" \
  --config ~/.claude/timesheet.json \
  --action create-task \
  --task-file "$TASK_FILE"
rm -f "$TASK_FILE"
```

Where `TASK_PLACEHOLDER` is:
```json
{
  "subject": "<confirmed subject>",
  "description": "<confirmed description>",
  "project": "<project from config>",
  "hours": <entry's current hours>,
  "date": "<today YYYY-MM-DD>"
}
```

The command outputs zero or more `Note:` lines followed by a JSON line `{"name": "TASK-..."}` on the last line. Print any `Note:` lines to the user. Parse the last line to get the task name. Assign it to the entry. Re-display TUI.

### [q] Quit

Say: `Timesheet not submitted.` Stop.

## Step 6: Submit

Tell the user: `Submitting timesheet...`

Write the approved entries to a temp file and submit. Each entry must include `description`, `hours`, `activity_type`. Entries with a task assigned also include `task`.

Substitute `ENTRIES_PLACEHOLDER` with the Python literal for the approved entries list:
```json
[
  {"description": "...", "hours": 4.0, "activity_type": "Development", "task": "TASK-2026-01052"},
  {"description": "...", "hours": 4.0, "activity_type": "Development"}
]
```

```bash
ENTRIES_FILE=$(mktemp /tmp/timesheet-entries-XXXXXX.json)
python3 -c "import json, sys; json.dump(ENTRIES_PLACEHOLDER, open(sys.argv[1], 'w'))" "$ENTRIES_FILE"
python3 "$CLAUDE_PLUGIN_ROOT/scripts/erpnext_client.py" \
  --config ~/.claude/timesheet.json \
  --action submit \
  --entries-file "$ENTRIES_FILE"
rm -f "$ENTRIES_FILE"
```

If the command succeeds (exit 0), say:
`Timesheet submitted. Reference: <name from output>`

If it fails, show the full error output and ask: `Retry? [y/n]`
If `y`, re-run the submit command (maximum 3 total attempts). After 3 failed attempts, stop and tell the user to check their ERPNext connection and try again later. If `n`, stop.
````

- [ ] **Step 2: Verify the file reads correctly**

```bash
wc -l /home/neox/Work/erpnext-timesheet/skills/timesheet/timesheet.md
```

Expected: ~200+ lines. Confirm the file starts with `# ERPNext Timesheet` and ends at `## Step 6`.

- [ ] **Step 3: Run the full test suite one final time**

```bash
cd /home/neox/Work/erpnext-timesheet && python -m pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
cd /home/neox/Work/erpnext-timesheet && git add skills/timesheet/timesheet.md && git commit -m "feat: update skill with interactive setup, task TUI, hours override"
```
