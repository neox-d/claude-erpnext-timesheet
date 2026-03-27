# ERPNext Timesheet v4 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace 4 CLI Python scripts with a single MCP server, add a terminal setup CLI, and rewrite SKILL.md with a fully conversational interface and proactive task integration.

**Architecture:** A single MCP server (`mcp_server.py`) registered via `plugin.json` exposes 7 tools that cover all operational interactions. All business logic from the 4 existing CLI scripts moves into this file. A standalone setup CLI (`timesheet_setup.py`) handles first-run configuration in the user's own terminal. SKILL.md is rewritten to call MCP tools, hold TUI state conversationally, and show overdue tasks proactively.

**Tech Stack:** Python 3.11+, FastMCP (`mcp[cli]` package), `requests`, `cryptography` (Fernet), `zoneinfo`

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Modified | `pyproject.toml` | Add `mcp` dependency |
| Modified | `.claude-plugin/plugin.json` | Register MCP server, bump version to `2.0.0` |
| Added | `skills/timesheet/mcp_server.py` | MCP server entry point + all 7 tool functions + all migrated business logic (ERPNext client, log parser, task manager, config validator, discover) |
| Added | `skills/timesheet/scripts/timesheet_setup.py` | Interactive first-run setup CLI; imports `discover` and `write_config` from `mcp_server` |
| Modified | `skills/timesheet/SKILL.md` | Full v4 rewrite: MCP tool calls, conversational TUI, entry announcement |
| Modified | `tests/test_erpnext_client.py` | Update import: `from mcp_server import ERPNextClient, build_timesheet_doc` |
| Modified | `tests/test_parse_logs.py` | Update import: `from mcp_server import parse_content_blocks, validate_config, get_today_messages` |
| Added | `tests/test_mcp_server.py` | Tests for all 7 MCP tool functions and `get_status` launcher writing |
| Deleted | `skills/timesheet/scripts/setup.py` | Logic moved to `mcp_server.py` (`discover`, `write_config`) and `timesheet_setup.py` |
| Deleted | `skills/timesheet/scripts/parse_logs.py` | Logic moved to `mcp_server.py` |
| Deleted | `skills/timesheet/scripts/erpnext_client.py` | Logic moved to `mcp_server.py` |
| Deleted | `skills/timesheet/scripts/task_manager.py` | Logic moved to `mcp_server.py` |
| Unchanged | `skills/timesheet/scripts/crypto.py` | Imported by `mcp_server.py` as `from scripts.crypto import ...` |
| Unchanged | `skills/timesheet/scripts/__init__.py` | Keeps `scripts` importable as a package |

---

## Task 1: Update project config files

**Files:**
- Modify: `pyproject.toml`
- Modify: `.claude-plugin/plugin.json`

No tests needed for config-only changes.

- [ ] **Step 1: Add `mcp` to pyproject.toml dependencies**

  In `pyproject.toml`, add `mcp[cli]>=1.0` to the `dependencies` list (alongside `requests` and `cryptography`).

- [ ] **Step 2: Register MCP server in plugin.json**

  Add a top-level `mcpServers` object to `.claude-plugin/plugin.json`. The key is `"erpnext-timesheet"`, with `command` set to `"python3"` and `args` set to a single-element array containing `"${CLAUDE_PLUGIN_ROOT}/skills/timesheet/mcp_server.py"`.

- [ ] **Step 3: Commit**

  Commit both files with message: `chore: add mcp dependency and register MCP server`

---

## Task 2: Create mcp_server.py — migrate all business logic

**Files:**
- Create: `skills/timesheet/mcp_server.py`
- Modify: `tests/test_erpnext_client.py` (import line only)
- Modify: `tests/test_parse_logs.py` (import line only)

This task moves all library logic from the 4 CLI scripts into `mcp_server.py`. No MCP tool registration yet — just the underlying functions. The existing test suites must pass with updated import paths.

- [ ] **Step 1: Create mcp_server.py with path bootstrap**

  Create `skills/timesheet/mcp_server.py`. The first two executable lines must add the file's own parent directory to `sys.path` so that `scripts.crypto` is importable at runtime: insert `str(Path(__file__).parent)` at position 0 of `sys.path`. Import `Path` from `pathlib` before this.

- [ ] **Step 2: Copy ERPNext client logic**

  Copy the `ERPNextClient` class and `build_timesheet_doc` function verbatim from `scripts/erpnext_client.py` into `mcp_server.py`. Copy all their imports (`requests`, `json`, `datetime`, `timedelta`, `decrypt_password`). Do not copy `main()` or `argparse` setup.

- [ ] **Step 3: Copy log-parsing logic**

  Copy `parse_content_blocks`, `validate_config`, `get_timezone`, and `get_today_messages` verbatim from `scripts/parse_logs.py` into `mcp_server.py`. Copy their imports (`re`, `date`, `datetime`, `ZoneInfo`). Do not copy `load_config`, `main()`, or `argparse` setup.

- [ ] **Step 4: Copy task-management logic**

  Copy `_login`, `get_tasks` (the function that returns a list), `_next_month_end`, `_extend_project`, `extend_project_end_date`, and `create_task` verbatim from `scripts/task_manager.py` into `mcp_server.py`. Copy their imports (`calendar`, `date`). Do not copy `main()` or `argparse` setup. Add `"exp_end_date"` to the `fields` list in `get_tasks` (it currently only fetches `name`, `subject`, `status`).

- [ ] **Step 5: Copy discover and write_config**

  Copy `discover` and `write_config` verbatim from `scripts/setup.py` into `mcp_server.py`. Copy their imports (`stat`, `tempfile`, `quote`, `encrypt_password`). Do not copy `main()` or `argparse` setup.

- [ ] **Step 6: Update test imports**

  In `tests/test_erpnext_client.py`, change the import line from `from scripts.erpnext_client import ERPNextClient, build_timesheet_doc` to `from mcp_server import ERPNextClient, build_timesheet_doc`.

  In `tests/test_parse_logs.py`, change the import block from `from scripts.parse_logs import (parse_content_blocks, validate_config, get_today_messages,)` to `from mcp_server import parse_content_blocks, validate_config, get_today_messages`.

- [ ] **Step 7: Run existing tests**

  Run: `pytest tests/test_erpnext_client.py tests/test_parse_logs.py -v`

  Expected: all tests pass. Fix any import errors before proceeding.

- [ ] **Step 8: Commit**

  Commit `mcp_server.py`, `test_erpnext_client.py`, and `test_parse_logs.py` with message: `refactor: migrate business logic to mcp_server.py`

---

## Task 3: MCP tool — get_status

**Files:**
- Modify: `skills/timesheet/mcp_server.py`
- Create: `tests/test_mcp_server.py`

The `get_status` tool reads `~/.claude/timesheet.json` and writes a launcher to `~/.claude/timesheet-setup` whenever that file is absent.

- [ ] **Step 1: Write failing tests**

  Create `tests/test_mcp_server.py`. Write four tests for `get_status`:

  - `test_get_status_not_configured`: monkeypatch `Path.home` to a `tmp_path` that has no `timesheet.json`. Call `get_status()`. Assert result has `configured=False`, `setup_command="python3 ~/.claude/timesheet-setup"`. Assert `username` and `url` keys are absent or `None`.

  - `test_get_status_configured`: monkeypatch `Path.home` to a `tmp_path`. Write a valid `timesheet.json` containing `url`, `username`, and other required keys. Call `get_status()`. Assert `configured=True`, `username` matches, `url` matches.

  - `test_get_status_writes_launcher_when_absent`: monkeypatch `Path.home` to a `tmp_path` with a valid `timesheet.json`. Confirm `~/.claude/timesheet-setup` does not exist in `tmp_path`. Call `get_status()`. Assert that `tmp_path / ".claude" / "timesheet-setup"` now exists and is a file.

  - `test_get_status_launcher_content_runs_setup_script`: same setup as above. After calling `get_status()`, read the launcher file content. Assert it contains the absolute path to `timesheet_setup.py` (i.e., the string `"timesheet_setup.py"` appears in the content).

- [ ] **Step 2: Run tests to verify they fail**

  Run: `pytest tests/test_mcp_server.py -v`

  Expected: `ImportError` or `AttributeError` — `get_status` not yet defined.

- [ ] **Step 3: Add FastMCP app and implement get_status**

  Near the top of `mcp_server.py` (after imports), add: `from mcp.server.fastmcp import FastMCP` and `mcp = FastMCP("erpnext-timesheet")`.

  Define the `get_status` function decorated with `@mcp.tool()`. All paths are computed inside the function body (not as module-level constants) so tests can monkeypatch `Path.home`. Its logic:
  1. `config_path = Path.home() / ".claude" / "timesheet.json"`.
  2. `launcher_path = Path.home() / ".claude" / "timesheet-setup"`.
  3. Compute `setup_script = Path(__file__).parent / "scripts" / "timesheet_setup.py"`.
  4. If `launcher_path` does not exist: write a Python script to `launcher_path` whose content is a shebang line (`#!/usr/bin/env python3`) followed by an import of `runpy` and a call to `runpy.run_path` with the absolute string of `setup_script` and `run_name="__main__"`. Make the file executable via `os.chmod` with `stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH`.
  5. If `config_path` does not exist: return `{"configured": False, "setup_command": "python3 ~/.claude/timesheet-setup"}`.
  6. Read and parse the config JSON. Return `{"configured": True, "username": config.get("username"), "url": config.get("url"), "work_hours": config.get("work_hours", 8), "project": config.get("project"), "default_activity": config.get("default_activity"), "setup_command": "python3 ~/.claude/timesheet-setup"}`.

- [ ] **Step 4: Run tests**

  Run: `pytest tests/test_mcp_server.py -v`

  Expected: all 4 tests pass.

- [ ] **Step 5: Commit**

  Commit `mcp_server.py` and `tests/test_mcp_server.py` with message: `feat: add MCP server skeleton and get_status tool`

---

## Task 4: MCP tools — validate_config and read_messages

**Files:**
- Modify: `skills/timesheet/mcp_server.py`
- Modify: `tests/test_mcp_server.py`

- [ ] **Step 1: Write failing tests**

  In `tests/test_mcp_server.py`, add:

  For `validate_config`:
  - `test_validate_config_valid`: monkeypatch `Path.home` to a `tmp_path` containing a valid `timesheet.json`. Call `validate_config()`. Assert `{"valid": True, "errors": []}`.
  - `test_validate_config_missing_field`: write a config missing the `employee` field. Call `validate_config()`. Assert `valid=False` and `errors` list contains a string mentioning `"employee"`.
  - `test_validate_config_no_config_file`: `tmp_path` has no `timesheet.json`. Call `validate_config()`. Assert `valid=False` and `errors` list is non-empty.

  For `read_messages`:
  - `test_read_messages_returns_list`: monkeypatch `Path.home` to a `tmp_path` with no projects dir. Call `read_messages("2026-03-27")`. Assert result is an empty list (no messages for an empty projects dir).

- [ ] **Step 2: Run tests to verify they fail**

  Run: `pytest tests/test_mcp_server.py::test_validate_config_valid tests/test_mcp_server.py::test_validate_config_missing_field tests/test_mcp_server.py::test_validate_config_no_config_file tests/test_mcp_server.py::test_read_messages_returns_list -v`

  Expected: all fail with `NameError` or `AttributeError`.

- [ ] **Step 3: Implement validate_config tool**

  Add a `validate_config` function decorated with `@mcp.tool()`. Logic:
  1. Config path = `Path.home() / ".claude" / "timesheet.json"`.
  2. If file does not exist: return `{"valid": False, "errors": ["Config file not found. Run python3 ~/.claude/timesheet-setup to set up."]}`.
  3. Parse the JSON. Call the existing `validate_config(config)` helper (the plain function, not the tool — rename one of them to avoid collision: rename the plain helper to `_validate_config_fields` and update all references including in `test_parse_logs.py`).
  4. Return `{"valid": True, "errors": []}` if no errors, else `{"valid": False, "errors": errors}`.

- [ ] **Step 4: Implement read_messages tool**

  Add a `read_messages` function decorated with `@mcp.tool()` taking a `date` string parameter. Logic:
  1. Load config from `Path.home() / ".claude" / "timesheet.json"`.
  2. Get timezone via `get_timezone(config)`.
  3. Call `get_today_messages(tz=tz, target_date=date_cls.fromisoformat(date))` where `date_cls` is the `date` class imported from `datetime` (rename the parameter to avoid shadowing: use `date_str` as the parameter name).
  4. Return the list.

- [ ] **Step 5: Fix validate_config naming collision**

  The plain helper function from `parse_logs.py` is named `validate_config`. The MCP tool is also named `validate_config`. Rename the plain helper to `_validate_config_fields` everywhere it is used: inside `mcp_server.py` itself, and update `tests/test_parse_logs.py` to import `_validate_config_fields` instead of `validate_config` (and rename test function references accordingly).

- [ ] **Step 6: Run all tests**

  Run: `pytest tests/ -v`

  Expected: all tests pass.

- [ ] **Step 7: Commit**

  Commit with message: `feat: add validate_config and read_messages MCP tools`

---

## Task 5: MCP tools — check_duplicate and submit_timesheet

**Files:**
- Modify: `skills/timesheet/mcp_server.py`
- Modify: `tests/test_mcp_server.py`

- [ ] **Step 1: Write failing tests**

  Add a helper `make_config_file(tmp_path)` to `test_mcp_server.py` that writes a valid `timesheet.json` with `url`, `username`, `password` (use a plaintext value — `ERPNextClient` accepts plaintext via the `decrypt_password` passthrough), `employee`, `company`, `project`, `default_activity`, `work_hours`, and `start_time`.

  For `check_duplicate`:
  - `test_check_duplicate_exists`: monkeypatch `Path.home`. Write config. Patch `ERPNextClient.login` to no-op and `ERPNextClient.check_duplicate` to return `True`. Call `check_duplicate("2026-03-27")`. Assert `{"exists": True}`.
  - `test_check_duplicate_not_exists`: same but `check_duplicate` returns `False`. Assert `{"exists": False}`.

  For `submit_timesheet`:
  - `test_submit_timesheet_success`: monkeypatch `Path.home`. Write config. Patch `ERPNextClient.login`, `ERPNextClient.create_timesheet` to return `"TS-0001"`, and `ERPNextClient.submit_timesheet` to no-op. Call `submit_timesheet("2026-03-27", [{"description": "Work", "hours": 8.0, "activity_type": "Development"}])`. Assert `{"success": True, "name": "TS-0001"}`.

- [ ] **Step 2: Run to verify failure**

  Run: `pytest tests/test_mcp_server.py -k "check_duplicate or submit_timesheet" -v`

  Expected: all fail.

- [ ] **Step 3: Implement check_duplicate tool**

  Add `check_duplicate` decorated with `@mcp.tool()` taking `date_str: str`. Logic: load config, decrypt password, construct `ERPNextClient`, call `client.check_duplicate(config["employee"], date_str)`, return `{"exists": result}`.

- [ ] **Step 4: Implement submit_timesheet tool**

  Add `submit_timesheet` decorated with `@mcp.tool()` taking `date_str: str` and `entries: list`. Logic: load config, decrypt password, construct `ERPNextClient`, call `build_timesheet_doc(config, entries, date_str=date_str)`, call `client.create_timesheet(doc)` to get `name`, call `client.submit_timesheet(name)`, return `{"success": True, "name": name}`.

- [ ] **Step 5: Run all tests**

  Run: `pytest tests/ -v`

  Expected: all pass.

- [ ] **Step 6: Commit**

  Commit with message: `feat: add check_duplicate and submit_timesheet MCP tools`

---

## Task 6: MCP tools — get_tasks and create_task

**Files:**
- Modify: `skills/timesheet/mcp_server.py`
- Modify: `tests/test_mcp_server.py`

- [ ] **Step 1: Write failing tests**

  For `get_tasks`:
  - `test_get_tasks_returns_tasks_with_exp_end_date`: monkeypatch `Path.home`, write config, patch `requests.Session.post` (login) to return 200 and `requests.Session.get` to return a response with `{"data": [{"name": "TASK-001", "subject": "Fix bug", "status": "Open", "exp_end_date": "2026-03-20"}]}`. Call `get_tasks("PROJ-001")`. Assert result is a list of length 1 with the task having `exp_end_date` key.
  - `test_get_tasks_empty_project`: same but response data is empty list. Assert result is `[]`.

  For `create_task`:
  - `test_create_task_success`: monkeypatch `Path.home`, write config, patch login and `requests.Session.request` for POST to return `{"data": {"name": "TASK-002"}}` with status 201. Call `create_task("Fix bug", "Detailed description", "PROJ-001", 4.0, "2026-03-27")`. Assert `{"name": "TASK-002", "notes": []}`.
  - `test_create_task_extends_project_on_invalid_dates`: patch the POST to first return a 417 response with `{"exc_type": "InvalidDates"}`, then patch the PUT (project extend) to succeed, then patch the retry POST to return `{"data": {"name": "TASK-003"}}`. Call `create_task(...)`. Assert `name == "TASK-003"` and `notes` contains a string mentioning `"extended"`.

- [ ] **Step 2: Run to verify failure**

  Run: `pytest tests/test_mcp_server.py -k "get_tasks or create_task" -v`

  Expected: all fail.

- [ ] **Step 3: Implement get_tasks tool**

  Add `get_tasks` decorated with `@mcp.tool()` taking `project: str`. Logic: load config, call `_login(config)` to get a session, call the existing `get_tasks(config, project)` helper (rename the existing plain helper to `_get_tasks_from_erpnext` to avoid collision with the tool — update all internal references). Return the list.

  The `_get_tasks_from_erpnext` function must fetch `["name", "subject", "status", "exp_end_date"]` — ensure `"exp_end_date"` is in the fields list (add it if not already present from Task 2 Step 4).

- [ ] **Step 4: Implement create_task tool**

  Add `create_task` decorated with `@mcp.tool()` taking `subject: str`, `description: str`, `project: str`, `hours: float`, `date_str: str`. Logic: load config, call the existing `create_task(config, task_input)` helper (rename to `_create_task_in_erpnext` to avoid collision). Build `task_input = {"subject": subject, "description": description, "project": project, "hours": hours, "date": date_str}`. Return `{"name": name, "notes": notes}`.

- [ ] **Step 5: Run all tests**

  Run: `pytest tests/ -v`

  Expected: all pass.

- [ ] **Step 6: Add MCP entry point**

  At the very bottom of `mcp_server.py`, add the standard entry point: `if __name__ == "__main__": mcp.run()`.

- [ ] **Step 7: Commit**

  Commit with message: `feat: add get_tasks and create_task MCP tools`

---

## Task 7: Delete old CLI scripts and verify

**Files:**
- Delete: `skills/timesheet/scripts/setup.py`
- Delete: `skills/timesheet/scripts/parse_logs.py`
- Delete: `skills/timesheet/scripts/erpnext_client.py`
- Delete: `skills/timesheet/scripts/task_manager.py`

- [ ] **Step 1: Delete the four files**

  Remove `skills/timesheet/scripts/setup.py`, `skills/timesheet/scripts/parse_logs.py`, `skills/timesheet/scripts/erpnext_client.py`, and `skills/timesheet/scripts/task_manager.py`.

- [ ] **Step 2: Run full test suite**

  Run: `pytest tests/ -v`

  Expected: all tests pass. If any test imports from the deleted files, fix the import.

- [ ] **Step 3: Commit**

  Commit with message: `refactor: delete old CLI scripts replaced by mcp_server.py`

---

## Task 8: Create timesheet_setup.py

**Files:**
- Create: `skills/timesheet/scripts/timesheet_setup.py`

No automated tests — interactive `getpass` CLI. The `discover` function it calls is covered by existing `ERPNextClient` tests.

- [ ] **Step 1: Create timesheet_setup.py**

  Create `skills/timesheet/scripts/timesheet_setup.py`. It must:

  1. Add `str(Path(__file__).parent.parent)` to `sys.path` at position 0 so it can import from `mcp_server`.
  2. Import `discover`, `write_config`, and `encrypt_password` from `mcp_server` (and `from scripts.crypto import encrypt_password`).
  3. Import `getpass`, `json`, `sys`, `Path`, `ZoneInfo`, and `subprocess` to get the system timezone via `timedatectl`.
  4. Define a `main()` function with this flow:
     - Loop: prompt `ERPNext URL: ` (via `input()`), prompt `Username: ` (via `input()`), prompt `Password: ` (via `getpass.getpass()`).
     - Call `discover(url, username, password)`. On `requests.HTTPError` or `ValueError`, print the error and `continue` the loop. On `ConnectionError` or `Timeout`, print connection error and `continue`.
     - Print identity block: full name, employee, company. Ask `Is this the right account? (y/n): ` via `input()`. If `n`, `continue`.
     - Print available projects (numbered list). If `projects_truncated` in result, note it. Prompt `Default project [<first>]: ` — accept blank to use the first.
     - Print available activity types (numbered list). If `activity_types_truncated`, note it. Prompt `Default activity type [<first>]: `.
     - Prompt `Working hours per day [8]: ` — accept blank for 8.
     - Prompt `Workday start time [09:00]: ` — accept blank for `09:00`.
     - Get system timezone: run `timedatectl show --property=Timezone --value` via `subprocess.check_output`. Fall back to `UTC` on error. Prompt `Timezone [<detected>]: ` — accept blank for detected.
     - Build the config dict with keys: `url`, `username`, `employee`, `company`, `project`, `default_activity`, `work_hours` (as float), `start_time`, `timezone`. Set `password` to `encrypt_password(password)`.
     - Call `write_config(config, str(Path.home() / ".claude" / "timesheet.json"))`.
     - Print `Config saved to ~/.claude/timesheet.json` and break.
  5. Call `main()` in `if __name__ == "__main__"` block.

- [ ] **Step 2: Manual smoke test**

  Run `python3 skills/timesheet/scripts/timesheet_setup.py` in a real terminal (not via Claude Code bash tool — `getpass` requires a real TTY). Verify it prompts for URL, username, and masked password, confirms identity, prompts for defaults, and writes the config.

- [ ] **Step 3: Commit**

  Commit with message: `feat: add interactive terminal setup CLI`

---

## Task 9: Rewrite SKILL.md and bump version

**Files:**
- Modify: `skills/timesheet/SKILL.md`
- Modify: `.claude-plugin/plugin.json`

- [ ] **Step 1: Rewrite SKILL.md**

  Replace the entire content of `skills/timesheet/SKILL.md` with the v4 spec. Key structural changes from v1.2.0:

  **Frontmatter:** bump `version` to `2.0.0`. Update `description` to mention MCP.

  **Step 0 — Setup and Date Resolution:**
  - Resolve `TARGET_DATE` from the invocation message exactly as in v1.2.0 (same date parsing logic: look for past-date phrases like "for yesterday", "for 2026-03-24", "last Friday"; otherwise use today's date in `YYYY-MM-DD` format).
  - Immediately tell the user: "Using erpnext-timesheet to log work for TARGET_DATE..." (announcement comes after date resolution, as part of Step 0).
  - Call the `get_status` MCP tool (no bash commands).
  - If `configured` is `false`: tell the user "To get started, run `python3 ~/.claude/timesheet-setup` in a new terminal, then come back and say done." Wait for the user to say done, then call `get_status` again and proceed if now configured.
  - If `configured` is `true`: tell the user "Logged in as `<username>` (`<url>`) — shall I continue, or do you want to reconfigure?" If the user wants to reconfigure: "Run `python3 ~/.claude/timesheet-setup` in a new terminal, then say done." Wait and recheck. If continuing: proceed to Step 1.
  - No setup wizard. No bash. No elaborate questions.

  **Step 1 — Validate Config:**
  - Call `validate_config` MCP tool silently.
  - If `valid` is `false`: print the errors list and stop.

  **Step 2 — Read Work Context:**
  - Tell the user: "Reading work context for TARGET_DATE..."
  - Call `read_messages(date=TARGET_DATE)` MCP tool.
  - If the user specified a different data source, use that instead (same flexibility as v1.2.0 — read git log, ask user to describe, etc.).
  - Use `work_hours` from the `get_status` response (it returns this field when configured — see Task 3).

  **Step 3 — Synthesize + Fetch Tasks:**
  - Tell the user: "Summarizing work done..."
  - Synthesize task entries from messages exactly as in v1.2.0 (same rules: max 8 tasks, group related messages, ignore meta-conversation, equal hour distribution with rounding absorbed by last entry).
  - Immediately call `get_tasks(project=<project from config>)` MCP tool.
  - Identify overdue tasks: entries in the returned list where `exp_end_date` is a non-empty string, `exp_end_date < TARGET_DATE` (date comparison), and `status` is not `"Completed"` and not `"Cancelled"`.
  - Auto-match each synthesized entry to the most relevant existing task by comparing the entry description to task subjects. If a good match exists, store it as a suggested assignment. If no good match, leave unassigned.

  **Step 4 — Draft Review:**
  - If overdue tasks found: tell the user "You have N overdue task(s): [list of name + subject + days overdue]. I've suggested task assignments in the draft below."
  - Display the draft in this exact format:
    ```
    Draft timesheet for TARGET_DATE (Xh total):
    ──────────────────────────────────────────
    1. [Xh] Entry description one        → TASK-XXXX (suggested)
    2. [Xh] Entry description two        → no task
    ──────────────────────────────────────────
    ```
  - Close with: "Ready to submit, or would you like to make changes? You can edit, delete, or add an entry, reassign or create a task, redistribute hours, or I can submit as-is."
  - Handle all edits, deletions, additions, and redistributions purely conversationally (no MCP calls). Claude holds the entry list in conversation state.
  - For task assignment: since the task list is already in context from Step 3, present the list conversationally and let the user pick by number or name. If the user asks to create a new task, call `create_task` MCP tool and assign the returned name. Print any notes from the response.
  - If the entry list is empty when user says submit: tell the user there are no entries and ask them to add some.
  - Hours mismatch: if total hours ≠ work_hours when user approves, note it conversationally and ask if they want to proceed.
  - When the user approves, proceed to Step 5.

  **Step 5 — Duplicate Check + Submit:**
  - Call `check_duplicate(date=TARGET_DATE)` MCP tool silently.
  - If exists: "A timesheet already exists for TARGET_DATE. Submit anyway?" If no, return to Step 4.
  - Tell the user: "Submitting timesheet..."
  - Call `submit_timesheet(date_str=TARGET_DATE, entries=<approved entries list>)` MCP tool. Each entry must include `description`, `hours`, `activity_type`. Include `task` key only for entries with a task assigned.
  - If success: "Timesheet submitted. Reference: TS-XXXX."
  - If failure: show the error, ask "Retry?" Maximum 3 total attempts.

- [ ] **Step 2: Bump version in plugin.json**

  Change `"version"` in `.claude-plugin/plugin.json` from `"1.2.0"` to `"2.0.0"`.

- [ ] **Step 3: Run full test suite one final time**

  Run: `pytest tests/ -v`

  Expected: all tests pass.

- [ ] **Step 4: Commit**

  Commit `SKILL.md` and `plugin.json` with message: `feat: v4 - conversational TUI, MCP server, setup CLI (v2.0.0)`
