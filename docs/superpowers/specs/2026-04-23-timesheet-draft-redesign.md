# Timesheet Draft Redesign + Submitter Agent

**Date:** 2026-04-23
**Scope:** SKILL.md rewrite of Steps 2–4 + new `agents/timesheet-submitter.md`

---

## 1. Draft Format

Every entry is **two lines** in a monospace draft block.

```
✓ 1. [2h] Implemented credential loading fix
      Development  ·  PROJ-0041 / Dev Work / TASK-0042

⚠ 2. [2h] Debugged MCP env var injection
      Debugging    ·  PROJ-0041 / ? needs matching
```

**Line 1:** `{marker} {n}. [{h}h] {description}`
**Line 2:** `      {activity}  ·  {project} / {group} / {task}`

### Rules

- Project is **always shown** — never omitted, even on single-project days.
- Group is shown when known; `/ ? needs matching` when unresolved.
- Task field values: `TASK-XXXX` (matched), `TASK-XXXX ⚠ Nd` (overdue matched), `new task` (will be created), `? needs matching` (unresolved).

### Status markers (left column, column 0)

| Marker | Meaning |
|--------|---------|
| `✓` | Auto-resolved with confidence |
| `⚠` | Needs resolution via AskUserQuestion |

### Color scheme

| Element | Color |
|---------|-------|
| Hours `[2h]` | Cyan |
| Description | Near-white |
| Activity type | Slate |
| Project | Purple |
| Task group | Pink |
| Existing matched task | Green |
| Overdue matched task | Orange |
| New task (to be created) | Amber |
| ✓ marker | Bright green |
| ⚠ marker | Red |
| `?` unresolved placeholder | Amber-dark |

---

## 2. Auto-Matching Rules (Step 2)

Claude runs a silent best-effort match against fetched tasks after synthesizing entries.

**✓ auto-resolved** when:
- Exactly one task has clear keyword overlap with the entry description, OR
- No task matched but the group placement is unambiguous (one group clearly fits) → resolved as `new task` under that group.

**⚠ needs matching** when:
- Zero tasks match, OR
- Two or more tasks are plausible with similar keyword overlap (ambiguous).

Entries explicitly assigned by the user during conversational edits are always marked ✓.

---

## 3. Within-Draft Interactive Resolution (Step 3)

The draft is shown first — resolved (✓) and unresolved (⚠) entries visible together. After display, AskUserQuestion fires for each unresolved entry.

### Clustering (before per-entry questions)

Before any AskUserQuestion call, Claude scans all ⚠ entries for semantic similarity. Entries sharing topic keywords are grouped into a cluster and handled with **one question**:

> "Entries 2, 3, 4 seem related to MCP plugin work (PROJ-0041). No matching group found — what should we do?"
>
> Options:
> 1. Create group "{suggested name}" → put all N entries under it
> 2. Use existing group → pick from list
> 3. No group → create root-level tasks
> 4. Split → handle each separately

### Per-entry resolution (unclustered or split)

Three sequential questions, each skipped if already known:

**1. Project** — asked only if the default project is absent or the entry seems off-topic.
Options: list of projects + "Other (type it)"

**2. Group** — lists existing groups for the project, plus:
- "Create new group (I'll name it)" → on selection, immediately offer to pull in other unmatched entries via multi-select
- "No group (root-level task)"

**3. Task** — lists open tasks in the chosen group (overdue tasks first, flagged `⚠ Nd`), plus "New task (create one)". If no group: lists all open tasks in the project.

### Post-resolution

After all ⚠ entries are resolved, the draft **re-renders in full** with updated ✓ markers. The user sees the final state and confirms before submission.

---

## 4. Submitter Agent (`agents/timesheet-submitter.md`)

A dedicated subagent dispatched after the user approves the final draft. The skill passes `TARGET_DATE`, `STATUS`, and the final `ENTRIES` list in the dispatch prompt.

### Execution order

1. `checkExisting` — verify no duplicate
2. Create new groups (`createTask` with `is_group=True`), collect returned IDs
3. Create child tasks (entries with `parent_task`)
4. Create root tasks (entries with no parent)
5. `submitTimesheet` with all entries, task IDs assigned

### Output format

Each line written as the action completes:

```
Submitting timesheet for 2026-04-23...

- [x] No duplicate found
- [x] Created group "MCP Plugin Work" → TASK-GRP-012
- [x] Created task "Debugged MCP env var injection" → TASK-0051
- [x] Created task "Investigated plugin credential flow" → TASK-0052
- [x] Submitted → TS-0089

Done.
```

### Agent constraints

- `disallowedTools: Write, Edit`
- Only MCP tools used: `checkExisting`, `createTask`, `submitTimesheet`
- On failure: stop, show error, ask "Retry?" — max 3 attempts
- Auth failure at any step: surface the re-configure message and stop

---

## Implementation Scope

**Files changed:**
- `skills/timesheet/SKILL.md` — rewrite Steps 2, 3, 4
- `agents/timesheet-submitter.md` — new file

**Files unchanged:**
- `mcp_server.py` — no new MCP tools needed
- `plugin.json` — no changes
- All tests pass as-is
