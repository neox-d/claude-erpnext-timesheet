# ERPNext Timesheet v3 — Design Spec

**Date:** 2026-03-25
**Scope:** UX improvements, Reset/Reconfigure, Backdated Entry, Data Source Flexibility

---

## Overview

Four improvements to the ERPNext Timesheet plugin:

1. **UX cleanup** — remove raw command output from user-facing flow
2. **Reset/Reconfigure** — allow re-running setup wizard without deleting config manually
3. **Backdated Entry** — submit timesheets for dates other than today
4. **Data source flexibility** — Step 2 reads from conversation logs by default, but supports other sources when the user specifies

---

## 1. UX Cleanup

All internal bash checks run silently. Claude reads the output but does not echo it to the user unless there is an error.

Affected steps:
- **Step 0** — `test -f ~/.claude/timesheet.json` result is not shown; just branch on it
- **Step 1** — `parse_logs.py --validate-only` output is not shown if it returns `OK`; only shown on failure
- **Step 4** — `erpnext_client.py --action check-duplicate` JSON is not shown; only the warning message if `"exists": true`

Other changes:
- Remove the "credentials are stored in plaintext" note from the setup wizard welcome message (passwords are encrypted at rest)
- Replace raw field names with human-readable labels in user-visible text (e.g., "Working hours: 8h" instead of `work_hours`)

---

## 2. Reset / Reconfigure

When `~/.claude/timesheet.json` exists, Step 0 reads the config and presents the current identity:

```
<username> @ <url>. [Enter] to continue, [r] to reconfigure.
```

- **Enter** — proceed to Step 1
- **r** — run the full setup wizard (identical to first-time setup), overwriting `~/.claude/timesheet.json` on confirmation, then proceed to Step 1

After the reconfigure wizard completes, execution continues at Step 1 (config validation) exactly as it would after a first-time setup.

No script changes required. This is a SKILL.md-only change.

---

## 3. Backdated Entry

### Intent detection

The SKILL.md description is updated to also match backdated invocations:

> Use when the user wants to submit today's ERPNext timesheet, log work hours, fill in a timesheet from conversation history, or make a backdated timesheet entry for a previous date.

If the invocation message specifies a past date, "yesterday", "last Friday", etc., Claude resolves it to a `YYYY-MM-DD` string at Step 0 and uses it throughout. Normal invocations always default to today — no extra prompt is shown.

### Date propagation

The resolved date is passed to all scripts that need it:

- `parse_logs.py --date YYYY-MM-DD` — reads conversations from that date
- `erpnext_client.py --action check-duplicate --date YYYY-MM-DD` — checks for existing timesheet on that date
- `erpnext_client.py --action submit --date YYYY-MM-DD` — submits timesheet for that date

The TUI header uses the resolved date: `Draft timesheet for YYYY-MM-DD`.

### Script changes: `parse_logs.py`

Add `--date YYYY-MM-DD` argument. When provided:
- `target_date` is parsed from the argument instead of `date.today()`
- The mtime pre-filter condition changes to `mtime.date() > target_date` (skip files modified *after* the target date — they can't contain target-date messages). Files modified on or before the target date are included.
- Message timestamp filter uses `target_date` instead of today

### Script changes: `erpnext_client.py`

Add `--date YYYY-MM-DD` argument to the `check-duplicate` and `submit` actions. When omitted, defaults to today (backward compatible).

For `submit`: the resolved date is passed into `build_timesheet_doc` and used for `start_date`, `end_date`, and as the base date for `from_time`/`to_time` timestamps — replacing all calls to `datetime.today()` inside that function.

### Script changes: `task_manager.py`

The `[t]` → `[n]` (create new task) flow in SKILL.md currently hardcodes `"date": "<today YYYY-MM-DD>"` in the task payload. For backdated entries, the resolved date is used instead of today.

---

## 4. Data Source Flexibility

Step 2 is a decision point, not a fixed command.

**Default behaviour (no user instruction):** run `parse_logs.py` to read today's (or target date's) conversation logs.

**Alternative sources:** if the invocation or user message specifies a different source — git commits, a written description, Jira tickets, etc. — Claude reads from that source instead of running `parse_logs.py`. No code change required; this is a SKILL.md instruction.

Step 3 (synthesis) is unchanged regardless of source: Claude produces task entries from whatever content was gathered in Step 2.

---

## Components Summary

| Component | Change type | Description |
|---|---|---|
| `SKILL.md` | Edit | UX cleanup, Step 0 reconfigure, backdated date propagation, Step 2 flexibility |
| `parse_logs.py` | Edit | Add `--date` flag; fix mtime pre-filter for past dates |
| `erpnext_client.py` | Edit | Add `--date` flag to check-duplicate and submit; pass date into `build_timesheet_doc` |
| `task_manager.py` | Edit | SKILL.md passes resolved date in task creation payload |
| Tests | Edit | Update/add tests for `--date` in parse_logs and erpnext_client |

---

## Testing

- `parse_logs.py --date 2026-03-24` returns messages from that date; files modified after that date are excluded by mtime pre-filter
- `parse_logs.py` with no `--date` keeps existing today-only behaviour
- `erpnext_client.py --action check-duplicate --date 2026-03-24` sends correct date in API call
- `erpnext_client.py --action submit --date 2026-03-24` uses that date in `build_timesheet_doc` (start_date, end_date, from_time, to_time base)
- Omitting `--date` in erpnext_client.py defaults to today (backward compatible)
- Task creation via `[t]` → `[n]` uses resolved date in the task payload
