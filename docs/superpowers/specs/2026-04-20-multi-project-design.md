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

## Step 2 — Task Fetch (SKILL.md)

Unchanged from pre-Feature-3 behaviour: call `listTasks(STATUS.project)` once. All entries begin without an `entry.project` assignment; project reassignment happens lazily in Step 3 based on user input.

---

## Step 3 — Draft Display and Lazy Project Assignment (SKILL.md)

**Unmatched entries — project hint:** For entries showing `→ new task`, the AI uses conversation context to judge whether the work likely belongs to a different project. If yes, the draft flags the entry: `→ new task (different project?)`.

**User-driven lazy assignment:** If the user confirms or requests a different project for any entry:
1. Call `listProjects` once (reuse if already fetched) → present the list
2. User picks a project
3. Call `listTasks` for that project (once, reuse on repeat)
4. Re-run auto-match for affected entries, set `entry.project`
5. Show updated draft

**Single-project day:** omit project prefix — no visual noise.  
**Multi-project day:** show project prefix before each task assignment (same format as previous design).

**Edit trigger:** `"entry N is from a different project"` or `"move entry N to another project"`.

---

## Step 4 — No Changes

`submitTimesheet` is called once with all entries. `build_timesheet_doc` handles per-log project assignment via `entry.get("project", config["project"])`. `createTask` already accepts a `project` parameter — the correct per-entry project is passed when auto-creating tasks.

`checkExisting` is project-agnostic (checks by employee + date), so no change.

---

## What Does Not Change

- `submitTimesheet`, `checkExisting`, `createTask`, `isReady`, `readHistory`, `updateSettings`, `listTasks` — unchanged
- Single-project behavior — fully backward compatible; if all entries resolve to `STATUS.project`, the flow is identical to today
- `STATUS.project` remains the default fallback throughout
