# ERPNext Timesheet v4 — Design Spec

**Date:** 2026-03-27
**Scope:** MCP server, terminal setup CLI, conversational TUI, proactive task integration

---

## Overview

Four improvements to the ERPNext Timesheet plugin:

1. **MCP server** — replace 4 Python CLI scripts with a single MCP server; all operational calls become compact MCP tool calls instead of visible `● Bash(...)` blocks
2. **Terminal setup CLI** — remove the setup wizard from SKILL.md entirely; a standalone script handles first-run setup in the user's own terminal with proper password masking
3. **Conversational TUI** — remove all CLI-style bracket shortcuts (`[a]`, `[e]`, `[y/n]`, etc.); the draft review step is fully conversational
4. **Proactive task integration** — fetch project tasks during synthesis; show overdue tasks; auto-suggest task assignments; no on-demand MCP calls during TUI navigation

---

## 1. MCP Server

### Registration

`plugin.json` gains an `mcpServers` field. Claude Code starts the server automatically when the plugin is enabled.

```json
"mcpServers": {
  "erpnext-timesheet": {
    "command": "python3",
    "args": ["${CLAUDE_PLUGIN_ROOT}/skills/timesheet/mcp_server.py"]
  }
}
```

### Server location

`skills/timesheet/mcp_server.py` — single file containing all tool implementations. The existing four CLI scripts (`setup.py`, `parse_logs.py`, `erpnext_client.py`, `task_manager.py`) are deleted; their logic moves into this file. `crypto.py` remains as a shared utility, imported by the MCP server.

`pyproject.toml` gains `mcp[cli]` as a dependency.

### Tools

**`get_status()`** → `{configured, username, url, setup_command}`

Reads `~/.claude/timesheet.json` if it exists. Returns `configured: false` with `setup_command` populated if the config is missing. Whenever `~/.claude/timesheet-setup` is absent, writes it — a one-line Python launcher pointing to `timesheet_setup.py` resolved from the MCP server's own path. The `setup_command` returned is always `python3 ~/.claude/timesheet-setup`.

**`validate_config()`** → `{valid, errors: [str]}`

Checks all required fields and formats in `~/.claude/timesheet.json`. Returns a list of error strings; empty list means valid.

**`read_messages(date: str)`** → `[{role, text, cwd, timestamp}]`

Reads Claude conversation logs for the given date (`YYYY-MM-DD`). Returns messages filtered and sorted by timestamp.

**`check_duplicate(date: str)`** → `{exists: bool}`

Queries ERPNext for an existing timesheet for the given date and employee.

**`submit_timesheet(date: str, entries: [{description, hours, activity_type, task?}])`** → `{success: bool, name: str}`

Creates and submits a timesheet document in ERPNext. Returns the timesheet name on success.

**`get_tasks(project: str)`** → `[{name, subject, status, exp_end_date}]`

Fetches all non-cancelled tasks for the project. Returns `exp_end_date` so the caller can identify overdue tasks.

**`create_task(subject, description, project, hours, date)`** → `{name: str, notes: [str]}`

Creates a task in ERPNext. Auto-extends project end date if ERPNext returns an `InvalidDates` error, then retries once. Returns the task name and any informational notes (e.g. "project end date extended to 2026-04-30").

---

## 2. Terminal Setup CLI

### Location

`skills/timesheet/scripts/timesheet_setup.py` — standalone interactive script, no command-line arguments. Invoked by the user in their own terminal via the launcher at `~/.claude/timesheet-setup`.

### Flow

1. Prompt `ERPNext URL:` (plain text input)
2. Prompt `Username:` (plain text input)
3. Prompt `Password:` (masked via `getpass.getpass`)
4. Attempt login and discovery; on failure show error and retry from step 1
5. Show identity confirmation: full name, employee ID, company — ask to confirm
6. Show discovered projects and activity types; prompt for defaults (project, activity type, working hours, start time, timezone)
7. Write `~/.claude/timesheet.json` with encrypted password
8. Print confirmation and exit

The setup wizard that currently lives in `SKILL.md` (the elaborate `--action discover` / `--action write-config` / `--pwd-file` bash orchestration) is removed entirely. Reconfigure = run the same script again.

---

## 3. SKILL.md v4

### Entry announcement

Skill announces itself on every invocation:
> "Using erpnext-timesheet to log work for TARGET_DATE..."

### Step 0 — Setup and Date Resolution

Resolve `TARGET_DATE` (same logic as v3).

Call `get_status`. Branch:

- **Not configured:** "To get started, run `python3 ~/.claude/timesheet-setup` in a new terminal, then come back and say done."
- **Configured:** "Logged in as user@company.com (https://erp.example.com) — shall I continue, or do you want to reconfigure?" If reconfigure: "Run `python3 ~/.claude/timesheet-setup` in a new terminal, then say done."

No wizard logic remains in SKILL.md.

### Step 1 — Validate Config

Call `validate_config` silently. On error: show errors, stop.

### Step 2 — Read Work Context

Progress message: "Reading work context for TARGET_DATE..."

Call `read_messages(date)`. Data source flexibility unchanged: if the user specifies a different source (git log, manual description, etc.), use that instead.

### Step 3 — Synthesize + Fetch Tasks

Progress message: "Summarizing work done..."

Synthesize task entries from messages as in v3. Then immediately call `get_tasks(project)` to fetch existing project tasks.

Identify overdue tasks: those with `exp_end_date < TARGET_DATE` and status not Completed.

Auto-match each synthesized entry to the most relevant existing task based on description similarity. Entries that represent genuinely new work get no task suggestion (will use `create_task` if user confirms).

### Step 4 — Draft Review (conversational)

Present overdue tasks first if any:
> "You have N overdue task(s): [task list]. I've suggested task assignments in the draft below."

Present the draft:
```
Draft timesheet for TARGET_DATE (Xh total):
──────────────────────────────────────────
1. [Xh] Description of entry one     → TASK-XXXX (suggested)
2. [Xh] Description of entry two     → no task
──────────────────────────────────────────
```

Close with a natural prompt:
> "Ready to submit, or would you like to make changes? You can edit, delete, or add an entry, reassign or create a task, redistribute hours, or I can submit as-is."

Handle responses conversationally. No bracket shortcuts. Since tasks are already fetched, task list is in context — no additional MCP call needed unless the user asks to create a new task (calls `create_task`).

When the user approves, proceed to Step 5.

### Step 5 — Duplicate Check + Submit

Check duplicate: call `check_duplicate(date)` silently. If exists: "A timesheet already exists for TARGET_DATE. Submit anyway?"

Progress message: "Submitting timesheet..."

Call `submit_timesheet(date, entries)`. On success: "Timesheet submitted. Reference: TS-XXXX." On failure: show error, ask if user wants to retry (max 3 attempts).

---

## 4. Testing

### Existing tests (keep, adapt paths)

- `tests/test_erpnext_client.py` — `ERPNextClient` and `build_timesheet_doc` logic is unchanged, moved into `mcp_server.py`. Tests adapted to import from new location.
- `tests/test_parse_logs.py` — `parse_content_blocks`, `validate_config`, `get_today_messages` logic unchanged. Tests adapted to import from new location.

### New tests

`tests/test_mcp_server.py` covers each tool function (not the MCP protocol layer):

- `get_status` with config present and missing
- `get_status` writes launcher to `~/.claude/timesheet-setup` when absent
- `validate_config` valid and invalid cases
- `check_duplicate` true and false
- `submit_timesheet` success path
- `get_tasks` returns correct fields including `exp_end_date`
- Overdue detection: tasks where `exp_end_date < target_date` are identifiable from the returned data
- `create_task` success and auto-extend project end date path

### Not tested

- `timesheet_setup.py` — interactive CLI with `getpass`; underlying discovery logic covered via `ERPNextClient` tests
- MCP protocol wiring — handled by the `mcp` library

---

## 5. Files Changed

| Action | Path |
|--------|------|
| Modified | `.claude-plugin/plugin.json` |
| Modified | `pyproject.toml` |
| Added | `skills/timesheet/mcp_server.py` |
| Added | `skills/timesheet/scripts/timesheet_setup.py` |
| Modified | `skills/timesheet/SKILL.md` |
| Modified | `tests/test_erpnext_client.py` |
| Modified | `tests/test_parse_logs.py` |
| Added | `tests/test_mcp_server.py` |
| Deleted | `skills/timesheet/scripts/setup.py` |
| Deleted | `skills/timesheet/scripts/parse_logs.py` |
| Deleted | `skills/timesheet/scripts/erpnext_client.py` |
| Deleted | `skills/timesheet/scripts/task_manager.py` |
