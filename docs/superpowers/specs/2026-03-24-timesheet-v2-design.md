# ERPNext Timesheet v2 — Design Spec

## Overview

Extends the existing timesheet skill with three improvements learned from the first live run:

1. **Task field support** — ERPNext instances may require a `task` on every timesheet row. The TUI now lets users assign existing tasks or create new ones per entry.
2. **Hours override** — a `[h]` menu option re-distributes hours for days where you worked more or less than configured.
3. **More interactive setup** — identity confirmation after login, per-field confirmation with defaults, and a final summary before saving.

---

## Architecture

No changes to `parse_logs.py` or the config schema.

### New file: `scripts/task_manager.py`

Handles all task and project operations. Three CLI actions:

- `get-tasks` — fetch open tasks for a project
- `create-task` — create a task from a JSON file; auto-extend project end date if needed
- `extend-project` — update a project's expected end date

### Modified: `scripts/setup.py`

`discover()` returns one additional field: `full_name` (the logged-in user's full name from ERPNext).

### Modified: `scripts/erpnext_client.py`

`build_timesheet_doc()` accepts an optional `task` key per entry and passes it through to the `time_logs` row. No other changes.

### Modified: `skills/timesheet/timesheet.md`

Step 0 and Step 5 updated as described below.

---

## Setup Wizard (Step 0)

After successful login, before asking any settings questions, show an identity block and ask for confirmation:

```
Logged in as: <full_name>
Employee:     <employee>
Company:      <company>

Is this the right account? [y/n]
```

If `n`, re-ask for URL, username, and password, then re-run discovery.

Then present each setting with the discovered or default value in brackets. Pressing Enter accepts the default; typing a value overrides it:

```
Default project [<discovered or first project>]:
Default activity type [<discovered or first activity type>]:
Work hours per day [8]:
Workday start time [09:00]:
Timezone [<system timezone>]:
```

If `projects_truncated` or `activity_types_truncated` is set, note that the list may be incomplete and the user can type a name manually.

Before writing the config, show a summary and ask for confirmation:

```
About to save:
  URL:           <url>
  User:          <username>
  Employee:      <employee>
  Project:       <project>
  Activity type: <default_activity>
  Work hours:    <work_hours>
  Start time:    <start_time>
  Timezone:      <timezone>

Save to ~/.claude/timesheet.json? [y/n]
```

If `n`, restart the wizard from the beginning.

---

## Timesheet TUI (Step 5)

### Display format

Each entry line shows its assigned task:

```
Draft timesheet for YYYY-MM-DD (Xh total):
──────────────────────────────────────────
1. [Xh] Description of task one          [no task]
2. [Xh] Description of task two          [TASK-2026-01052]
──────────────────────────────────────────
```

### Menu

```
[a] Approve and submit
[e] Edit an entry
[d] Delete an entry
[+] Add an entry
[h] Change hours for today
[t] Assign task to an entry
[q] Quit without submitting
```

### `[h] Change hours for today`

Prompts: `New total hours [<current>]:`

Re-distributes hours evenly across all entries (hours per entry = total / count, rounded to 1 decimal; last entry absorbs remainder so sum equals total exactly).

If the new total differs from `work_hours` in config, show: `Note: total is Xh (configured default is Yh).` — informational only, does not block submission.

### `[t] Assign task to an entry`

1. Ask: `Which entry number?`
2. Run `get-tasks` for the configured project. Display the list:

```
Entry N: <description>

  Existing tasks in <project>:
  1. <subject> (<name>, <status>)
  2. ...
  [n] Create new task
  [s] Skip (no task)
  >
```

3. **Select existing** — assign the chosen task to the entry. Re-display TUI.

4. **`[n]` Create new task:**

   Show pre-filled values (user may edit or press Enter to accept):
   ```
   Subject [<entry description, truncated to 140 chars>]:
   Description [<full entry description>]:
   ```
   Hours and dates (today) are set automatically from the entry — not shown to the user.

   Run `create-task`. If the project end date is in the past, `task_manager.py` auto-extends it to the end of the following month and prints a warning line before the JSON result; the skill surfaces this to the user: `Note: project end date extended to <date>.`

   Assign the newly created task to the entry. Re-display TUI.

5. **`[s]` Skip** — entry remains `[no task]`. Re-display TUI.

### `[e] Edit an entry`

Existing behaviour, plus an optional task field:

```
Description [current]:
Hours [current]:
Activity type [current]:
Task [current or blank]:
```

If the user types a task ID directly it is assigned as-is. If left blank the task is cleared.

### `[a] Approve`

If any entry has `[no task]` and the previous submission attempt failed with a `MandatoryError` on `task`, warn:
`Warning: X entries have no task assigned. Your ERPNext instance may require tasks. Continue? [y/n]`

Otherwise proceed to Step 6 as before.

---

## `task_manager.py`

### `get-tasks`

```bash
python3 task_manager.py --config ~/.claude/timesheet.json \
  --action get-tasks --project <project>
```

- GET `/api/resource/Task` filtered by `project = <project>` and `status != Cancelled`
- Returns JSON array: `[{"name": "TASK-...", "subject": "...", "status": "..."}, ...]`
- Returns `[]` if no tasks found

### `create-task`

```bash
python3 task_manager.py --config ~/.claude/timesheet.json \
  --action create-task --task-file <path>
```

Input JSON (from file):
```json
{
  "subject": "...",
  "description": "...",
  "project": "PROJ-XXXX",
  "hours": 4.0,
  "date": "YYYY-MM-DD"
}
```

- Sets `expected_time = hours`, `exp_start_date = date`, `exp_end_date = date`, `custom_planned_completion_date = date`, `status = "Completed"`
- If creation fails with `InvalidDates` (project end date in the past): fetch project end date, compute end of the following month, call extend-project, retry create-task once
- On success, prints warning if end date was extended: `Note: project end date extended to YYYY-MM-DD`
- Returns JSON: `{"name": "TASK-..."}`
- Exits non-zero on any unrecoverable error

### `extend-project`

```bash
python3 task_manager.py --config ~/.claude/timesheet.json \
  --action extend-project --project <project> --date YYYY-MM-DD
```

- PUT `/api/resource/Project/<project>` with `{"expected_end_date": "<date>"}`
- Returns `{"success": true}`
- Exits non-zero on failure

---

## `erpnext_client.py` change

`build_timesheet_doc()`: if an entry dict contains a `"task"` key with a non-empty value, include it in the time log row. No other changes.

---

## `setup.py` change

`discover()` return dict gains one field:
```json
{
  "full_name": "Abhiraaj Chandrasekaran",
  "employee": "...",
  ...
}
```

Fetch from `/api/method/frappe.client.get_value` with `doctype=User, fieldname=full_name, filters={"name": <username>}`, or fall back to the username if the call fails.

---

## Tests

### `tests/test_task_manager.py` (new)

- `get_tasks()`: returns task list, handles empty result, handles HTTP error
- `create_task()`: success path, auto-extend on InvalidDates then retry, exits non-zero on unrecoverable error
- `extend_project_end_date()`: success path, exits non-zero on failure

### `tests/test_setup.py` (update)

- `discover()` return includes `full_name`
- `full_name` falls back to username if User fetch fails

### `tests/test_erpnext_client.py` (update)

- `build_timesheet_doc()` includes `task` field in time log row when entry has `task` key
- `build_timesheet_doc()` omits `task` field when entry has no `task` key

---

## Out of Scope

- Multi-project support per config
- Caching task lists between runs
- Editing task details after creation
- Any changes to `parse_logs.py`
