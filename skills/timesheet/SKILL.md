---
name: timesheet
description: Use when the user wants to submit today's ERPNext timesheet, log work hours, fill in a timesheet from conversation history, or make a backdated timesheet entry for a previous date. Uses MCP tools to interact with ERPNext.
version: 2.0.11
---

# ERPNext Timesheet

Automate daily ERPNext timesheet filling from your Claude conversation history.

---

When this skill is invoked, follow these steps exactly. Do not skip steps. Do not narrate which step you are on — no "Starting Step N", no "checking X", no intermediate announcements. The only output before the draft is the installation messages block (if any) and the setup prompt or announce line.

## Step 0: Setup and Date Resolution

**Resolve the target date.** Read the invocation message:
- If it specifies a past date (e.g. "for yesterday", "for 2026-03-24", "last Friday") — resolve it to `YYYY-MM-DD` and store as `TARGET_DATE`.
- Otherwise use today's date.

Call `isReady` silently. Store the full response as `STATUS`.

**If `configured` is `false` and `needs_defaults` is not set:**

If the SessionStart hook reported installation activity, output each line exactly as received — no rewording, no summarising. Render them in a code block, one line per entry.

Tell the user:

> Open a new terminal and run:
> ```
> timesheet-setup
> ```
> Once done, re-run `/timesheet`.

Stop here — do not wait, do not call `isReady` again.

**If `configured` is `false` and `needs_defaults` is `true`:**

Credentials are saved but defaults are missing. Use `AskUserQuestion` with two questions using `STATUS._projects` and `STATUS._activity_types`:
- **Default Project**: up to 4 options from `_projects` (show `label`, value is `id`); mark current default as "(Selected)"
- **Default Activity**: always offer these 4 options: Development, Development Testing, Debugging, Debug & Fix — plus the user can type Other for anything else

Call `updateSettings` with the selected `project` and `activity_type`. Store the return value as `STATUS` — it has the same shape as a configured `isReady` response. Do not call `isReady` again.

**If `configured` is `true` and user mentioned reconfiguring:**

Tell the user to run `timesheet-setup` in a new terminal, then re-run `/timesheet`. Stop here.

Announce: `Logging work for TARGET_DATE — <username> on <url>`

Otherwise proceed directly to Step 1.

## Step 1: Read Work Context

Call `readHistory` with `date=TARGET_DATE` silently. Store as `MESSAGES`.

**If the user specified a different source** (git commits, manual description, a file), use that instead — run `git log`, read files, or ask. The goal is the same: gather enough context to synthesize entries in Step 2.

If no messages found, tell the user briefly and continue to Step 3 with an empty list.

## Step 2: Synthesize + Fetch Tasks

From `MESSAGES`, identify distinct work themes. Create entries where:
- **description**: concise professional summary, max 80 chars, no filler phrases ("worked on", "helped with")
- **hours**: `STATUS.work_hours / number_of_tasks`, rounded to 1 decimal; last entry absorbs rounding remainder so total equals `work_hours` exactly
- **activity_type**: `STATUS.default_activity`
- **task**: not set yet — assigned via auto-matching below

Grouping rules:
- Merge closely related messages (e.g. "fix bug" + "write test for fix" = one entry)
- Ignore meta-conversation (greetings, off-topic chat)
- Focus on deliverables: what was built, fixed, reviewed, or designed
- 1–8 entries

Call `listTasks` with `project=STATUS.project` silently. Store as `TASKS`.

**Identify overdue tasks:** walk `TASKS` recursively; collect nodes where `exp_end_date` is non-empty and `exp_end_date < TARGET_DATE`. (Completed and Cancelled tasks are excluded at fetch time.)

**Auto-match:** for each entry, find the closest task in `TASKS` by keyword overlap. Walk `TASKS` recursively — groups and leaves are both valid match targets. Assign if a good match exists; leave unassigned otherwise.

**Group placement:** For each entry, determine where a new task will be placed if one must be created:

1. If `task` points to a group (`is_group=1`) and keyword overlap with that group is vague (the group was the closest available but not a clear match) → demote: clear `task`, set `parent_task` to that group's name.
2. For entries with no `task` → walk `TASKS` recursively to find the best-fit group by keyword overlap:
   - Clear group match → set `parent_task` to that group's name
   - No good group match → propose a new group subject → set `proposed_group`
3. Entries where no group is semantically appropriate → leave `parent_task` and `proposed_group` unset (root level).

Apply rules 1–3 in order. After all three rules are evaluated, store the final state on each entry in `ENTRIES`. The postcondition is: at most one of `task`, `parent_task`, `proposed_group` is set per entry.

Store synthesized entries as `ENTRIES`.

## Step 3: Draft Review

If overdue tasks exist, list them before the draft:
> **Overdue:** TASK-XXXX — subject (N days), ...

Display the draft:

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

Legend: `→ TASK-XXXX` = direct assign; `→ [GROUP] / new task` = child of existing group; `→ [new "Name"] / new task` = child of proposed new group; `→ new task` = root level.

**Unmatched entries and project hints:** For entries showing `→ new task`, use conversation context to judge whether the work likely belongs to a different project than `STATUS.project`. If yes, flag the entry in the draft:

```
3. [2h] Review vendor proposal    → new task (different project?)
```

If the user confirms or asks to assign a different project to any entry, call `listProjects` silently (once — reuse if already fetched), present the list, let the user pick, then call `listTasks` for that project and re-run auto-match for the affected entries. Update `entry.project` on each reassigned entry.

**Handle edits conversationally.** `TASKS` is already in context — no extra MCP call unless the user asks to create a new task.

- Edit description → update entry, show draft
- Delete entry → remove, recalculate hours, show draft
- Add entry → append, show draft
- Assign by name or topic → look up in `TASKS` recursively (search all nodes), assign, show draft
- Create new task → ask for subject (pre-fill from entry), call `createTask`, assign returned name, show draft
- Redistribute hours → recalculate evenly, show draft
- "Submit" / "Looks good" / "Go ahead" → Step 4
- Move to existing group → `"put entry N under Group X"` → set `parent_task` to matched group name, clear `proposed_group`, show draft
- Propose new group → `"create group Z for entry N"` → set `proposed_group` to Z, clear `parent_task`, show draft
- Remove group placement → `"move entry N to root"` → clear both `parent_task` and `proposed_group`, show draft
- Rename proposed group → `"rename the new group to X"` → update `proposed_group` subject, show draft
- Reassign project → `"entry N is from a different project"` or `"move entry N to another project"` → call `listProjects` (once, if not already fetched), present the list, user picks → call `listTasks` for that project (if not already fetched), re-run auto-match for affected entries, set `entry.project`, show draft

**Hours mismatch:** if total ≠ `STATUS.work_hours` at approval, note it: "Total is Xh, default is Yh — proceed?" and wait.

**Empty entries:** if user tries to submit with no entries, ask them to add some first.

## Step 4: Duplicate Check + Submit

Call `checkExisting` with `date=TARGET_DATE` silently.

If `exists` is `true`: "A timesheet already exists for TARGET_DATE — submit anyway?" If no, return to Step 3.

**Auto-create tasks for unassigned entries** in this order. Only process entries where `task` is not yet assigned — entries with `task` already set skip directly to step 4 (assign names).

1. **New groups first** — for entries with `proposed_group` set: call `createTask` with `subject=proposed_group`, `description=proposed_group`, `project=entry.project (or STATUS.project if not set)`, `hours=0`, `date=TARGET_DATE`, `is_group=True`. Collect returned names. For each such entry, update its `parent_task` to the returned name (the actual ERPNext task ID) before proceeding to step 2.
2. **Child tasks** — for entries with `parent_task` set (either an existing group name or a name returned in step 1): call `createTask` with `parent_task` set, `project=entry.project (or STATUS.project if not set)`, `is_group=False`.
3. **Root tasks** — for entries with neither `parent_task` nor `proposed_group` set: call `createTask` with no parent, `project=entry.project (or STATUS.project if not set)`, `is_group=False`.
4. Assign all returned task names to their entries before calling `submitTimesheet`.

After all are created, show a brief list: `TASK-XXXX — subject` for each. Print any `notes`.

Call `submitTimesheet` with `date=TARGET_DATE` and `entries=ENTRIES`. Each entry must include `description`, `hours`, `activity_type`; include `task` only if assigned.

Success: `Submitted — TS-XXXX`

Failure: show the error, ask "Retry?" Max 3 attempts. After 3, tell the user to check their ERPNext connection.

**If any MCP call returns `{"error": "auth_failed"}` at any step:** tell the user:
> Your ERPNext session has expired. Open a new terminal, run `timesheet-setup`, then come back and re-run `/timesheet`.
Do not retry — re-authentication requires running the setup script.
