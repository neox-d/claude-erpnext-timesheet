# ERPNext Timesheet

Automate daily ERPNext timesheet filling from your Claude conversation history.

---

When this skill is invoked, follow these steps exactly. Do not skip steps.

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

Also read work_hours from config:
```bash
python3 -c "import json; c=json.load(open('$HOME/.claude/timesheet.json')); print(c['work_hours'])"
```

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
Otherwise proceed to Step 6.

### [e] Edit
Ask: `Which entry number?`
For the chosen entry, prompt each field with its current value in brackets (press Enter to keep):
```
  Description [current value]:
  Hours [current value]:
  Activity type [current value]:
```
After edit, check if total hours still equals work_hours. If not:
`Warning: total hours = Xh (expected Yh). Submit anyway? [y/n]`
Re-display TUI.

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
```bash
ENTRIES_FILE=$(mktemp /tmp/timesheet-entries-XXXXXX.json)
# write the JSON array of approved entries to $ENTRIES_FILE
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
If `y`, re-run the submit command. If `n`, stop.
