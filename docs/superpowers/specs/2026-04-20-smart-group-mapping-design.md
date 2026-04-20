# Smart Group Mapping

**Feature:** Smart Group Mapping (Feature 2 of 3 — Issue #2)  
**Scope:** `createTask` MCP tool + `ERPNextClient.create_task()` + SKILL.md Steps 2–4. No changes to `submitTimesheet`, `checkExisting`, `readHistory`, `isReady`, or `updateSettings`.

---

## Problem

When the skill auto-creates tasks for unassigned entries (Step 4), they are always created at the project root level. ERPNext supports task hierarchy via `is_group` and `parent_task`, and Feature 1 now returns this tree from `listTasks`. The skill should use that tree to place new tasks under the right group — and propose creating a new group when none fits.

---

## Entry Data Model

Each `ENTRY` carries at most one of three mutually exclusive placement fields:

| Field | Type | Meaning |
|---|---|---|
| `task` | str | Direct assignment to an existing task (strong keyword match, leaf or group) |
| `parent_task` | str | Name of an existing group — a new child task will be created under it |
| `proposed_group` | str | Subject for a new group task to create — child task goes under it |

Priority at auto-create time: `task` (no creation needed) → `parent_task` (create child under existing group) → `proposed_group` (create group, then child) → root level (create task with no parent).

---

## Step 2 — Auto-Match Enhancement (SKILL.md)

After the existing auto-match pass that assigns `task`:

1. **Demote weak group matches:** for entries where `task` points to a group (`is_group=1`) and keyword overlap is vague (the group was just the closest available option), clear `task` and set `parent_task` to that group's name instead.
2. **Find group parent for unassigned entries:** walk `TASKS` recursively; find the best-fit group by keyword overlap.
   - Good group match → set `parent_task`
   - No good group match → AI proposes a new group subject → set `proposed_group`
3. Entries where no group makes semantic sense → leave all three fields unset (root level).

---

## Step 3 — Draft Display (SKILL.md)

```
TARGET_DATE — Xh total
─────────────────────────────────────────
1. [Xh] Implement task tree builder    → TASK-2026-0312
2. [Xh] Write pagination tests         → [Development Start] / new task
3. [Xh] Design multi-project spec      → [new "Planning"] / new task
4. [Xh] Fix session hook timing        → new task
─────────────────────────────────────────
```

Legend:
- `→ TASK-XXXX` — direct assignment to existing task
- `→ [GROUP-XXXX] / new task` — will create child under existing group
- `→ [new "Name"] / new task` — will create a new group, then a child under it
- `→ new task` — root level, no group

**New edit commands (Step 3):**
- `"put entry N under Group X"` → set `parent_task`, clear others, show draft
- `"create group Z for entry N"` → set `proposed_group`, clear others, show draft
- `"move entry N to root"` → clear `parent_task` and `proposed_group`, show draft
- `"rename the new group to X"` → update `proposed_group` subject, show draft

---

## Step 4 — Auto-Create Order (SKILL.md)

When auto-creating tasks for unassigned entries, process in this order:

1. **Create new groups** — entries with `proposed_group` set; call `createTask` with `is_group=True`, `subject=proposed_group`. Collect returned names.
2. **Create child tasks** — entries with `parent_task` set (either an existing group name or a name from step 1); call `createTask` with `parent_task` set.
3. **Create root tasks** — entries with no placement field set.
4. Assign all returned task names to their entries before calling `submitTimesheet`.

Show the created task list as before: `TASK-XXXX — subject` for each. Note any project date extensions.

---

## MCP Tool — `createTask`

Two new optional parameters:

| Parameter | Type | Default | Meaning |
|---|---|---|---|
| `parent_task` | str | None | Place this task under an existing group task |
| `is_group` | bool | False | Create a group task (container for child tasks) |

---

## ERPNextClient — `create_task()`

**When `is_group=True`:**
- Add `"is_group": 1` to the ERPNext doc
- Omit `"status": "Completed"` (group tasks stay Open)
- Omit `"expected_time"`, `"exp_start_date"`, `"exp_end_date"`, `"custom_planned_completion_date"` (these belong to leaf tasks)

**When `parent_task` is provided:**
- Add `"parent_task": parent_task` to the ERPNext doc

Both can be combined (creating a group that is itself a child of another group).

---

## What Does Not Change

- `submitTimesheet`, `checkExisting`, `readHistory`, `isReady`, `updateSettings`, `listTasks` — unchanged
- The existing `task` assignment behavior for strong leaf matches — unchanged
- Hours redistribution logic — unchanged
