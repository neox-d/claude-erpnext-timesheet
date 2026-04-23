---
name: timesheet
description: Use when the user wants to submit today's ERPNext timesheet, log work hours, fill in a timesheet from conversation history, or make a backdated timesheet entry for a previous date. Uses MCP tools to interact with ERPNext.
version: 2.1.0
---

# ERPNext Timesheet

Automate daily ERPNext timesheet filling from your Claude conversation history.

---

When this skill is invoked, follow these steps exactly. Do not skip steps. Before the draft (Steps 0–2): no narration — no "Starting Step N", no "checking X", no intermediate announcements. The only output before the draft is the setup prompt or announce line. During Step 3: use AskUserQuestion as specified. During Step 4: show the timesheet-submitter agent's output verbatim.

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

**If `CONFIG.configured` is `false` and `reason` is `connection_error`:**

> Could not connect to your ERPNext instance. Check that your URL is correct and the server is reachable, then re-run `/timesheet`.

Stop here.

**If the invocation message mentions reconfiguring, changing credentials, or updating settings:** tell the user to run `/plugin config erpnext-timesheet`, then re-run `/timesheet`. Stop here.

**If `CONFIG.configured` is `true`:**

**If `project` or `default_activity` is empty:**

Credentials are saved but defaults are missing. Use `AskUserQuestion` with two questions using `CONFIG._projects` and `CONFIG._activity_types`:
- **Default Project**: up to 4 options from `_projects` (show `label`, value is `id`); mark current default as "(Selected)"
- **Default Activity**: always offer these 4 options: Development, Development Testing, Debugging, Debug & Fix — plus the user can type Other for anything else

Call `updateSettings` with the selected `project` and `activity_type`. Store the return value as `STATUS` — it has the full configured shape. Proceed to Step 1.

**Otherwise** build `STATUS` directly from `CONFIG` — `configured: true`, `username`, `url`, `project`, `default_activity` taken directly; `work_hours` defaults to 8 if absent.

Announce: Logging work for `TARGET_DATE` — `<username>` on `<url>`

Proceed to Step 1.

## Step 1: Read Work Context

Call `readHistory` with `date=TARGET_DATE` silently. Store as `MESSAGES`.

**If the user specified a different source** (git commits, manual description, a file), use that instead — run `git log`, read files, or ask. The goal is the same: gather enough context to synthesize entries in Step 2.

If no messages found, tell the user briefly and continue to Step 3 with an empty list.

## Step 2: Synthesize + Fetch Tasks

From `MESSAGES`, identify distinct work themes. Create entries where:
- **description**: concise professional summary, max 80 chars, no filler phrases ("worked on", "helped with")
- **hours**: `STATUS.work_hours / number_of_tasks`, rounded to 1 decimal; last entry absorbs rounding remainder so total equals `work_hours` exactly
- **activity_type**: `STATUS.default_activity`
- **project**: `STATUS.project` (default; may be overridden per entry during Step 3)

Grouping rules:
- Merge closely related messages (e.g. "fix bug" + "write test for fix" = one entry)
- Ignore meta-conversation (greetings, off-topic chat)
- Focus on deliverables: what was built, fixed, reviewed, or designed
- 1–8 entries

Call `listTasks` with `project=STATUS.project` silently. Store as `TASKS`.

**Identify overdue tasks:** walk `TASKS` recursively; collect nodes where `exp_end_date` is non-empty and `exp_end_date < TARGET_DATE`. (Completed and Cancelled tasks are excluded at fetch time.)

**Auto-match and classify each entry:**

For each entry, search `TASKS` recursively by keyword overlap between the entry description and task subjects:

- **✓ resolved (existing task)** — exactly one task has clear keyword overlap. Set `entry.task = task.name`. If the matched task has a parent, set `entry.parent_task = task.parent_task`. Set `entry.resolved = true`. Set `entry.cluster_id = null`.
- **✓ resolved (new task, group known)** — zero tasks match AND exactly one group has clear keyword overlap with the description. Set `entry.parent_task = group.name`, leave `entry.task` unset. Set `entry.resolved = true`. Set `entry.cluster_id = null`.
- **⚠ unresolved** — zero matches with no clear group fit, OR two or more tasks share similar keyword overlap (ambiguous). Set `entry.resolved = false`.

**Cluster unresolved entries:**

After classifying all entries, group the ⚠ entries by shared topic keywords (e.g. entries mentioning "MCP", "plugin", "auth" form a cluster). Store each cluster as a list of entry indices. Assign each ⚠ entry a `cluster_id` (a short label like "mcp-work"); singletons get `cluster_id = null`.

Store synthesized entries as `ENTRIES`.

## Step 3: Draft Review

If overdue tasks were identified in Step 2, list them before the draft:
> **Overdue tasks:** TASK-XXXX — subject (N days overdue), ...

**Display the draft:**

Each entry is two lines. Status marker at column 0 (`✓` resolved, `⚠` needs matching):

```
TARGET_DATE — Xh total
──────────────────────────────────────────────────────────────
✓ 1. [Xh] Description one
      Activity  ·  PROJ-XXXX / Group Name / TASK-XXXX

✓ 2. [Xh] Description two
      Deployment  ·  PROJ-XXXX / Infrastructure / new task

⚠ 3. [Xh] Description three
      Development  ·  PROJ-XXXX / ? needs matching
──────────────────────────────────────────────────────────────
N entries need matching — resolving below.
```

Rules:
- Project is **always shown** — never omitted, even on single-project days.
- Group field: existing group name (plain text), proposed new group as `[new "Name"]`, omitted as `/ ? needs matching` if unknown.
- Task field: `TASK-XXXX` (matched), `TASK-XXXX ⚠ Nd` (overdue matched), `new task` (will create), `? needs matching` (unresolved).
- Show `N entries need matching — resolving below.` only if N > 0. If all resolved from the start, show `All resolved — submit, or let me know what to change.` instead.

**Interactive resolution (only if ⚠ entries exist):**

Process clusters before singletons.

**Cluster resolution** — for each cluster of 2+ ⚠ entries (same `cluster_id`):

Use `AskUserQuestion`:
- Question: `Entries {n1}, {n2}, ... seem related to {inferred topic} ({entry.project}) — could not auto-match. What should we do?`
- Options:
  1. `Create group "{suggested name}"` — set `entry.proposed_group` to the suggested name for all entries in the cluster; mark all resolved
  2. `Use existing group` — follow up with a second `AskUserQuestion` listing existing groups from `TASKS` for `entry.project` (default project); set `entry.parent_task` for all cluster entries; mark all resolved
  3. `No group (root-level tasks)` — clear `parent_task` and `proposed_group` on all cluster entries; mark all resolved
  4. `Split — handle each separately` — treat each cluster entry as a singleton below

**Per-entry resolution** — for singletons and entries split from clusters, in order:

**Q1 — Project** (skip if `entry.project` is already set):
Use `AskUserQuestion`:
- Question: `Entry N — "{description}" — which project?`
- Options: each item from `CONFIG._projects` (show `label`, value is `id`) + `Other (I'll type it)`
Set `entry.project` to the selected id.

**Q2 — Group** (skip if `entry.parent_task` or `entry.proposed_group` is already set):
Use `AskUserQuestion`:
- Question: `Entry N — "{description}" — which task group? ({entry.project})`
- Options: existing groups from `TASKS` (nodes where `is_group=1`) + `Create new group` + `No group (root-level task)`

If `Create new group` selected:
- Derive a suggested group name from the entry description (short, title-case, topic-focused — e.g. "MCP Plugin Work", "Auth Refactor"). Use `AskUserQuestion` with the question `Name for this group?` and options: the suggested name first, then `Rename (I'll type it)`. If `Rename` selected, ask for the name as a plain conversational message and wait for their reply; then echo `Using "{name}".` before continuing. Set `entry.proposed_group` to the chosen name.
- Immediately offer to pull in other ⚠ entries that don't yet have a group: use `AskUserQuestion` listing each remaining entry where `resolved = false` and `parent_task` and `proposed_group` are both unset — as a multi-select. For each entry selected, set `entry.proposed_group` to the same name and mark `entry.resolved = true`, skipping their Q2/Q3.

If an existing group selected: set `entry.parent_task = group.name`.
If `No group`: leave both unset; mark `entry.resolved = true`.

**Q3 — Task** (skip if `entry.task` is set, `entry.parent_task` is set, `entry.proposed_group` is set, or `entry.resolved` is true):
Use `AskUserQuestion`:
- Question: `Entry N — "{description}" — assign to an existing task?`
- Options — overdue tasks first, then open tasks, then new:
  - Overdue: `TASK-XXXX — {subject} (⚠ Nd overdue)`
  - Open: `TASK-XXXX — {subject}`
  - Last option: `New task (create one under {group name or "root"})`

If an existing task selected: set `entry.task = task.name`. Mark `entry.resolved = true`.
If `New task`: leave `entry.task` unset. Mark `entry.resolved = true`.

**After all entries resolved:**

Re-render the full draft with `✓` on all entries:

```
TARGET_DATE — Xh total
──────────────────────────────────────────────────────────────
✓ 1. [Xh] Description one
      Activity  ·  PROJ-XXXX / Group Name / TASK-XXXX

✓ 2. [Xh] Description two
      Activity  ·  PROJ-XXXX / [new "Group Name"] / new task
──────────────────────────────────────────────────────────────
All resolved — submit, or let me know what to change.
```

**Conversational edits** (handle at any point):

- Edit description → update entry, re-render draft
- Delete entry → remove, recalculate hours, re-render draft
- Add entry → append, re-render draft
- Change activity → update `entry.activity_type`, re-render draft
- Reassign to leaf task → look up leaf tasks (non-group) in `TASKS` recursively, assign, re-render draft
- Move to group → look up groups (`is_group=1`) in `TASKS`, set `entry.parent_task`, clear `entry.proposed_group`, re-render draft
- Change project → set `entry.project`, re-fetch tasks if needed, re-run Q2/Q3 for that entry
- Redistribute hours → recalculate evenly, re-render draft
- Move to root → clear both `entry.parent_task` and `entry.proposed_group`, re-render draft
- "Submit" / "Looks good" / "Go ahead" → Step 4

**Hours mismatch:** if total ≠ `STATUS.work_hours` at approval, note it: "Total is Xh, default is Yh — proceed?" and wait.

**Empty entries:** if user tries to submit with no entries, ask them to add some first.

## Step 4: Submit

Call `checkExisting` with `date=TARGET_DATE` silently.

If `exists` is `true`: "A timesheet already exists for TARGET_DATE — submit anyway?" If no, return to Step 3.

Dispatch to the `timesheet-submitter` agent with this prompt (substitute actual values):

```
Submit timesheet for {TARGET_DATE}.

TARGET_DATE: {TARGET_DATE}
STATUS: {JSON — include username, project, work_hours}
ENTRIES: {JSON array — each entry with: description, hours, activity_type, project, task (if set), parent_task (if set), proposed_group (if set)}
```

Display the agent's output to the user verbatim as it arrives.

**If any MCP call returns `{"error": "auth_failed"}` at any step:** tell the user:
> Your ERPNext session has expired. Run `/plugin config erpnext-timesheet` to update your credentials, then re-run `/timesheet`.
