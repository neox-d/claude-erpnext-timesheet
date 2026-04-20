# Multi-Project Submission

**Feature:** Multi-Project Submission (Feature 3 of 3 — Issue #2)  
**Scope:** New `listProjects` MCP tool + `build_timesheet_doc` one-line change + SKILL.md Steps 2–3. No changes to `submitTimesheet`, `checkExisting`, `createTask`, `isReady`, `readHistory`, or `updateSettings`.

---

## Problem

The skill currently assigns all time log entries to `STATUS.project` (the single configured default). In practice, a day's work often spans multiple ERPNext projects. The skill should infer which project each entry belongs to from conversation context, confirm with the user in Step 3, and submit a single timesheet with per-log project assignments.

---

## New MCP Tool — `listProjects`

Fetches all non-Completed/non-Cancelled projects from ERPNext.

**API call:**
```
GET /api/resource/Project
filters: [["status", "not in", ["Completed", "Cancelled"]]]
fields: ["name", "project_name"]
```

**Pagination:** same loop as `list_tasks` — pages of 100 until a short page.

**Return shape:**
```json
[
  {"id": "PROJ-0001", "label": "PROJ-0001 — My Project Name"},
  {"id": "PROJ-0050", "label": "PROJ-0050 — Another Project"}
]
```

When `project_name` is absent or equal to `name`, `label` is just `name`.

Auth error handling identical to `listTasks`.

**ERPNextClient method:** `list_projects() -> list[dict]`

---

## `build_timesheet_doc` Change

Per time log, use the entry's own project if set, falling back to `config["project"]`:

```
"project": entry.get("project", config["project"])
```

No other change to this function.

---

## Step 2 — Project Inference (SKILL.md)

After synthesizing entries from `MESSAGES`:

1. Call `listProjects` silently → store as `PROJECTS`.
2. For each entry, infer the ERPNext project from conversation content — topics discussed, system names, repositories mentioned, domain context. Match against `PROJECTS` by `label`/`id` similarity.
3. Assign `entry.project` for each entry. When uncertain, default to `STATUS.project`.
4. Collect the distinct set of projects across all entries. Call `listTasks(project)` for each — one call per unique project, not one per entry. Store as a map: `project_id → task tree`.
5. Auto-match each entry against its own project's task tree (Feature 1 + Feature 2 matching logic).

---

## Step 3 — Draft Display (SKILL.md)

**Single-project day:** omit project prefix entirely — no visual noise.

**Multi-project day:** show project prefix before the task assignment:

```
TARGET_DATE — Xh total
─────────────────────────────────────────
1. [2h] Implement task tree builder    → PROJ-0001 / TASK-2026-0312
2. [2h] Write pagination tests         → PROJ-0001 / [Dev Start] / new task
3. [2h] Review vendor proposal         → PROJ-0050 / no task
─────────────────────────────────────────
```

**Edit command:** `"move entry N to PROJ-XXXX"` → update `entry.project`, re-run auto-match against that project's task tree (already in context if previously fetched; call `listTasks` lazily if not), show draft.

---

## Step 4 — No Changes

`submitTimesheet` is called once with all entries. `build_timesheet_doc` handles per-log project assignment via `entry.get("project", config["project"])`. `createTask` already accepts a `project` parameter — the correct per-entry project is passed when auto-creating tasks.

`checkExisting` is project-agnostic (checks by employee + date), so no change.

---

## What Does Not Change

- `submitTimesheet`, `checkExisting`, `createTask`, `isReady`, `readHistory`, `updateSettings`, `listTasks` — unchanged
- Single-project behavior — fully backward compatible; if all entries resolve to `STATUS.project`, the flow is identical to today
- `STATUS.project` remains the default fallback throughout
