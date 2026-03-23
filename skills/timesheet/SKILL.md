---
name: timesheet
description: Use when the user wants to submit today's ERPNext timesheet, log work hours, or fill in a timesheet from conversation history
version: 1.0.0
---

# ERPNext Timesheet

Automate daily ERPNext timesheet filling from your Claude conversation history.

---

When this skill is invoked, follow these steps exactly. Do not skip steps.

## Step 0: First-Time Setup

Check if `~/.claude/timesheet.json` exists:
```bash
test -f ~/.claude/timesheet.json && echo "EXISTS" || echo "MISSING"
```

If `EXISTS`, skip to Step 1. If `MISSING`, run the interactive setup wizard:

### Setup Wizard

Tell the user:
```
Welcome! Let's connect to your ERPNext instance.
This will create ~/.claude/timesheet.json with your credentials and preferences.
Note: credentials are stored in plaintext — ensure your home directory is appropriately secured.
```

Ask the following questions one at a time:

1. **ERPNext URL** — e.g. `https://yourcompany.erpnext.com`
2. **Username** — your ERPNext login email
3. **Password**

Then test login and discover configuration:
```bash
python3 "$CLAUDE_PLUGIN_ROOT/scripts/setup.py" \
  --action discover \
  --url "<URL>" \
  --username "<USERNAME>" \
  --password "<PASSWORD>"
```

If the command fails, show the error and ask the user to correct their credentials. Re-ask steps 1–3.

If it succeeds, the output contains `employee`, `company`, `full_name`, `projects` (list), `activity_types` (list).

Show the identity confirmation block and ask:
```
Logged in as: <full_name>
Employee:     <employee>
Company:      <company>

Is this the right account? [y/n]
```

If `n`, re-ask steps 1–3 and re-run discover.

Then present each setting with the discovered or default value in brackets. The user presses Enter to accept, or types a new value to override:

```
Default project [<first project from discovered list>]:
Default activity type [<first activity type from discovered list>]:
Work hours per day [8]:
Workday start time [09:00]:
Timezone [<system timezone — run: timedatectl show --property=Timezone --value>]:
```

If the output shows `projects_truncated` or `activity_types_truncated`, note to the user that the list may be incomplete and they can type a name manually.

Before saving, show a summary and ask for confirmation:
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

If `y`, build the config JSON and write it:

Substitute `CONFIG_PLACEHOLDER` with the Python dict literal for the assembled config. This avoids passing credentials as shell arguments.

```bash
CONFIG_TMPFILE=$(mktemp /tmp/timesheet-setup-XXXXXX.json)
python3 -c "import json, sys; json.dump(CONFIG_PLACEHOLDER, open(sys.argv[1], 'w'))" "$CONFIG_TMPFILE"
python3 "$CLAUDE_PLUGIN_ROOT/scripts/setup.py" \
  --action write-config \
  --config-file "$CONFIG_TMPFILE" \
  --config-out ~/.claude/timesheet.json
rm -f "$CONFIG_TMPFILE"
```

Where `CONFIG_PLACEHOLDER` is the Python dict literal for:
```json
{
  "url": "<URL>",
  "username": "<USERNAME>",
  "password": "<PASSWORD>",
  "employee": "<discovered employee>",
  "company": "<discovered company>",
  "project": "<chosen project>",
  "default_activity": "<chosen activity type>",
  "work_hours": <work_hours>,
  "start_time": "<start_time>",
  "timezone": "<timezone>"
}
```

Tell the user: `Setup complete! Config saved to ~/.claude/timesheet.json`

Then continue to Step 1 (config validation) to confirm everything is in order.

## Step 1: Validate Config

Run:
```bash
python3 "$CLAUDE_PLUGIN_ROOT/scripts/parse_logs.py" --config ~/.claude/timesheet.json --validate-only
```

If the command exits non-zero or output is not `OK`, print the error and stop. Do not proceed.

## Step 2: Read Today's Conversations

Tell the user: `Reading today's Claude conversations...`

Run:
```bash
python3 "$CLAUDE_PLUGIN_ROOT/scripts/parse_logs.py" --config ~/.claude/timesheet.json
```

This returns a JSON array of messages `[{role, text, cwd, timestamp}]`. Store this as your context.

Parse `work_hours` from `~/.claude/timesheet.json` for use in Step 3 and Step 5.

## Step 3: Synthesize Task Entries

Tell the user: `Summarizing work done...`

From the conversation messages, identify distinct work themes. Create task entries where:
- **description**: short professional summary of the work, max 80 characters, no filler ("worked on", "helped with")
- **hours**: `work_hours / number_of_tasks`, rounded to 1 decimal. Last task absorbs rounding remainder so total equals work_hours exactly.
- **activity_type**: read `default_activity` from `~/.claude/timesheet.json`
- **task**: not set at synthesis time — assigned in Step 5 via `[t]`

Rules:
- Group closely related messages into one task (e.g. "fix bug" + "write test for fix" = one task)
- Ignore meta-conversation (greetings, "thanks", off-topic chat)
- Focus on deliverables: what was built, fixed, reviewed, or designed
- Minimum 1 task, maximum 8 tasks

If no messages were found, tell the user and skip to Step 5 with an empty list.

## Step 4: Check for Duplicate

Run:
```bash
python3 "$CLAUDE_PLUGIN_ROOT/scripts/erpnext_client.py" --config ~/.claude/timesheet.json --action check-duplicate
```

If the output contains `"exists": true`, ask:
`Warning: A timesheet already exists for today. Continue anyway? [y/n]`
If user answers `n`, stop.

## Step 5: Present Draft TUI

Read today's date. Read `project` from `~/.claude/timesheet.json`. Display:

```
Draft timesheet for YYYY-MM-DD (Xh total):
──────────────────────────────────────────
1. [Xh] Description of task one          [no task]
2. [Xh] Description of task two          [TASK-2026-01052]
...
──────────────────────────────────────────

[a] Approve and submit
[e] Edit an entry
[d] Delete an entry
[+] Add an entry (for work done outside Claude)
[h] Change hours for today
[t] Assign task to an entry
[q] Quit without submitting

>
```

Each entry shows its assigned task in brackets at the right: `[no task]` if none, or the task ID if assigned.

Handle the user's response:

### [a] Approve

If the entry list is empty, say: `No entries to submit. Use [+] to add entries first.` Re-display menu.

Otherwise, perform these checks in order:

1. **Task warning** — if any entry has no task assigned, warn:
   `Warning: X entries have no task assigned. Your ERPNext instance may require a task on each row. Continue? [y/n]`
   If `n`, re-display TUI.

2. **Hours mismatch warning** — if total hours ≠ work_hours:
   `Warning: total hours = Xh (expected Yh). Submit anyway? [y/n]`
   If `n`, re-display TUI. If `y` (or no mismatch), proceed to Step 6.

### [e] Edit

Ask: `Which entry number?`
For the chosen entry, prompt each field with its current value in brackets (press Enter to keep):
```
  Description [current value]:
  Hours [current value]:
  Activity type [current value]:
  Task [current task ID or blank to clear]:
```
After edit, check if total hours still equals work_hours. If not, show:
`Warning: total hours = Xh (expected Yh).`
This is informational only. Re-display TUI.

### [d] Delete

Ask: `Which entry number?`
Remove that entry. Re-display TUI.

### [+] Add entry

Prompt freehand (for work done outside Claude — meetings, calls, etc.):
```
  Description:
  Hours:
  Activity type [default_activity]:
```
Add to list with no task assigned. Use `[t]` to assign a task to it afterwards. Re-display TUI.

### [h] Change hours for today

Prompt: `New total hours [<current total>]:`

Parse the input as a float, round to 1 decimal. Re-distribute hours evenly across all current entries in-place:
- `per_entry = round(total / count, 1)`
- Last entry = `round(total - sum(all other entries), 1)`

Show: `Note: total is Xh (configured default is Yh).` if different from config work_hours — informational only.

Re-display TUI.

### [t] Assign task to an entry

Ask: `Which entry number?`

Fetch tasks from the configured project:
```bash
python3 "$CLAUDE_PLUGIN_ROOT/scripts/task_manager.py" \
  --config ~/.claude/timesheet.json \
  --action get-tasks \
  --project "<project from config>"
```

Display the list:
```
Entry N: <description>

  Existing tasks in <project>:
  1. <subject> (<name>, <status>)
  2. ...
  [n] Create new task
  [s] Skip (no task)
  >
```

**Select a number** — assign that task to the entry. Re-display TUI.

**`[s]` Skip** — entry remains `[no task]`. Re-display TUI.

**`[n]` Create new task:**

Show pre-filled subject and description. User presses Enter to accept or types a new value:
```
  Subject [<entry description, max 140 chars>]:
  Description [<full entry description>]:
```

Write a temp file and run create-task:
```bash
TASK_FILE=$(mktemp /tmp/timesheet-task-XXXXXX.json)
python3 -c "import json, sys; json.dump(TASK_PLACEHOLDER, open(sys.argv[1], 'w'))" "$TASK_FILE"
python3 "$CLAUDE_PLUGIN_ROOT/scripts/task_manager.py" \
  --config ~/.claude/timesheet.json \
  --action create-task \
  --task-file "$TASK_FILE"
rm -f "$TASK_FILE"
```

Where `TASK_PLACEHOLDER` is:
```json
{
  "subject": "<confirmed subject>",
  "description": "<confirmed description>",
  "project": "<project from config>",
  "hours": <entry's current hours>,
  "date": "<today YYYY-MM-DD>"
}
```

The command outputs zero or more `Note:` lines followed by a JSON line `{"name": "TASK-..."}` on the last line. Print any `Note:` lines to the user. Parse the last line to get the task name. Assign it to the entry. Re-display TUI.

### [q] Quit

Say: `Timesheet not submitted.` Stop.

## Step 6: Submit

Tell the user: `Submitting timesheet...`

Write the approved entries to a temp file and submit. Each entry must include `description`, `hours`, `activity_type`. Entries with a task assigned also include `task`.

Substitute `ENTRIES_PLACEHOLDER` with the Python literal for the approved entries list:
```json
[
  {"description": "...", "hours": 4.0, "activity_type": "Development", "task": "TASK-2026-01052"},
  {"description": "...", "hours": 4.0, "activity_type": "Development"}
]
```

```bash
ENTRIES_FILE=$(mktemp /tmp/timesheet-entries-XXXXXX.json)
python3 -c "import json, sys; json.dump(ENTRIES_PLACEHOLDER, open(sys.argv[1], 'w'))" "$ENTRIES_FILE"
python3 "$CLAUDE_PLUGIN_ROOT/scripts/erpnext_client.py" \
  --config ~/.claude/timesheet.json \
  --action submit \
  --entries-file "$ENTRIES_FILE"
rm -f "$ENTRIES_FILE"
```

If the command succeeds (exit 0), say:
`Timesheet submitted. Reference: <name from output>`

If it fails, show the full error output and ask: `Retry? [y/n]`
If `y`, re-run the submit command (maximum 3 total attempts). After 3 failed attempts, stop and tell the user to check their ERPNext connection and try again later. If `n`, stop.
