# ERPNext Timesheet

Automate daily ERPNext timesheet filling from your Claude conversation history.

---

When this skill is invoked, follow these steps exactly. Do not skip steps.

## Step 0: First-Time Setup

Check if `~/.claude/timesheet.json` exists:
```bash
test -f ~/.claude/timesheet.json && echo "EXISTS" || echo "MISSING"
```

If `MISSING`, run the interactive setup wizard:

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

If it succeeds, the output contains `employee`, `company`, `projects` (list), `activity_types` (list).

Present the discovered values to the user:
```
Found:
  Employee:  <employee>
  Company:   <company>
  Projects:  <list>
  Activity types: <list>
```

If the list shows a `projects_truncated` or `activity_types_truncated` flag, note to the user that the list may be incomplete and they can type a project/activity name manually.

Ask:
4. **Default project** — show the discovered list, ask user to pick one (or type a project name if not listed)
5. **Default activity type** — show the discovered list, ask user to pick one
6. **Work hours per day** — default `8`
7. **Workday start time** — default `09:00`
8. **Timezone** — default is your system timezone; common options: `Asia/Kolkata`, `UTC`, `America/New_York`

Build the config JSON and write it:

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

If `EXISTS`, skip to Step 1.

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

Parse `work_hours` from the JSON output already stored in Step 2. (It is one of the required fields guaranteed to be present after successful config validation.)

## Step 3: Synthesize Task Entries

Tell the user: `Summarizing work done...`

From the conversation messages, identify distinct work themes. Create task entries where:
- **description**: short professional summary of the work, max 80 characters, no filler ("worked on", "helped with")
- **hours**: `work_hours / number_of_tasks`, rounded to 1 decimal. Last task absorbs rounding remainder so total equals work_hours exactly.
- **activity_type**: read `default_activity` from `~/.claude/timesheet.json`

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

Read today's date and display:

```
Draft timesheet for YYYY-MM-DD (Xh total):
──────────────────────────────────────────
1. [Xh] Description of task one
2. [Xh] Description of task two
...
──────────────────────────────────────────

[a] Approve and submit
[e] Edit an entry
[d] Delete an entry
[+] Add an entry (for work done outside Claude)
[q] Quit without submitting

>
```

Handle the user's response:

### [a] Approve
If the entry list is empty, say: `No entries to submit. Use [+] to add entries first.` Re-display menu.
Otherwise, check if total hours equals work_hours. If there is a mismatch, show:
`Warning: total hours = Xh (expected Yh). Submit anyway? [y/n]`
If `n`, re-display TUI. If `y` (or if no mismatch), proceed to Step 6.

### [e] Edit
Ask: `Which entry number?`
For the chosen entry, prompt each field with its current value in brackets (press Enter to keep):
```
  Description [current value]:
  Hours [current value]:
  Activity type [current value]:
```
After edit, check if total hours still equals work_hours. If not, show:
`Warning: total hours = Xh (expected Yh).`
This is informational only — do not submit. Re-display TUI so the user can adjust further or choose [a] to submit with the mismatch acknowledged.

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
Add to list. Re-display TUI.

### [q] Quit
Say: `Timesheet not submitted.` Stop.

## Step 6: Submit

Tell the user: `Submitting timesheet...`

Write the approved entries to a temp file and submit:

Substitute `ENTRIES_PLACEHOLDER` with the Python literal for the approved entries list (e.g. `[{"description": "...", "hours": 2.0, "activity_type": "Development"}, ...]`). Serialize using `json.dumps()` if constructing dynamically.

```bash
ENTRIES_FILE=$(mktemp /tmp/timesheet-entries-XXXXXX.json)
python3 -c "import json, sys; json.dump(ENTRIES_PLACEHOLDER, open(sys.argv[1], 'w'))" "$ENTRIES_FILE"
python3 "$CLAUDE_PLUGIN_ROOT/scripts/erpnext_client.py" \
  --config ~/.claude/timesheet.json \
  --action submit \
  --entries-file "$ENTRIES_FILE"
rm -f "$ENTRIES_FILE"
```

Each entry in the JSON array must have keys: `description`, `hours`, `activity_type`.

If the command succeeds (exit 0), say:
`Timesheet submitted. Reference: <name from output>`

If it fails, show the full error output and ask: `Retry? [y/n]`
If `y`, re-run the submit command (maximum 3 total attempts). After 3 failed attempts, stop and tell the user to check their ERPNext connection and try again later. If `n`, stop.
