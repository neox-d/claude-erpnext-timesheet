# claude-erpnext-timesheet

A Claude Code plugin that automatically fills your daily ERPNext timesheet from your Claude conversation history.

Run `/timesheet` at the end of the day and Claude will:
1. Read your conversations from the day
2. Synthesise billable task entries with descriptions and hours
3. Let you review and edit them (add, delete, edit, assign tasks, adjust hours)
4. Submit the approved timesheet to ERPNext

## Requirements

- [Claude Code](https://claude.ai/claude-code) CLI
- [uv](https://docs.astral.sh/uv/) — install once per machine:
  ```
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```
- ERPNext / Frappe v15 instance with API access

## Installation

```
/plugin install erpnext-timesheet@neox-d-plugins
```

Claude Code will prompt for your ERPNext credentials:

```
ERPNext URL   _______________
Username      _______________
Password      •••••••••••••••
```

Credentials are stored securely in your system keychain — never in a plain text file.

## First run

```
/timesheet
```

On first use, Claude connects to your ERPNext instance and prompts you to select a default project and activity type. After that, `/timesheet` runs without any setup.

## Usage

```
/timesheet              — fill today's timesheet
/timesheet yesterday    — fill yesterday's
/timesheet 2026-04-21  — fill a specific date
```

## Updating the plugin

```
! claude plugin update erpnext-timesheet@neox-d-plugins
```

## Updating credentials

If your ERPNext password changes, run `/plugin` → Installed → erpnext-timesheet → Configure Options.

## License

MIT
