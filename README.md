# claude-erpnext-timesheet

A Claude Code skill that automatically fills your daily ERPNext timesheet from your Claude conversation history.

At the end of the day, run `/timesheet` and Claude will:
1. Read your conversations from the day
2. Synthesise billable task entries with descriptions and hours
3. Let you review and edit them in a TUI (add, delete, edit, assign tasks, adjust hours)
4. Submit the approved timesheet to ERPNext

## Requirements

- [Claude Code](https://claude.ai/claude-code) CLI
- ERPNext / Frappe v15 instance with API access
- Python 3.9+ with `requests` installed

## Installation

### As a Claude Code plugin

Add the marketplace (once):
```
/plugin marketplace add neox-d/claude-plugins
```

Then install:
```
/plugin install erpnext-timesheet@neox-d-plugins
```

To update later:
```
/plugin update erpnext-timesheet@neox-d-plugins
```

### Manual Installation

```bash
git clone https://github.com/neox-d/claude-erpnext-timesheet ~/.claude/plugins/cache/erpnext-timesheet
cd ~/.claude/plugins/cache/erpnext-timesheet
bash install.sh
```

The install script:
- Symlinks `skills/timesheet/SKILL.md` into `~/.claude/skills/timesheet/`
- Sets `CLAUDE_PLUGIN_ROOT` in `~/.claude/settings.json`
- Runs `pip install .` to install Python dependencies

### First run (setup wizard)

Run `/timesheet` in Claude Code. On first use it will guide you through connecting to your ERPNext instance:

- URL, username, and password
- Identity confirmation (employee, company)
- Default project, activity type, work hours, timezone

Credentials are stored in plaintext at `~/.claude/timesheet.json` — ensure your home directory is appropriately secured.

## Usage

```
/timesheet
```

### TUI options

| Key | Action |
|-----|--------|
| `a` | Approve and submit |
| `e` | Edit an entry (description, hours, activity type, task) |
| `d` | Delete an entry |
| `+` | Add an entry manually |
| `h` | Change total hours for today (redistributes evenly) |
| `t` | Assign an ERPNext task to an entry |
| `q` | Quit without submitting |

### Task assignment (`t`)

Fetches open tasks from your configured project. You can select an existing task or create a new one. If your ERPNext instance requires a task on every timesheet row, Claude will warn you before submitting.

## Project structure

```
scripts/
  erpnext_client.py   — ERPNext REST API client (Timesheet CRUD)
  task_manager.py     — Task and project operations (get, create, extend)
  setup.py            — Login, discovery, config write
  parse_logs.py       — Read today's Claude conversation logs
skills/
  timesheet/
    SKILL.md          — The Claude Code skill definition
tests/                — pytest test suite (48 tests)
config-template.json  — Example config structure
```

## Config file reference (`~/.claude/timesheet.json`)

| Field | Description |
|-------|-------------|
| `url` | ERPNext base URL |
| `username` | Login email |
| `password` | Login password |
| `employee` | Employee docname (e.g. `EMP-0001`) |
| `company` | Company name |
| `project` | Default project for all entries |
| `default_activity` | Default activity type |
| `work_hours` | Expected hours per day (default `8`) |
| `start_time` | Workday start time (default `09:00`) |
| `timezone` | IANA timezone (e.g. `Asia/Kolkata`) |

## License

MIT
