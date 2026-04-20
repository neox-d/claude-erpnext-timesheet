# Smart Group Mapping Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow new tasks auto-created by the skill to be placed under existing or new group tasks, with group placement shown in the Step 3 draft.

**Architecture:** Two code changes (ERPNextClient + MCP tool) and one SKILL.md prose update. The client gains `is_group` and `parent_task` support in `create_task()`; the MCP tool exposes those as optional parameters; SKILL.md gains group-placement logic in Steps 2, 3, and 4.

**Tech Stack:** Python 3.11+, pytest, ERPNext REST API (`/api/resource/Task`)

---

## File Map

| File | Change |
|---|---|
| `skills/timesheet/mcp_server.py` | Modify `ERPNextClient.create_task()` and `createTask` MCP tool |
| `skills/timesheet/SKILL.md` | Update Steps 2, 3, 4 |
| `tests/test_erpnext_client.py` | Add tests for `create_task` with `parent_task` and `is_group` |
| `tests/test_mcp_server.py` | Add tests for `createTask` MCP tool with new parameters |

---

### Task 1: `ERPNextClient.create_task()` — `parent_task` and `is_group`

**Files:**
- Modify: `skills/timesheet/mcp_server.py` — `ERPNextClient.create_task()` (lines 118–142)
- Test: `tests/test_erpnext_client.py`

- [ ] **Step 1: Write three failing tests**

Append to `tests/test_erpnext_client.py`:

```python
# --- create_task (parent_task / is_group) ---

def test_create_task_with_parent_task():
    client = make_client()
    client._authenticated = True
    with patch.object(client, "_request",
                      return_value={"data": {"name": "TASK-0001"}}) as mock_req:
        name, notes = client.create_task({
            "subject": "Child task",
            "description": "desc",
            "project": "PROJ-001",
            "hours": 2.0,
            "date": "2026-04-20",
            "parent_task": "TASK-GROUP-001",
        })
    doc = mock_req.call_args[1]["json"]
    assert doc["parent_task"] == "TASK-GROUP-001"
    assert name == "TASK-0001"
    assert notes == []


def test_create_task_is_group_true():
    client = make_client()
    client._authenticated = True
    with patch.object(client, "_request",
                      return_value={"data": {"name": "TASK-GRP-001"}}) as mock_req:
        name, notes = client.create_task({
            "subject": "My Group",
            "description": "group desc",
            "project": "PROJ-001",
            "hours": 0,
            "date": "2026-04-20",
            "is_group": True,
        })
    doc = mock_req.call_args[1]["json"]
    assert doc["is_group"] == 1
    assert "status" not in doc
    assert "expected_time" not in doc
    assert "exp_start_date" not in doc
    assert "exp_end_date" not in doc
    assert name == "TASK-GRP-001"
    assert notes == []


def test_create_task_leaf_omits_is_group_field():
    client = make_client()
    client._authenticated = True
    with patch.object(client, "_request",
                      return_value={"data": {"name": "TASK-0002"}}) as mock_req:
        client.create_task({
            "subject": "Leaf task",
            "description": "desc",
            "project": "PROJ-001",
            "hours": 2.0,
            "date": "2026-04-20",
        })
    doc = mock_req.call_args[1]["json"]
    assert "is_group" not in doc
    assert doc["status"] == "Completed"
    assert doc["expected_time"] == 2.0
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd /home/neox/Work/erpnext-timesheet/skills/timesheet
python -m pytest ../../tests/test_erpnext_client.py::test_create_task_with_parent_task ../../tests/test_erpnext_client.py::test_create_task_is_group_true ../../tests/test_erpnext_client.py::test_create_task_leaf_omits_is_group_field -v
```

Expected: 3 FAILs (KeyError or AssertionError — `parent_task` not in doc, `is_group` not in doc).

- [ ] **Step 3: Replace `create_task()` in `mcp_server.py`**

Replace the entire `create_task` method (currently lines 118–142) with:

```python
def create_task(self, task_input: dict) -> tuple[str, list[str]]:
    notes = []
    is_group = task_input.get("is_group", False)
    doc = {
        "subject": task_input["subject"],
        "description": task_input["description"],
        "project": task_input["project"],
    }
    if task_input.get("parent_task"):
        doc["parent_task"] = task_input["parent_task"]
    if is_group:
        doc["is_group"] = 1
    else:
        doc["expected_time"] = task_input["hours"]
        doc["exp_start_date"] = task_input["date"]
        doc["exp_end_date"] = task_input["date"]
        doc["custom_planned_completion_date"] = task_input["date"]
        doc["status"] = "Completed"
    try:
        result = self._request("POST", "/api/resource/Task", json=doc)
    except requests.HTTPError as e:
        if (e.response is not None
                and e.response.status_code == 417
                and e.response.json().get("exc_type") == "InvalidDates"):
            new_end = _next_month_end(date_type.today())
            self.extend_project(doc["project"], new_end)
            notes.append(f"Note: project end date extended to {new_end}")
            result = self._request("POST", "/api/resource/Task", json=doc)
        else:
            raise
    return result["data"]["name"], notes
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/neox/Work/erpnext-timesheet/skills/timesheet
python -m pytest ../../tests/test_erpnext_client.py::test_create_task_with_parent_task ../../tests/test_erpnext_client.py::test_create_task_is_group_true ../../tests/test_erpnext_client.py::test_create_task_leaf_omits_is_group_field -v
```

Expected: 3 PASSes.

- [ ] **Step 5: Run full test suite to check for regressions**

```bash
cd /home/neox/Work/erpnext-timesheet/skills/timesheet
python -m pytest ../../tests/ -v
```

Expected: all existing tests still PASS.

- [ ] **Step 6: Commit**

```bash
git add skills/timesheet/mcp_server.py tests/test_erpnext_client.py
git commit -m "feat: add parent_task and is_group support to ERPNextClient.create_task"
```

---

### Task 2: `createTask` MCP Tool — `parent_task` and `is_group` Parameters

**Files:**
- Modify: `skills/timesheet/mcp_server.py` — `createTask` tool function
- Test: `tests/test_mcp_server.py`

- [ ] **Step 1: Write two failing tests**

Append to `tests/test_mcp_server.py`:

```python
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
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd /home/neox/Work/erpnext-timesheet/skills/timesheet
python -m pytest ../../tests/test_mcp_server.py::test_createTask_passes_parent_task ../../tests/test_mcp_server.py::test_createTask_passes_is_group -v
```

Expected: 2 FAILs — `TypeError: createTask() got an unexpected keyword argument 'parent_task'`.

- [ ] **Step 3: Update `createTask` MCP tool in `mcp_server.py`**

Replace the existing `createTask` function:

```python
@mcp.tool()
def createTask(subject: str, description: str, project: str, hours: float, date: str,
               parent_task: str = None, is_group: bool = False) -> dict:
    """Create a task in ERPNext. Auto-extends project end date on InvalidDates errors."""
    config = _load_config()
    try:
        name, notes = _get_client(config).create_task({
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

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/neox/Work/erpnext-timesheet/skills/timesheet
python -m pytest ../../tests/test_mcp_server.py::test_createTask_passes_parent_task ../../tests/test_mcp_server.py::test_createTask_passes_is_group -v
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
git commit -m "feat: expose parent_task and is_group in createTask MCP tool"
```

---

### Task 3: SKILL.md — Group Placement in Steps 2, 3, 4

**Files:**
- Modify: `skills/timesheet/SKILL.md` — Steps 2, 3, 4

There are no automated tests for SKILL.md (it is prose read by an LLM). Each step below is a targeted edit.

- [ ] **Step 1: Update Step 2 — add group placement after auto-match**

In `SKILL.md`, find the end of the Step 2 auto-match block (after "Store synthesized entries as `ENTRIES`."). Insert the following block immediately before that line:

```markdown
**Group placement:** For each entry, determine where a new task will be placed if one must be created:

1. If `task` points to a group (`is_group=1`) and keyword overlap with that group is vague (the group was the closest available but not a clear match) → demote: clear `task`, set `parent_task` to that group's name.
2. For entries with no `task` → walk `TASKS` recursively to find the best-fit group by keyword overlap:
   - Clear group match → set `parent_task` to that group's name
   - No good group match → propose a new group subject → set `proposed_group`
3. Entries where no group is semantically appropriate → leave `parent_task` and `proposed_group` unset (root level).

Store `parent_task` and `proposed_group` on each entry alongside `task` in `ENTRIES`. At most one of `task`, `parent_task`, `proposed_group` is set per entry.
```

- [ ] **Step 2: Update Step 3 — draft format and new edit commands**

In `SKILL.md`, replace the draft template block in Step 3 with:

```markdown
```
TARGET_DATE — Xh total
─────────────────────────────────────────
1. [Xh] Description one          → TASK-XXXX
2. [Xh] Description two          → [GROUP-XXXX] / new task
3. [Xh] Description three        → [new "Backend"] / new task
4. [Xh] Description four         → new task
─────────────────────────────────────────
Submit, or let me know what to change.
```

Legend: `→ TASK-XXXX` = direct assign; `→ [GROUP] / new task` = child of existing group; `→ [new "Name"] / new task` = child of proposed new group; `→ new task` = root level.
```

Then, in the edit command list in Step 3, add these four commands after the existing list:

```markdown
- Move to existing group → `"put entry N under Group X"` → set `parent_task` to matched group name, clear `proposed_group`, show draft
- Propose new group → `"create group Z for entry N"` → set `proposed_group` to Z, clear `parent_task`, show draft
- Remove group placement → `"move entry N to root"` → clear both `parent_task` and `proposed_group`, show draft
- Rename proposed group → `"rename the new group to X"` → update `proposed_group` subject, show draft
```

- [ ] **Step 3: Update Step 4 — auto-create order**

In `SKILL.md`, replace the existing **Auto-create tasks for unassigned entries** block with:

```markdown
**Auto-create tasks for unassigned entries** in this order:

1. **New groups first** — for entries with `proposed_group` set: call `createTask` with `subject=proposed_group`, `description=proposed_group`, `project=STATUS.project`, `hours=0`, `date=TARGET_DATE`, `is_group=True`. Collect returned names.
2. **Child tasks** — for entries with `parent_task` set (either an existing group name or a name returned in step 1): call `createTask` with `parent_task` set, `is_group=False`.
3. **Root tasks** — for entries with neither `parent_task` nor `proposed_group` set: call `createTask` with no parent, `is_group=False`.
4. Assign all returned task names to their entries before calling `submitTimesheet`.

After all are created, show a brief list: `TASK-XXXX — subject` for each. Print any `notes`.
```

- [ ] **Step 4: Verify the file reads correctly**

```bash
cat skills/timesheet/SKILL.md
```

Read through Steps 2, 3, 4. Check:
- Step 2 has the group placement block immediately before "Store synthesized entries as `ENTRIES`."
- Step 3 draft shows all four `→` legend variants
- Step 3 edit list has the four new group commands
- Step 4 auto-create block has the numbered 1–4 order

- [ ] **Step 5: Bump version in SKILL.md and plugin.json**

In `skills/timesheet/SKILL.md` line 4, change `version: 2.0.7` → `version: 2.0.8`.

In `.claude-plugin/plugin.json` line 4, change `"version": "2.0.7"` → `"version": "2.0.8"`.

- [ ] **Step 6: Commit**

```bash
git add skills/timesheet/SKILL.md .claude-plugin/plugin.json
git commit -m "feat: smart group mapping — Steps 2/3/4 skill instructions + version 2.0.8"
```
