# Multi-Project Submission Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow a single day's timesheet to span multiple ERPNext projects, with project inferred per entry from conversation context and shown in the Step 3 draft.

**Architecture:** New `listProjects` MCP tool + `ERPNextClient.list_projects()` method; one-line change to `build_timesheet_doc` to use per-entry project; SKILL.md Step 2 gains project inference + per-project `listTasks` calls; Step 3 shows project prefix when multiple projects are detected.

**Tech Stack:** Python 3.11+, pytest, ERPNext REST API (`/api/resource/Project`)

---

## File Map

| File | Change |
|---|---|
| `skills/timesheet/mcp_server.py` | Add `ERPNextClient.list_projects()`; add `listProjects` MCP tool; patch `build_timesheet_doc` |
| `skills/timesheet/SKILL.md` | Update Steps 2 and 3 |
| `tests/test_erpnext_client.py` | Add tests for `list_projects()` |
| `tests/test_mcp_server.py` | Add tests for `listProjects` MCP tool |

---

### Task 1: `ERPNextClient.list_projects()` — fetch active projects

**Files:**
- Modify: `skills/timesheet/mcp_server.py` — add `list_projects()` after `list_tasks()`
- Test: `tests/test_erpnext_client.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_erpnext_client.py`:

```python
# --- list_projects ---

def test_list_projects_returns_label():
    client = make_client()
    client._authenticated = True
    page = {"data": [
        {"name": "PROJ-0001", "project_name": "My Project"},
        {"name": "PROJ-0050", "project_name": "PROJ-0050"},
    ]}
    with patch.object(client, "_request", side_effect=[page]) as mock_req:
        result = client.list_projects()
    assert result == [
        {"id": "PROJ-0001", "label": "PROJ-0001 — My Project"},
        {"id": "PROJ-0050", "label": "PROJ-0050"},
    ]


def test_list_projects_filter_excludes_completed_cancelled():
    client = make_client()
    client._authenticated = True
    with patch.object(client, "_request", return_value={"data": []}) as mock_req:
        client.list_projects()
    params = mock_req.call_args[1]["params"]
    filters = json.loads(params["filters"])
    assert ["status", "not in", ["Completed", "Cancelled"]] in filters


def test_list_projects_paginates():
    client = make_client()
    client._authenticated = True
    page1 = {"data": [{"name": f"PROJ-{i:04d}", "project_name": f"Project {i}"}
                       for i in range(100)]}
    page2 = {"data": [{"name": "PROJ-0100", "project_name": "Last"}]}
    with patch.object(client, "_request", side_effect=[page1, page2]):
        result = client.list_projects()
    assert len(result) == 101
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd /home/neox/Work/erpnext-timesheet/skills/timesheet
python -m pytest ../../tests/test_erpnext_client.py::test_list_projects_returns_label ../../tests/test_erpnext_client.py::test_list_projects_filter_excludes_completed_cancelled ../../tests/test_erpnext_client.py::test_list_projects_paginates -v
```

Expected: 3 FAILs — `AttributeError: 'ERPNextClient' object has no attribute 'list_projects'`.

- [ ] **Step 3: Add `list_projects()` to `ERPNextClient` in `mcp_server.py`**

Insert after the closing line of `list_tasks()` (after `return tasks`), before `extend_project`:

```python
def list_projects(self) -> list:
    projects = []
    page_size = 100
    start = 0
    while True:
        result = self._request(
            "GET",
            "/api/resource/Project",
            params={
                "filters": json.dumps([
                    ["status", "not in", ["Completed", "Cancelled"]],
                ]),
                "fields": json.dumps(["name", "project_name"]),
                "limit_page_length": page_size,
                "limit_start": start,
            },
        )
        page = result.get("data", [])
        for p in page:
            label = (
                f"{p['name']} — {p['project_name']}"
                if p.get("project_name") and p["project_name"] != p["name"]
                else p["name"]
            )
            projects.append({"id": p["name"], "label": label})
        if len(page) < page_size:
            break
        start += page_size
    return projects
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/neox/Work/erpnext-timesheet/skills/timesheet
python -m pytest ../../tests/test_erpnext_client.py::test_list_projects_returns_label ../../tests/test_erpnext_client.py::test_list_projects_filter_excludes_completed_cancelled ../../tests/test_erpnext_client.py::test_list_projects_paginates -v
```

Expected: 3 PASSes.

- [ ] **Step 5: Run full test suite**

```bash
cd /home/neox/Work/erpnext-timesheet/skills/timesheet
python -m pytest ../../tests/ -v
```

Expected: all existing tests still PASS.

- [ ] **Step 6: Commit**

```bash
git add skills/timesheet/mcp_server.py tests/test_erpnext_client.py
git commit -m "feat: add ERPNextClient.list_projects() with pagination and status filter"
```

---

### Task 2: `listProjects` MCP Tool

**Files:**
- Modify: `skills/timesheet/mcp_server.py` — add `listProjects` tool after `listTasks`
- Test: `tests/test_mcp_server.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_mcp_server.py`. First add `listProjects` to the import line at the top:

```python
from mcp_server import checkExisting, submitTimesheet, listTasks, createTask, listProjects
```

Then append the test:

```python
# --- listProjects ---

def test_listProjects_returns_project_list(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
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
    make_config_file(tmp_path)
    monkeypatch.setattr(mcp_server.ERPNextClient, "login", lambda self: None)
    monkeypatch.setattr(mcp_server.ERPNextClient, "list_projects",
                        lambda self: [])
    assert listProjects() == []
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd /home/neox/Work/erpnext-timesheet/skills/timesheet
python -m pytest ../../tests/test_mcp_server.py::test_listProjects_returns_project_list ../../tests/test_mcp_server.py::test_listProjects_empty -v
```

Expected: 2 FAILs — `ImportError: cannot import name 'listProjects'`.

- [ ] **Step 3: Add `listProjects` MCP tool to `mcp_server.py`**

Insert after the `listTasks` tool function, before `createTask`:

```python
@mcp.tool()
def listProjects() -> list:
    """Return all non-Completed/non-Cancelled projects as [{id, label}]."""
    config = _load_config()
    try:
        return _get_client(config).list_projects()
    except requests.HTTPError as e:
        if _is_auth_error(e):
            _clear_client()
            return [_AUTH_ERROR]
        raise
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/neox/Work/erpnext-timesheet/skills/timesheet
python -m pytest ../../tests/test_mcp_server.py::test_listProjects_returns_project_list ../../tests/test_mcp_server.py::test_listProjects_empty -v
```

Expected: 2 PASSes.

- [ ] **Step 5: Run full test suite**

```bash
cd /home/neox/Work/erpnext-timesheet/skills/timesheet
python -m pytest ../../tests/ -v
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add skills/timesheet/mcp_server.py tests/test_mcp_server.py
git commit -m "feat: add listProjects MCP tool"
```

---

### Task 3: `build_timesheet_doc` — Per-Entry Project

**Files:**
- Modify: `skills/timesheet/mcp_server.py` — one line in `build_timesheet_doc`
- Test: `tests/test_erpnext_client.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_erpnext_client.py`:

```python
# --- build_timesheet_doc (per-entry project) ---

def test_build_timesheet_doc_per_entry_project_override():
    """Entry-level project overrides config project in the time log."""
    entries = [
        {"description": "Task A", "hours": 2.0, "project": "PROJ-0050"},
        {"description": "Task B", "hours": 2.0},
    ]
    doc = build_timesheet_doc(BASE_CONFIG, entries)
    assert doc["time_logs"][0]["project"] == "PROJ-0050"
    assert doc["time_logs"][1]["project"] == "PROJ-001"   # falls back to config
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd /home/neox/Work/erpnext-timesheet/skills/timesheet
python -m pytest ../../tests/test_erpnext_client.py::test_build_timesheet_doc_per_entry_project_override -v
```

Expected: FAIL — `assert 'PROJ-0050' == 'PROJ-001'` (both currently use `config["project"]`).

- [ ] **Step 3: Patch `build_timesheet_doc` in `mcp_server.py`**

Find this line inside `build_timesheet_doc` (in the `log` dict construction):

```python
            "project": config["project"],
```

Replace it with:

```python
            "project": entry.get("project", config["project"]),
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /home/neox/Work/erpnext-timesheet/skills/timesheet
python -m pytest ../../tests/test_erpnext_client.py::test_build_timesheet_doc_per_entry_project_override -v
```

Expected: PASS.

- [ ] **Step 5: Run full test suite**

```bash
cd /home/neox/Work/erpnext-timesheet/skills/timesheet
python -m pytest ../../tests/ -v
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add skills/timesheet/mcp_server.py tests/test_erpnext_client.py
git commit -m "feat: build_timesheet_doc uses per-entry project with config fallback"
```

---

### Task 4: SKILL.md — Multi-Project Steps 2 and 3

**Files:**
- Modify: `skills/timesheet/SKILL.md` — Steps 2 and 3

- [ ] **Step 1: Update Step 2 — project inference after entry synthesis**

In `SKILL.md` Step 2, find the line:

```
Call `listTasks` with `project=STATUS.project` silently. Store as `TASKS`.
```

Replace it with:

```markdown
Call `listProjects` silently. Store as `PROJECTS`.

For each entry, infer the ERPNext project from conversation context — topics discussed, system names, repositories or products mentioned, domain keywords. Match against `PROJECTS` by `label`/`id` similarity. Set `entry.project` for each entry. When uncertain, default to `STATUS.project`.

Collect the distinct set of projects across all entries. Call `listTasks(project)` once for each unique project. Store results as a map: `project_id → task tree`. (If all entries resolve to `STATUS.project`, this is one call — identical to the previous behaviour.)

Auto-match each entry against its own project's task tree using the existing recursive matching logic (Feature 1 + Feature 2 group placement).
```

- [ ] **Step 2: Update Step 4 — use `entry.project` in auto-create**

In `SKILL.md` Step 4, the Feature 2 auto-create instruction for new group tasks uses `project=STATUS.project`. With multi-project support, each entry now carries `entry.project`. Find this text in Step 4:

```
call `createTask` with `subject=proposed_group`, `description=proposed_group`, `project=STATUS.project`, `hours=0`, `date=TARGET_DATE`, `is_group=True`
```

Replace `project=STATUS.project` with `project=entry.project` in all three auto-create clauses (groups, children, root tasks).

- [ ] **Step 3: Update Step 3 — conditional project prefix in draft**

In `SKILL.md` Step 3, replace the draft template block with:

```markdown
**If all entries share one project** (single-project day), omit the project prefix — no visual noise:

```
TARGET_DATE — Xh total
─────────────────────────────────────────
1. [Xh] Description one          → TASK-XXXX
2. [Xh] Description two          → [GROUP-XXXX] / new task
─────────────────────────────────────────
Submit, or let me know what to change.
```

**If entries span multiple projects**, show project prefix before each task assignment:

```
TARGET_DATE — Xh total
─────────────────────────────────────────
1. [2h] Implement task tree builder    → PROJ-0001 / TASK-XXXX
2. [2h] Write pagination tests         → PROJ-0001 / [Dev Start] / new task
3. [2h] Review vendor proposal         → PROJ-0050 / no task
─────────────────────────────────────────
Submit, or let me know what to change.
```
```

Then add a project reassignment edit command to the existing edit list in Step 3:

```markdown
- Reassign project → `"move entry N to PROJ-XXXX"` → update `entry.project`, re-run auto-match against that project's task tree (call `listTasks` lazily if not already fetched), show draft
```

- [ ] **Step 4: Verify the file reads correctly**

```bash
cat skills/timesheet/SKILL.md
```

Check:
- Step 2 now has `listProjects` call before `listTasks`
- Step 2 shows per-project `listTasks` loop with project map
- Step 3 has both single-project and multi-project draft templates
- Step 3 edit list has the project reassignment command

- [ ] **Step 5: Bump version in SKILL.md and plugin.json**

In `skills/timesheet/SKILL.md` line 4, change the current version → `2.0.9`.

In `.claude-plugin/plugin.json` line 4, change the current version → `"2.0.9"`.

(If Feature 2 has already been applied, the current version in these files will be `2.0.8`. If applying both features together, bump from `2.0.7` to `2.0.9` in one go.)

- [ ] **Step 6: Commit**

```bash
git add skills/timesheet/SKILL.md .claude-plugin/plugin.json
git commit -m "feat: multi-project — listProjects, per-entry project inference, draft prefix + version 2.0.9"
```
