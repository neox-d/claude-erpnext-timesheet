---
name: timesheet
description: Use when the user wants to submit today's ERPNext timesheet, log work hours, fill in a timesheet from conversation history, or make a backdated timesheet entry for a previous date
version: 2.0.0
---

# ERPNext Timesheet

Automate daily ERPNext timesheet filling from your Claude conversation history.

---

When this skill is invoked, follow these steps exactly. Do not skip steps.

## Step 0: Setup and Date Resolution

**Resolve the target date first.** Read the invocation message:
- If it specifies a past date (e.g. "for yesterday", "for 2026-03-24", "last Friday") — resolve it to `YYYY-MM-DD` format and store as `TARGET_DATE`.
- Otherwise set `TARGET_DATE` to today's date (`YYYY-MM-DD`).

Announce: "Using erpnext-timesheet to log work for TARGET_DATE..."

Call the `get_status` MCP tool.

Branch on the result:

**`configured` is `false`:** Tell the user:
> "To get started, run `python3 ~/.claude/timesheet-setup` in a new terminal, then come back and say done."
Wait for the user to say done. Call `get_status` again. If still not configured, repeat. Once configured, proceed.

**`configured` is `true`:** Tell the user:
> "Logged in as `<username>` (`<url>`) — shall I continue, or do you want to reconfigure?"
- If continue: proceed to Step 1.
- If reconfigure: "Run `python3 ~/.claude/timesheet-setup` in a new terminal, then say done." Wait and re-call `get_status`. Once configured, proceed to Step 1.

No setup wizard. No bash commands. Store the full `get_status` response as `STATUS` (it contains `work_hours`, `project`, `default_activity` used in later steps).

## Step 1: Validate Config

Call the `validate_config` MCP tool silently. Do not display the raw output.

If `valid` is `false`: show the errors list to the user and stop. Do not proceed.

## Step 2: Read Work Context

Tell the user: "Reading work context for TARGET_DATE..."

Call the `read_messages` MCP tool with `date_str=TARGET_DATE`.

**If the user specified a different data source** (e.g. "use my git commits", "I'll describe what I did"), use that instead. Adapt naturally — run `git log`, read files, or ask the user to describe their work. The goal is the same: gather enough context to synthesize task entries in Step 3.

Store the messages as `MESSAGES`.

## Step 3: Synthesize + Fetch Tasks

Tell the user: "Summarizing work done..."

From `MESSAGES`, identify distinct work themes. Create task entries where:
- **description**: short professional summary of the work, max 80 characters, no filler ("worked on", "helped with")
- **hours**: `work_hours / number_of_tasks` (use `STATUS.work_hours`), rounded to 1 decimal. Last task absorbs rounding remainder so total equals work_hours exactly.
- **activity_type**: use `STATUS.default_activity`
- **task**: not set at synthesis time — suggested via auto-matching below

Rules:
- Group closely related messages into one task (e.g. "fix bug" + "write test for fix" = one task)
- Ignore meta-conversation (greetings, "thanks", off-topic chat)
- Focus on deliverables: what was built, fixed, reviewed, or designed
- Minimum 1 task, maximum 8 tasks

If no messages were found, tell the user and proceed to Step 4 with an empty list.

**Fetch project tasks:** Immediately call `get_tasks` MCP tool with `project=STATUS.project`.

Store the returned list as `TASKS`.

**Identify overdue tasks:** Tasks in `TASKS` where `exp_end_date` is a non-empty string and `exp_end_date < TARGET_DATE` (string date comparison, ISO format) and `status` is not `"Completed"` and not `"Cancelled"`.

**Auto-match:** For each synthesized entry, compare its description to the subjects of tasks in `TASKS`. If a close match exists (similar topic, keywords overlap), suggest that task as the assignment. If no good match, leave unassigned (will show "no task").

Store the synthesized entries with their suggested task assignments as `ENTRIES`.

## Step 4: Draft Review

If overdue tasks were found in Step 3, tell the user:
> "You have N overdue task(s): [list each as: name — subject (N days overdue)]. I've suggested task assignments in the draft below."

Display the draft:
```
Draft timesheet for TARGET_DATE (Xh total):
──────────────────────────────────────────
1. [Xh] Entry description one        → TASK-XXXX (suggested)
2. [Xh] Entry description two        → no task
──────────────────────────────────────────
```

Close with:
> "Ready to submit, or would you like to make changes? You can edit, delete, or add an entry, reassign or create a task, redistribute hours, or I can submit as-is."

**Handle responses conversationally.** No bracket shortcuts. Since `TASKS` is already in context from Step 3, no additional MCP call is needed for task assignment (unless the user asks to create a new task).

Examples of what the user might say and how to respond:
- "Edit entry 2 description to X" — update that entry's description in `ENTRIES`, show updated draft.
- "Delete entry 3" — remove it from `ENTRIES`, recalculate hours, show updated draft.
- "Add an entry: Reviewed PRs, 1 hour" — add it to `ENTRIES`, show updated draft.
- "Assign entry 1 to TASK-001" — look up that task name in `TASKS`, assign it, show updated draft.
- "Assign entry 2 to the bug fix task" — find the closest match in `TASKS` by subject, confirm with user, assign it, show updated draft.
- "Create a new task for entry 1" — ask for subject and description (pre-fill from entry), call `create_task` MCP tool, assign returned name, print any notes, show updated draft.
- "Redistribute hours to 6h total" — recalculate hours evenly, last entry absorbs remainder, show updated draft.
- "Submit" or "Looks good" or "Go ahead" — proceed to Step 5.

**Hours mismatch:** If total hours ≠ `STATUS.work_hours` when the user approves, note it conversationally: "Total is Xh (your configured default is Yh) — proceed?" and wait for confirmation.

**Empty entries:** If the user tries to submit with no entries, tell them there are no entries and ask them to add some.

When the user approves, proceed to Step 5.

## Step 5: Duplicate Check + Submit

Call the `check_duplicate` MCP tool with `date_str=TARGET_DATE` silently.

If `exists` is `true`: "A timesheet already exists for TARGET_DATE. Submit anyway?" If the user says no, return to Step 4.

Tell the user: "Submitting timesheet..."

Call the `submit_timesheet` MCP tool with `date_str=TARGET_DATE` and `entries=ENTRIES`. Each entry must include `description`, `hours`, `activity_type`. Include `task` key only for entries with a task assigned.

If success: "Timesheet submitted. Reference: TS-XXXX."

If failure: show the error and ask "Retry?" Maximum 3 total attempts. After 3 failed attempts, tell the user to check their ERPNext connection and try again later.
