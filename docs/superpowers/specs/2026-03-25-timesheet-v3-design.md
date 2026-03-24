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

When `~/.claude/timesheet.json` exists, Step 0 presents the current identity and offers to reconfigure before proceeding:

```
<username> @ <url>. [Enter] to continue, [r] to reconfigure.
```

- **Enter** — skip to Step 1 (existing behavior)
- **r** — run the setup wizard (same flow as first-time setup), overwriting `~/.claude/timesheet.json` when confirmed

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
- The mtime pre-filter uses `mtime.date() < target_date` (relaxed from `< today` to allow past files)
- Message timestamp filter uses `target_date` instead of today

### Script changes: `erpnext_client.py`

Add `--date YYYY-MM-DD` argument to the `check-duplicate` and `submit` actions. When omitted, defaults to today (backward compatible).

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
| `parse_logs.py` | Edit | Add `--date` flag |
| `erpnext_client.py` | Edit | Add `--date` flag to check-duplicate and submit |
| Tests | Edit | Update/add tests for `--date` in both scripts |

---

## Testing

- `parse_logs.py --date 2026-03-24` returns messages from that date (existing fixture covers this with adjustment)
- `erpnext_client.py --action check-duplicate --date 2026-03-24` sends correct date in API call
- `erpnext_client.py --action submit --date 2026-03-24` uses that date in submitted timesheet
- Omitting `--date` keeps existing behaviour (backward compatible)
