# ERPNext Timesheet v2 — Design Spec

## Overview

Extends the existing timesheet skill with three improvements learned from the first live run:

1. **Task field support** — ERPNext instances may require a `task` on every timesheet row. The TUI now lets users assign existing tasks or create new ones per entry.
2. **Hours override** — a `[h]` menu option re-distributes hours for days where you worked more or less than configured.
3. **More interactive setup** — identity confirmation after login, per-field confirmation with defaults, and a final summary before saving.

---

## Architecture

No changes to `parse_logs.py` or the config schema. `full_name` returned by `discover()` is used only during the setup wizard interaction — it is **not** written to `~/.claude/timesheet.json`.

### New file: `scripts/task_manager.py`

Handles all task and project operations. Three CLI actions:

- `get-tasks` — fetch open tasks for a project
- `create-task` — create a task from a JSON file; auto-extend project end date if needed
- `extend-project` — update a project's expected end date

### Modified: `scripts/setup.py`

`discover()` returns one additional field: `full_name` (the logged-in user's full name from ERPNext). All other fields unchanged.

### Modified: `scripts/erpnext_client.py`

`build_timesheet_doc()` accepts an optional `task` key per entry and passes it through to the `time_logs` row. No other changes.

### Modified: `skills/timesheet/timesheet.md`

Step 0 (setup wizard), Step 5 (TUI), and Step 6 (submit entries format) updated as described below. No other steps change.

---

## Setup Wizard (Step 0)

After successful login, before asking any settings questions, the skill reads `full_name`, `employee`, and `company` from the `discover()` JSON output and displays the identity block. `username` (the login email entered earlier by the user) is not part of `discover()` — the skill retains it from the user's earlier input:

```
Logged in as: <full_name>
Employee:     <employee>
Company:      <company>

Is this the right account? [y/n]
```

If `n`, re-ask for URL, username, and password from the start, then re-run `discover()`.

Then present each setting with the discovered or default value in brackets. Pressing Enter accepts the default; typing a value overrides it:

```
Default project [<discovered or first project>]:
Default activity type [<discovered or first activity type>]:
Work hours per day [8]:
Workday start time [09:00]:
Timezone [<system timezone>]:
```

If `projects_truncated` or `activity_types_truncated` is set, note that the list may be incomplete and the user can type a name manually.

Before writing the config, show a summary and ask for confirmation. `username` comes from the user's earlier input; all other values from discovery or user responses:

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

If `n`, restart from the beginning (re-ask URL, username, password).

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

`[+]` does not include a task field inline — add the entry first, then use `[t]` to assign a task to it. This is intentional.

### `[h] Change hours for today`

Prompts: `New total hours [<current>]:`

Re-distributes hours evenly across **all current entries** (including any added via `[+]` or previously edited via `[e]`). Modifies `hours` in-place on each entry object. The user's input is parsed as a float and rounded to 1 decimal before redistribution. Formula: `per_entry = round(total / count, 1)`; the last entry is set to `round(total - sum(all other entries), 1)` to ensure the total is exact to 1 decimal place. If `[h]` is invoked again later, it re-distributes from scratch across all entries at that point.

If the new total differs from `work_hours` in config, show: `Note: total is Xh (configured default is Yh).` — informational only, does not block submission.

### `[t] Assign task to an entry`

1. Ask: `Which entry number?`
2. Run `get-tasks` for `config["project"]`. Task lookup is always scoped to the single configured project — this is intentional in v1 (no per-entry project overrides). Display the list:

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
   `project` is always `config["project"]`. Hours and dates (today) are set automatically from the entry's **current hours at the moment `[n]` is selected** — not the originally synthesised hours. Not shown to the user.

   Write a temp file with `{subject, description, project, hours, date}` and run `create-task --task-file <path>`.

   The script outputs zero or more note lines (e.g. `Note: project end date extended to YYYY-MM-DD`) followed by the JSON result as the last line. The skill prints any note lines to the user, then parses the final line as JSON to extract the task name.

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

Perform checks in this order before proceeding to Step 6:

1. **Task warning** — if any entry has `[no task]`, warn:
   `Warning: X entries have no task assigned. Your ERPNext instance may require a task on each row. Continue? [y/n]`
   If `n`, re-display TUI.

2. **Hours mismatch warning** (existing behaviour) — if total hours ≠ `work_hours` in config:
   `Warning: total hours = Xh (expected Yh). Submit anyway? [y/n]`
   If `n`, re-display TUI.

Both checks apply every time `[a]` is selected — not only after a failed submission.

### Step 6 — entries format update

The entries JSON written to the temp file includes `task` where assigned:

```json
[
  {"description": "...", "hours": 4.0, "activity_type": "Development", "task": "TASK-2026-01052"},
  {"description": "...", "hours": 4.0, "activity_type": "Development"}
]
```

Entries with no task assigned omit the `task` key entirely (do not send `null` or `""`).

The updated note in `timesheet.md` Step 6: "Each entry in the JSON array must have keys: `description`, `hours`, `activity_type`. Entries with a task assigned also include `task`."

---

## `task_manager.py`

### `get-tasks`

```bash
python3 task_manager.py --config ~/.claude/timesheet.json \
  --action get-tasks --project <project>
```

- GET `/api/resource/Task` with `params={"filters": json.dumps([...]), "fields": json.dumps(["name", "subject", "status"])}`
- Filtered by `project = <project>` and `status != Cancelled` — returns all non-cancelled tasks (including Completed, Overdue, Open, etc.)
- Returns JSON array: `[{"name": "TASK-...", "subject": "...", "status": "..."}, ...]`
- Returns `[]` if no tasks found
- Exits non-zero on HTTP error

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
- If creation returns HTTP 417 and the response body contains `"exc_type": "InvalidDates"`:
  - Compute the last calendar day of the month following today's month (e.g. today = 2026-03-24 → 2026-04-30; today = 2026-01-31 → 2026-02-28)
  - Call `extend-project` on `config["project"]` with that date
  - Retry `create-task` once
- If auto-extend succeeds, print to stdout before the JSON result: `Note: project end date extended to YYYY-MM-DD`
- JSON result (last line of stdout): `{"name": "TASK-..."}`
- Exits non-zero on any unrecoverable error (including retry failure)

### `extend-project`

```bash
python3 task_manager.py --config ~/.claude/timesheet.json \
  --action extend-project --project <project> --date YYYY-MM-DD
```

- PUT `/api/resource/Project/<project>` with `json={"expected_end_date": "<date>"}`
- Returns `{"success": true}`
- Exits non-zero on failure

---

## `erpnext_client.py` change

`build_timesheet_doc()`: if an entry dict contains a `"task"` key with a non-empty string value, include it in the time log row. If the key is absent or its value is an empty string, omit it. No other changes.

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

Fetch `full_name` via GET `/api/resource/User/<percent-encoded-username>` (use `urllib.parse.quote(username, safe="")` to encode the email address in the path) with `params={"fields": json.dumps(["full_name"])}`. Use `.get()` to extract the value: `response.json().get("data", {}).get("full_name")`. Fall back to `username` if the call raises any `requests` exception (connection error or HTTP error) or if `full_name` is `None` / absent in the response. `full_name` is returned in the dict but is **not** written to `timesheet.json`.

---

## Tests

Skill-level TUI interaction tests are out of scope — the skill is a prompt, not executable code. Untested branches acknowledged: `[s]` skip path, `[a]` warn-on-no-task path, task creation note surfacing. These are verified by manual end-to-end runs.

### `tests/test_task_manager.py` (new)

- `get_tasks()`: returns task list; returns `[]` on empty result; exits non-zero on HTTP error
- `create_task()`: success path returns task name; auto-extends project when HTTP 417 response body contains `"exc_type": "InvalidDates"` then retries; prints note line before JSON on auto-extend; exits non-zero on unrecoverable error (second attempt also fails)
- `extend_project_end_date()`: success path returns `{"success": true}`; exits non-zero on HTTP error

### `tests/test_setup.py` (update)

- `discover()` return includes `full_name` field — update the existing `test_discover_returns_expected_shape` to mock the 4th GET call (User endpoint) in addition to the existing 3 mocks (employee, projects, activity types)
- `full_name` falls back to `username` when User GET raises `requests.HTTPError`
- `full_name` falls back to `username` when User GET response is missing the `full_name` field

### `tests/test_erpnext_client.py` (update)

- `build_timesheet_doc()` includes `task` field in time log row when entry has non-empty `task` key
- `build_timesheet_doc()` omits `task` field when entry has no `task` key
- `build_timesheet_doc()` omits `task` field when entry has empty string `task` key (`"task": ""`)

---

## Out of Scope

- Multi-project support per config
- Caching task lists between runs
- Editing task details after creation
- Any changes to `parse_logs.py`
- Persisting `full_name` to config
