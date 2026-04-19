# Task Tree — `listTasks` returns hierarchy

**Feature:** Task Tree (Feature 1 of 3)  
**Scope:** Read-only change to `listTasks` — no changes to `createTask`, `submitTimesheet`, or any other tool.

---

## Problem

`listTasks` currently returns a flat list of all non-cancelled tasks, including Completed ones. Two issues:

1. **No hierarchy** — ERPNext tasks have `is_group` and `parent_task` fields that represent a tree structure. The skill can't map work items to task groups or reason about where new tasks belong.
2. **Too much noise** — Completed tasks are fetched on every invocation but never used. PROJ-0050 has 54 tasks, most Completed.

---

## Data Layer — `ERPNextClient.list_tasks()`

**Filter change:** exclude both Completed and Cancelled.

```
["project", "=", project],
["status", "not in", ["Completed", "Cancelled"]]
```

**Fields added:** `is_group`, `parent_task` (in addition to existing `name`, `subject`, `status`, `exp_end_date`).

**Pagination:** replace `limit: 50` with a paginated loop — fetch pages of 100 until a page comes back with fewer than 100 results. Returns the full flat list to the caller.

---

## Tree Builder — `_build_tree(tasks)`

New private helper in `mcp_server.py`. Takes the flat list from `list_tasks()` and returns a nested tree.

Algorithm:
1. Index all tasks by `name`
2. Walk the list — if a task has `parent_task`, append it to that parent's `children`
3. Roots are tasks where `parent_task` is null or not present in the fetched set

Output shape per node:
```json
{
  "name": "TASK-xxx",
  "subject": "...",
  "is_group": true,
  "status": "Open",
  "exp_end_date": "2026-05-01",
  "children": [ ... ]
}
```

`children` is always present (empty list for leaf nodes). Groups and orphan leaf tasks both appear at the root level if they have no parent.

---

## MCP Tool — `listTasks`

Signature unchanged: `listTasks(project: str) -> list`

Implementation change: call `list_tasks()`, pass result through `_build_tree()`, return the nested structure.

---

## SKILL.md Changes

Three places reference `TASKS`:

**Step 2 — auto-match**  
Add a note: `TASKS` is a tree. Match against all nodes (groups and leaves) by walking recursively. Groups are valid match targets — a work item can be assigned to a group task.

**Step 2 — overdue detection**  
Simplify: since Completed tasks are excluded at fetch time, the check is now just `exp_end_date < TARGET_DATE` (no status exclusion needed). Walk the tree recursively to collect matching nodes.

**Step 3 — edit handling ("Assign by name or topic")**  
Lookup is now recursive — search all nodes in the tree by name or subject keyword.

---

## What Does Not Change

- `createTask` — no `parent_task` parameter yet (Feature 2)
- `checkExisting`, `submitTimesheet`, `readHistory`, `isReady`, `updateSettings` — unchanged
- The skill flow (Steps 0–4) — unchanged except the three SKILL.md notes above
