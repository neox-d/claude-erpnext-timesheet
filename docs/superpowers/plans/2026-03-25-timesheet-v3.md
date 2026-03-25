# Timesheet v3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add UX cleanup, Reset/Reconfigure, Backdated Entry support, and data source flexibility to the ERPNext Timesheet plugin.

**Architecture:** Script changes (`parse_logs.py`, `erpnext_client.py`) are backward-compatible additions of an optional `--date` flag. SKILL.md changes handle the rest: silent internal checks, Step 0 reconfigure prompt, date resolution at entry, and data source flexibility instruction. All changes are tested before SKILL.md is updated.

**Tech Stack:** Python 3.9+, argparse, pytest, ERPNext REST API, Claude Code SKILL.md

---

## File Map

| File | Change |
|---|---|
| `skills/timesheet/scripts/parse_logs.py` | Add `--date` arg; update `get_today_messages` signature; fix mtime filter direction |
| `skills/timesheet/scripts/erpnext_client.py` | Add `--date` arg; pass into `build_timesheet_doc`; replace `datetime.today()` |
| `skills/timesheet/SKILL.md` | UX cleanup, Step 0 reconfigure, date resolution, date propagation, data source flexibility |
| `tests/test_parse_logs.py` | Add `--date` tests; fix two existing tests that regress after mtime filter change |
| `tests/test_erpnext_client.py` | Add `--date` tests for `build_timesheet_doc` and CLI |
| `.claude-plugin/plugin.json` | Bump version to `1.2.0` |

**Note on `task_manager.py`:** The spec lists it as an edit because the task date comes from the SKILL.md `TASK_PLACEHOLDER` payload (`task_input["date"]` at line 99). No code change to `task_manager.py` is needed — the fix is entirely in SKILL.md (Step 3.6). The `_next_month_end(date.today())` call at line 112 (project extension deadline) is out of scope per the spec.

---

## Task 1: `parse_logs.py` — add `--date` flag

**Files:**
- Modify: `skills/timesheet/scripts/parse_logs.py:75-136,139-163`
- Test: `tests/test_parse_logs.py`

### Changes

`get_today_messages` gains an optional `target_date: date | None = None` parameter:
- When `None`: uses today (unchanged behaviour)
- When provided: uses `target_date` for timestamp filter
- mtime pre-filter direction reverses: skip files modified **after** `target_date` (`mtime.date() > target_date`), so past files are included

`main()` gains `--date YYYY-MM-DD` argument that parses to a `date` and passes to `get_today_messages`.

- [ ] **Step 1.1: Write failing tests**

Add to `tests/test_parse_logs.py`. First add this import near the top with the other imports (the file already imports `date` and `datetime` from `datetime` — add an alias):

```python
from datetime import date as date_type  # alias to avoid shadowing in test bodies
```

Then add the new tests:

```python
def test_get_messages_for_date_returns_messages_from_that_date(tmp_path, monkeypatch):
    """--date 2026-03-23 returns messages from that date."""
    proj_dir = tmp_path / ".claude" / "projects" / "myproject"
    proj_dir.mkdir(parents=True)
    session_file = proj_dir / "abc-123.jsonl"
    session_file.write_text(FIXTURE_PATH.read_text())

    # mtime = the target date (should be included)
    target = datetime(2026, 3, 23, 12, 0, 0, tzinfo=timezone.utc)
    os.utime(session_file, (target.timestamp(), target.timestamp()))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    messages = get_today_messages(tz=timezone.utc, target_date=date_type(2026, 3, 23))
    assert len(messages) == 4


def test_get_messages_for_date_skips_future_mtime_files(tmp_path, monkeypatch):
    """Files with mtime after target_date are skipped."""
    proj_dir = tmp_path / ".claude" / "projects" / "myproject"
    proj_dir.mkdir(parents=True)
    session_file = proj_dir / "abc-123.jsonl"
    session_file.write_text(FIXTURE_PATH.read_text())

    # mtime = one day after target date — should be skipped
    future = datetime(2026, 3, 24, 12, 0, 0, tzinfo=timezone.utc)
    os.utime(session_file, (future.timestamp(), future.timestamp()))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    messages = get_today_messages(tz=timezone.utc, target_date=date_type(2026, 3, 23))
    assert messages == []


def test_get_messages_for_date_includes_same_day_mtime(tmp_path, monkeypatch):
    """Files with mtime on the target date are included."""
    proj_dir = tmp_path / ".claude" / "projects" / "myproject"
    proj_dir.mkdir(parents=True)
    session_file = proj_dir / "abc-123.jsonl"
    session_file.write_text(FIXTURE_PATH.read_text())

    # mtime = end of target date (still same day)
    same_day = datetime(2026, 3, 23, 23, 59, 0, tzinfo=timezone.utc)
    os.utime(session_file, (same_day.timestamp(), same_day.timestamp()))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    messages = get_today_messages(tz=timezone.utc, target_date=date_type(2026, 3, 23))
    assert len(messages) == 4


def test_get_today_messages_no_date_arg_uses_today(tmp_path, monkeypatch):
    """Calling get_today_messages() with no target_date uses today (backward compat)."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    # No projects dir → empty result; what matters is it doesn't crash
    messages = get_today_messages()
    assert messages == []
```

- [ ] **Step 1.2: Run tests to confirm they fail**

```bash
cd /home/neox/Work/erpnext-timesheet
python -m pytest tests/test_parse_logs.py::test_get_messages_for_date_returns_messages_from_that_date tests/test_parse_logs.py::test_get_messages_for_date_skips_future_mtime_files tests/test_parse_logs.py::test_get_messages_for_date_includes_same_day_mtime -v
```

Expected: `TypeError` or `FAILED` — `target_date` parameter doesn't exist yet.

- [ ] **Step 1.3: Implement the changes**

In `skills/timesheet/scripts/parse_logs.py`:

1. Update the import line (add `date` type alias if not already imported — it is: `from datetime import date, datetime`).

2. Change `get_today_messages` signature and body:

```python
def get_today_messages(tz=None, target_date=None) -> list:
    projects_dir = Path.home() / ".claude" / "projects"
    if not projects_dir.exists():
        return []

    if target_date is None:
        if tz is not None:
            target_date = datetime.now(tz).date()
        else:
            target_date = date.today()
    messages = []

    for project_dir in projects_dir.iterdir():
        if not project_dir.is_dir():
            continue
        for jsonl_file in project_dir.glob("*.jsonl"):
            # mtime pre-filter: skip files modified AFTER target_date
            # (they can't contain messages from that date)
            if tz is not None:
                mtime = datetime.fromtimestamp(jsonl_file.stat().st_mtime, tz=tz).date()
            else:
                mtime = datetime.fromtimestamp(jsonl_file.stat().st_mtime).date()
            if mtime > target_date:
                continue

            try:
                for line in jsonl_file.read_text(errors="replace").splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    if entry.get("type") not in ("user", "assistant"):
                        continue

                    ts_str = entry.get("timestamp", "")
                    if not ts_str:
                        continue

                    ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    ts_local = ts.astimezone(tz) if tz else ts.astimezone()

                    if ts_local.date() != target_date:
                        continue

                    msg = entry.get("message", {})
                    content = msg.get("content", "")
                    text = parse_content_blocks(content)
                    if not text:
                        continue

                    messages.append({
                        "role": entry["type"],
                        "text": text[:500],
                        "cwd": entry.get("cwd", ""),
                        "timestamp": ts_local.isoformat(),
                    })
            except Exception:
                continue

    return sorted(messages, key=lambda m: m["timestamp"])
```

3. Update `main()` to add the `--date` argument:

```python
def main():
    parser = argparse.ArgumentParser(description="Parse Claude conversation logs")
    parser.add_argument("--config", required=True, help="Path to timesheet.json")
    parser.add_argument("--validate-only", action="store_true",
                        help="Validate config and exit")
    parser.add_argument("--date", help="Date to read logs for (YYYY-MM-DD). Defaults to today.")
    args = parser.parse_args()

    config = load_config(args.config)
    errors = validate_config(config)
    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    if args.validate_only:
        print("OK")
        return

    tz = get_timezone(config)
    target_date = date.fromisoformat(args.date) if args.date else None
    messages = get_today_messages(tz, target_date=target_date)
    print(json.dumps(messages, indent=2))
```

- [ ] **Step 1.4: Run all parse_logs tests and fix the two that regress**

```bash
cd /home/neox/Work/erpnext-timesheet
python -m pytest tests/test_parse_logs.py -v
```

Two existing tests will fail because after the change, `get_today_messages(tz=timezone.utc)` (no `target_date`) does `datetime.now(tz).date()` which is not patched by the old `patch("scripts.parse_logs.date")` mock. Fix both:

**Fix `test_get_today_messages_sorted_by_timestamp`:** add an explicit mtime set and pass `target_date`:

```python
def test_get_today_messages_sorted_by_timestamp(tmp_path, monkeypatch):
    proj_dir = tmp_path / ".claude" / "projects" / "myproject"
    proj_dir.mkdir(parents=True)
    session_file = proj_dir / "abc-123.jsonl"
    session_file.write_text(FIXTURE_PATH.read_text())

    # Set mtime to the fixture date so mtime pre-filter includes the file
    fixed_ts = datetime(2026, 3, 23, 12, 0, 0, tzinfo=timezone.utc)
    os.utime(session_file, (fixed_ts.timestamp(), fixed_ts.timestamp()))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    messages = get_today_messages(tz=timezone.utc, target_date=date_type(2026, 3, 23))

    timestamps = [m["timestamp"] for m in messages]
    assert timestamps == sorted(timestamps)
```

**Fix `test_get_today_messages_skips_old_mtime_files`:** pass `target_date` and set mtime to one day after it (so `mtime.date() > target_date` is True, file is skipped):

```python
def test_get_today_messages_skips_future_mtime_files(tmp_path, monkeypatch):
    """Files with mtime after target_date are skipped (mtime pre-filter)."""
    proj_dir = tmp_path / ".claude" / "projects" / "myproject"
    proj_dir.mkdir(parents=True)
    session_file = proj_dir / "abc-123.jsonl"
    session_file.write_text(FIXTURE_PATH.read_text())

    # Set mtime to one day after the target date — should be skipped
    after_target = datetime(2026, 3, 24, 0, 0, 0, tzinfo=timezone.utc)
    os.utime(session_file, (after_target.timestamp(), after_target.timestamp()))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    messages = get_today_messages(tz=timezone.utc, target_date=date_type(2026, 3, 23))
    assert messages == []
```

Note: rename the function from `test_get_today_messages_skips_old_mtime_files` to `test_get_today_messages_skips_future_mtime_files` to match the new filter semantics.

After applying both fixes, re-run:
```bash
python -m pytest tests/test_parse_logs.py -v
```
Expected: all pass.

- [ ] **Step 1.5: Commit**

```bash
cd /home/neox/Work/erpnext-timesheet
git add skills/timesheet/scripts/parse_logs.py tests/test_parse_logs.py
git commit -m "feat: add --date flag to parse_logs.py for backdated entry support"
```

---

## Task 2: `erpnext_client.py` — add `--date` flag

**Files:**
- Modify: `skills/timesheet/scripts/erpnext_client.py:74-106,109-152`
- Test: `tests/test_erpnext_client.py`

### Changes

`build_timesheet_doc(config, entries, date_str=None)` gains an optional `date_str` parameter:
- When `None`: uses `datetime.today()` (existing behavior)
- When provided: parsed with `datetime.strptime(date_str, "%Y-%m-%d")` and used for `start_date`, `end_date`, `from_time`/`to_time` base

`main()` gains `--date YYYY-MM-DD` argument, used for both `check-duplicate` and `submit`.

- [ ] **Step 2.1: Write failing tests**

Add to `tests/test_erpnext_client.py`:

```python
def test_build_timesheet_doc_with_date_str_uses_that_date():
    """date_str overrides today for start_date, end_date, and time log timestamps."""
    entries = [{"description": "Task A", "hours": 2.0}]
    doc = build_timesheet_doc(BASE_CONFIG, entries, date_str="2026-03-24")
    assert doc["start_date"] == "2026-03-24"
    assert doc["end_date"] == "2026-03-24"
    assert doc["time_logs"][0]["from_time"].startswith("2026-03-24")
    assert doc["time_logs"][0]["to_time"].startswith("2026-03-24")


def test_build_timesheet_doc_without_date_str_uses_today():
    """No date_str → dates use today (backward compat)."""
    from datetime import date as date_type
    entries = [{"description": "Task A", "hours": 2.0}]
    doc = build_timesheet_doc(BASE_CONFIG, entries)
    today_str = date_type.today().strftime("%Y-%m-%d")
    assert doc["start_date"] == today_str
    assert doc["end_date"] == today_str
```

- [ ] **Step 2.2: Run tests to confirm they fail**

```bash
cd /home/neox/Work/erpnext-timesheet
python -m pytest tests/test_erpnext_client.py::test_build_timesheet_doc_with_date_str_uses_that_date tests/test_erpnext_client.py::test_build_timesheet_doc_without_date_str_uses_today -v
```

Expected: `TypeError` — `date_str` parameter doesn't exist yet.

- [ ] **Step 2.3: Implement the changes**

In `skills/timesheet/scripts/erpnext_client.py`:

1. Change `build_timesheet_doc` signature and body:

```python
def build_timesheet_doc(config: dict, entries: list, date_str: str = None) -> dict:
    if date_str:
        base = datetime.strptime(date_str, "%Y-%m-%d")
    else:
        base = datetime.today()
    today = base.strftime("%Y-%m-%d")
    start_time_str = config.get("start_time", "09:00")
    h, m = map(int, start_time_str.split(":"))
    current = base.replace(hour=h, minute=m, second=0, microsecond=0)

    time_logs = []
    for entry in entries:
        hours = float(entry["hours"])
        from_time = current.strftime("%Y-%m-%d %H:%M:%S")
        current += timedelta(hours=hours)
        to_time = current.strftime("%Y-%m-%d %H:%M:%S")
        log = {
            "activity_type": entry.get("activity_type", config["default_activity"]),
            "description": entry["description"],
            "hours": hours,
            "from_time": from_time,
            "to_time": to_time,
            "project": config["project"],
        }
        if entry.get("task"):
            log["task"] = entry["task"]
        time_logs.append(log)

    return {
        "employee": config["employee"],
        "company": config["company"],
        "user": config["username"],
        "start_date": today,
        "end_date": today,
        "time_logs": time_logs,
    }
```

2. Update `main()` to add `--date`:

```python
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--action", choices=["check-duplicate", "submit"], required=True)
    parser.add_argument("--entries", help="JSON array of approved entries (inline)")
    parser.add_argument("--entries-file", help="Path to JSON file with approved entries (preferred)")
    parser.add_argument("--date", help="Date for timesheet operations (YYYY-MM-DD). Defaults to today.")
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.exists():
        print(f"ERROR: Config file not found: {args.config}", file=sys.stderr)
        sys.exit(1)
    try:
        config = json.loads(config_path.read_text())
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON in config: {e}", file=sys.stderr)
        sys.exit(1)
    client = ERPNextClient(config["url"], config["username"], decrypt_password(config["password"]))
    date_str = args.date if args.date else datetime.today().strftime("%Y-%m-%d")

    if args.action == "check-duplicate":
        exists = client.check_duplicate(config["employee"], date_str)
        print(json.dumps({"exists": exists}))

    elif args.action == "submit":
        if args.entries_file:
            try:
                entries = json.loads(Path(args.entries_file).read_text())
            except (OSError, json.JSONDecodeError) as e:
                print(f"ERROR: Could not read entries file: {e}", file=sys.stderr)
                sys.exit(1)
        elif args.entries:
            entries = json.loads(args.entries)
        else:
            print("ERROR: --entries-file or --entries required for submit action", file=sys.stderr)
            sys.exit(1)
        doc = build_timesheet_doc(config, entries, date_str=args.date)
        # Note: pass args.date (None when omitted), NOT the resolved date_str variable.
        # build_timesheet_doc handles None by calling datetime.today() internally.
        name = client.create_timesheet(doc)
        client.submit_timesheet(name)
        print(json.dumps({"success": True, "name": name}))
```

- [ ] **Step 2.4: Run all erpnext_client tests**

```bash
cd /home/neox/Work/erpnext-timesheet
python -m pytest tests/test_erpnext_client.py -v
```

Expected: all pass.

- [ ] **Step 2.5: Run full test suite**

```bash
cd /home/neox/Work/erpnext-timesheet
python -m pytest -v
```

Expected: all pass.

- [ ] **Step 2.6: Commit**

```bash
cd /home/neox/Work/erpnext-timesheet
git add skills/timesheet/scripts/erpnext_client.py tests/test_erpnext_client.py
git commit -m "feat: add --date flag to erpnext_client.py for backdated entry support"
```

---

## Task 3: `SKILL.md` — UX cleanup, reset, backdated entry, data source flexibility

**Files:**
- Modify: `skills/timesheet/SKILL.md`

No tests for SKILL.md — validate by reading the updated file end-to-end and confirming the flow is coherent.

- [ ] **Step 3.1: Update frontmatter**

Change `description` and bump `version`:

```yaml
---
name: timesheet
description: Use when the user wants to submit today's ERPNext timesheet, log work hours, fill in a timesheet from conversation history, or make a backdated timesheet entry for a previous date
version: 1.2.0
---
```

- [ ] **Step 3.2: Replace Step 0**

Replace the entire `## Step 0` section (lines 15–135) with:

```markdown
## Step 0: Setup and Date Resolution

**Resolve the target date first.** Read the invocation message:
- If it specifies a past date (e.g. "for yesterday", "for 2026-03-24", "last Friday") — resolve it to `YYYY-MM-DD` format and store as `TARGET_DATE`.
- Otherwise set `TARGET_DATE` to today's date (`YYYY-MM-DD`).

Check if `~/.claude/timesheet.json` exists:
```bash
test -f ~/.claude/timesheet.json && echo "EXISTS" || echo "MISSING"
```

Do not display the output. Branch silently:

**If MISSING** — run the setup wizard below.

**If EXISTS** — read the config file to get `username` and `url`. Show:
```
<username> @ <url>. [Enter] to continue, [r] to reconfigure.
```
If the user presses Enter, skip to Step 1.
If the user types `r`, run the setup wizard below. After the wizard completes, continue to Step 1.

### Setup Wizard

Tell the user:
```
Welcome! Let's connect to your ERPNext instance.
This will create ~/.claude/timesheet.json with your credentials and preferences.
```

Ask the following questions one at a time:

1. **ERPNext URL** — e.g. `https://yourcompany.erpnext.com`
2. **Username** — your ERPNext login email

Then test login and discover configuration. The password will be prompted securely in the terminal (masked — it will not appear in the conversation):
```bash
python3 "scripts/setup.py" \
  --action discover \
  --url "<URL>" \
  --username "<USERNAME>" \
  --prompt-password
```

If the command fails, show the error and ask the user to correct their credentials. Re-ask steps 1–2.

If it succeeds, the output contains `employee`, `company`, `full_name`, `projects` (list), `activity_types` (list), and `_pwd_file` (path to a temp file holding the password securely). Store the `_pwd_file` path for the write-config step.

Show the identity confirmation block and ask:
```
Logged in as: <full_name>
Employee:     <employee>
Company:      <company>

Is this the right account? [y/n]
```

If `n`, re-ask steps 1–2 and re-run discover.

Then display the discovered lists and present each setting with the discovered or default value in brackets. The user presses Enter to accept, or types a new value to override:

```
Available projects:
  1. <project 1>
  2. <project 2>
  ...

Available activity types:
  1. <activity type 1>
  2. <activity type 2>
  ...

Default project [<first project>]:
Default activity type [<first activity type>]:
Working hours per day [8]:
Workday start time [09:00]:
Timezone [<system timezone — run: timedatectl show --property=Timezone --value>]:
```

If the output shows `projects_truncated` or `activity_types_truncated`, append `(list may be incomplete — type a name manually if yours is missing)` after the respective list.

Before saving, show a summary and ask for confirmation:
```
About to save:
  URL:           <url>
  User:          <username>
  Employee:      <employee>
  Project:       <project>
  Activity type: <default_activity>
  Working hours: <work_hours>
  Start time:    <start_time>
  Timezone:      <timezone>

Save to ~/.claude/timesheet.json? [y/n]
```

If `n`, restart from the beginning (re-ask URL, username).

If `y`, build the config JSON and write it. The password is never included in the conversation — it is read from the `_pwd_file` temp file created during discover.

Substitute `CONFIG_PLACEHOLDER` with the Python dict literal for the assembled config (no password field — that is injected by `--pwd-file`):

```bash
CONFIG_TMPFILE=$(mktemp /tmp/timesheet-setup-XXXXXX.json)
python3 -c "import json, sys; json.dump(CONFIG_PLACEHOLDER, open(sys.argv[1], 'w'))" "$CONFIG_TMPFILE"
python3 "scripts/setup.py" \
  --action write-config \
  --config-file "$CONFIG_TMPFILE" \
  --pwd-file "<_pwd_file path from discover output>" \
  --config-out ~/.claude/timesheet.json
rm -f "$CONFIG_TMPFILE"
```

Where `CONFIG_PLACEHOLDER` is the Python dict literal for:
```json
{
  "url": "<URL>",
  "username": "<USERNAME>",
  "employee": "<discovered employee>",
  "company": "<discovered company>",
  "project": "<chosen project>",
  "default_activity": "<chosen activity type>",
  "work_hours": <work_hours>,
  "start_time": "<start_time>",
  "timezone": "<timezone>"
}
```

The `--pwd-file` flag injects the password into the config and deletes the temp file automatically.

Tell the user: `Setup complete! Config saved to ~/.claude/timesheet.json`
```

- [ ] **Step 3.3: Update Step 1 (silent validation)**

Replace:
```markdown
## Step 1: Validate Config

Run:
```bash
python3 "scripts/parse_logs.py" --config ~/.claude/timesheet.json --validate-only
```

If the command exits non-zero or output is not `OK`, print the error and stop. Do not proceed.
```

With:
```markdown
## Step 1: Validate Config

Run silently:
```bash
python3 "scripts/parse_logs.py" --config ~/.claude/timesheet.json --validate-only
```

Do not display the output. If the command exits non-zero, print the error output and stop. Do not proceed.
```

- [ ] **Step 3.4: Update Step 2 (date-aware, data source flexible)**

Replace:
```markdown
## Step 2: Read Today's Conversations

Tell the user: `Reading today's Claude conversations...`

Run:
```bash
python3 "scripts/parse_logs.py" --config ~/.claude/timesheet.json
```

This returns a JSON array of messages `[{role, text, cwd, timestamp}]`. Store this as your context.

Parse `work_hours` from `~/.claude/timesheet.json` for use in Step 3 and Step 5.
```

With:
```markdown
## Step 2: Read Work Context

Tell the user: `Reading work context for <TARGET_DATE>...`

**Default (no other instruction):** run:
```bash
python3 "scripts/parse_logs.py" --config ~/.claude/timesheet.json --date "<TARGET_DATE>"
```

This returns a JSON array of messages `[{role, text, cwd, timestamp}]`. Store this as your context.

**If the user specified a different data source** (e.g. "use my git commits", "I'll describe what I did"), read from that source instead. Adapt naturally — run `git log`, read files, or ask the user to describe their work. The goal is the same: gather enough context to synthesize task entries in Step 3.

Parse `work_hours` from `~/.claude/timesheet.json` for use in Step 3 and Step 5.
```

- [ ] **Step 3.5: Update Step 4 (silent duplicate check, date-aware)**

Replace:
```markdown
## Step 4: Check for Duplicate

Run:
```bash
python3 "scripts/erpnext_client.py" --config ~/.claude/timesheet.json --action check-duplicate
```

If the output contains `"exists": true`, ask:
`Warning: A timesheet already exists for today. Continue anyway? [y/n]`
If user answers `n`, stop.
```

With:
```markdown
## Step 4: Check for Duplicate

Run silently:
```bash
python3 "scripts/erpnext_client.py" --config ~/.claude/timesheet.json --action check-duplicate --date "<TARGET_DATE>"
```

Do not display the raw output. If the output contains `"exists": true`, warn:
`A timesheet already exists for <TARGET_DATE>. Continue anyway? [y/n]`
If user answers `n`, stop.
```

- [ ] **Step 3.6: Update Step 5 TUI header, `[h]` label, and task date**

In the TUI display block, change:
- `Draft timesheet for YYYY-MM-DD (Xh total):` → `Draft timesheet for <TARGET_DATE> (Xh total):`
- `[h] Change hours for today` → `[h] Redistribute hours`

In the `[h]` section header, change:
- `### [h] Change hours for today` → `### [h] Redistribute hours`
- Prompt: `New total hours [<current total>]:` (keep as-is)
- Note: `Note: total is Xh (configured default is Yh).` (keep as-is)

In the `[t]` → `[n]` create-task payload, change:
```json
"date": "<today YYYY-MM-DD>"
```
to:
```json
"date": "<TARGET_DATE>"
```

- [ ] **Step 3.7: Update Step 6 (pass date to submit)**

In the submit bash block, change:
```bash
python3 "scripts/erpnext_client.py" \
  --config ~/.claude/timesheet.json \
  --action submit \
  --entries-file "$ENTRIES_FILE"
```
to:
```bash
python3 "scripts/erpnext_client.py" \
  --config ~/.claude/timesheet.json \
  --action submit \
  --date "<TARGET_DATE>" \
  --entries-file "$ENTRIES_FILE"
```

- [ ] **Step 3.8: Read the full updated SKILL.md end-to-end**

Read `skills/timesheet/SKILL.md` from top to bottom and confirm:
- Step 0 has date resolution, silent config check, reconfigure prompt, and setup wizard without "plaintext" note
- Step 1 is silent on success
- Step 2 passes `--date` and has data source flexibility note
- Step 4 is silent, passes `--date`, warning uses TARGET_DATE
- Step 5 TUI shows TARGET_DATE, `[h]` says "Redistribute hours", `[n]` task date uses TARGET_DATE
- Step 6 passes `--date`

Fix any inconsistencies found.

- [ ] **Step 3.9: Commit**

```bash
cd /home/neox/Work/erpnext-timesheet
git add skills/timesheet/SKILL.md
git commit -m "feat: UX cleanup, reset/reconfigure, backdated entry, data source flexibility"
```

---

## Task 4: Version bump and deploy

**Files:**
- Modify: `.claude-plugin/plugin.json`
- Modify: `/tmp/claude-plugins/.claude-plugin/marketplace.json`

- [ ] **Step 4.1: Bump plugin version**

In `.claude-plugin/plugin.json`, change `"version": "1.1.0"` to `"version": "1.2.0"`.

- [ ] **Step 4.2: Commit and push plugin repo**

```bash
cd /home/neox/Work/erpnext-timesheet
git add .claude-plugin/plugin.json
git commit -m "chore: bump version to 1.2.0"
git push
```

- [ ] **Step 4.3: Update marketplace SHA**

Get the new HEAD SHA:
```bash
cd /home/neox/Work/erpnext-timesheet
git rev-parse HEAD
```

Update `/tmp/claude-plugins/.claude-plugin/marketplace.json` — the plugin source uses `"ref": "master"` (no SHA), so **no SHA update needed**. The marketplace will always pull from `master`.

- [ ] **Step 4.4: Verify instructions for user**

After pushing, instruct the user to run:
```
/plugin marketplace update neox-d-plugins
```

This will show "1 plugin bumped" (from 1.1.0 to 1.2.0) and trigger the update automatically.
