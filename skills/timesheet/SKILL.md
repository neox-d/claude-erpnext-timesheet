---
name: timesheet
description: Use when the user wants to submit today's ERPNext timesheet, log work hours, fill in a timesheet from conversation history, or make a backdated timesheet entry for a previous date. Uses MCP tools to interact with ERPNext.
version: 2.0.5
---

# ERPNext Timesheet

Automate daily ERPNext timesheet filling from your Claude conversation history.

---

When this skill is invoked, follow these steps exactly. Do not skip steps.

## Step 0: Setup and Date Resolution

**Resolve the target date.** Read the invocation message:
- If it specifies a past date (e.g. "for yesterday", "for 2026-03-24", "last Friday") — resolve it to `YYYY-MM-DD` and store as `TARGET_DATE`.
- Otherwise use today's date.

Call `isReady` silently. Store the full response as `STATUS`.

**If `configured` is `false` and `needs_defaults` is `true`:**

Credentials are saved but defaults are missing. Use `AskUserQuestion` with two questions using `STATUS._projects` and `STATUS._activity_types`:
- **Default Project**: up to 4 options from `_projects` (show `label`, value is `id`); mark current default as "(Selected)"
- **Default Activity**: always offer these 4 options: Development, Development Testing, Debugging, Debug & Fix — plus the user can type Other for anything else

Call `updateSettings` with the selected `project` and `activity_type`. Call `isReady` again and store as `STATUS`.

**If `configured` is `false` and `needs_defaults` is not set:**

Tell the user:

> Open a new terminal and run:
> ```
> STATUS.setup_command
> ```
> Enter your credentials, then come back here.

Wait for the user to return. Call `isReady` again. If still not configured, repeat.

Once configured, use `AskUserQuestion` with two questions using `STATUS._projects` and `STATUS._activity_types`:
- **Default Project**: up to 4 options from `_projects` (show `label`, value is `id`); mark current default as "(Selected)"
- **Default Activity**: always offer these 4 options: Development, Development Testing, Debugging, Debug & Fix — plus the user can type Other for anything else

Call `updateSettings` with the selected `project` and `activity_type`.

Announce: `Logging work for TARGET_DATE — <username> @ <url>`

**If `configured` is `true` and user mentioned reconfiguring:**

Tell the user to run `STATUS.setup_command` in a new terminal, then come back. Call `isReady` again — it will return `needs_defaults: true` so the selector flow above will run automatically.

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

**Identify overdue tasks:** entries in `TASKS` where `exp_end_date` is non-empty, `exp_end_date < TARGET_DATE`, and `status` is not `"Completed"` or `"Cancelled"`.

**Auto-match:** for each entry, find the closest task in `TASKS` by keyword overlap. Assign if a good match exists; leave unassigned otherwise.

Store synthesized entries as `ENTRIES`.

## Step 3: Draft Review

If overdue tasks exist, list them before the draft:
> **Overdue:** TASK-XXXX — subject (N days), ...

Display the draft:

```
TARGET_DATE — Xh total
─────────────────────────────────────────
1. [Xh] Description one          → TASK-XXXX
2. [Xh] Description two          → no task
─────────────────────────────────────────
Submit, or let me know what to change.
```

**Handle edits conversationally.** `TASKS` is already in context — no extra MCP call unless the user asks to create a new task.

- Edit description → update entry, show draft
- Delete entry → remove, recalculate hours, show draft
- Add entry → append, show draft
- Assign by name or topic → look up in `TASKS`, assign, show draft
- Create new task → ask for subject (pre-fill from entry), call `createTask`, assign returned name, show draft
- Redistribute hours → recalculate evenly, show draft
- "Submit" / "Looks good" / "Go ahead" → Step 4

**Hours mismatch:** if total ≠ `STATUS.work_hours` at approval, note it: "Total is Xh, default is Yh — proceed?" and wait.

**Empty entries:** if user tries to submit with no entries, ask them to add some first.

## Step 4: Duplicate Check + Submit

Call `checkExisting` with `date=TARGET_DATE` silently.

If `exists` is `true`: "A timesheet already exists for TARGET_DATE — submit anyway?" If no, return to Step 3.

**Auto-create tasks for unassigned entries:** for each unassigned entry, call `createTask` with `subject` = description (max 140 chars), `description` = description, `project` = STATUS.project, `hours` = entry hours, `date` = TARGET_DATE. Assign the returned `name`. After all are created, show a brief list: `TASK-XXXX — subject` for each. Print any `notes`.

Call `submitTimesheet` with `date=TARGET_DATE` and `entries=ENTRIES`. Each entry must include `description`, `hours`, `activity_type`; include `task` only if assigned.

Success: `Submitted — TS-XXXX`

Failure: show the error, ask "Retry?" Max 3 attempts. After 3, tell the user to check their ERPNext connection.

**If any MCP call returns `{"error": "auth_failed"}` at any step:** tell the user:
> Your ERPNext session has expired. Open a new terminal, run `timesheet-setup`, then come back and re-run `/timesheet`.
Do not retry — re-authentication requires running the setup script.
