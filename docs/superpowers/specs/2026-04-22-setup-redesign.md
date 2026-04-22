# Setup Redesign: userConfig + uv

**Date:** 2026-04-22
**Status:** Approved

## Problem

Five-machine install track record: each machine required manual intervention due to Python environment fragmentation — missing `ensurepip`, distro pip in wrong location, pyenv conflicts. The current setup also requires users to open a separate terminal to run a credential script, which is confusing and platform-dependent.

## Solution

Replace the entire custom install/credential stack with two platform primitives:

- **`uv`** — single static binary, handles Python + venv + deps from `pyproject.toml`. Same behavior on every distro.
- **`userConfig`** in `plugin.json` — Claude Code's native credential dialog (masked input, system keychain storage). No scripts, no TTY hacks.

## Installation Flow (new)

```
1. Install uv  (one-time per machine, same command everywhere)
   curl -LsSf https://astral.sh/uv/install.sh | sh

2. Install plugin
   /plugin install github:neox-d/claude-erpnext-timesheet

3. Claude Code shows config dialog:
   ERPNext URL   _______________
   Username      _______________
   Password      •••••••••••••••   ← masked, stored in system keychain

4. /timesheet
   MCP auto-discovers employee/company on first call.
   Skill prompts for default project and activity via AskUserQuestion.
   Done.
```

No separate terminal. No venv script. No manual pip.

## Architecture

### `plugin.json`

Add `userConfig` with three fields:

| Key | Type | Sensitive |
|---|---|---|
| `url` | string, required | No |
| `username` | string, required | No |
| `password` | string, required | Yes → keychain |

Change MCP server command from `bash run-mcp.sh` to:
```
command: uv
args: ["run", "--project", "${CLAUDE_PLUGIN_ROOT}", "${CLAUDE_PLUGIN_ROOT}/skills/timesheet/mcp_server.py"]
```

`uv run` reads `pyproject.toml`, creates a managed venv on first run (~5 sec), instant cache hits every run after. No stamp file, no venv management code needed.

### `mcp_server.py`

**Credentials source changes:** all three env vars (`CLAUDE_PLUGIN_OPTION_url`, `CLAUDE_PLUGIN_OPTION_username`, `CLAUDE_PLUGIN_OPTION_password`) replace config file reads. Decryption logic removed — Claude Code owns credential storage.

**`checkConfig` tool (restored):** No circular dependency with the new approach since uv handles startup. On call:
1. Check env vars present → if not, return `{ configured: false, reason: "credentials_missing" }`
2. Check `~/.claude/timesheet.json` exists → if not, call ERPNext `discover()`, write file
3. If credentials invalid → return `{ configured: false, reason: "auth_failed" }`
4. Return full config: `{ configured: true, username, url, work_hours, project, default_activity, employee, company, _projects, _activity_types }`

**`~/.claude/timesheet.json`** stores only non-credentials:
`employee`, `company`, `project`, `default_activity`, `work_hours`, `start_time`, `timezone`, `_projects`, `_activity_types`

All crypto code (`encrypt_password`, `decrypt_password`) removed.

### `SKILL.md` — Step 0

Replaces direct file read with `checkConfig` MCP call:

- `credentials_missing` → "Your ERPNext credentials aren't configured. Run `/plugin config erpnext-timesheet` to enter them." Stop.
- `auth_failed` → "Authentication failed. Run `/plugin config erpnext-timesheet` to update your credentials." Stop.
- `project` or `default_activity` missing → `AskUserQuestion` with `_projects`/`_activity_types` → `updateSettings`
- Otherwise → build `STATUS` from response, announce, proceed to Step 1

## Files Deleted

| Path | Replaced by |
|---|---|
| `hooks/hooks-handlers/run-mcp.sh` | `uv run` in `plugin.json` |
| `hooks/hooks-handlers/session-start.sh` | `userConfig` in `plugin.json` |
| `hooks/hooks.json` | — |
| `hooks/` directory | — |
| `skills/timesheet/scripts/timesheet_setup.py` | `userConfig` dialog |
| `skills/timesheet/scripts/crypto.py` | Keychain storage |
| `skills/timesheet/scripts/set_password.py` | `userConfig` dialog |
| `skills/timesheet/scripts/select_defaults.py` | `AskUserQuestion` in skill |
| `skills/timesheet/scripts/__init__.py` | — |
| `config-template.json` | `userConfig` schema in `plugin.json` |

## Files Modified

| Path | Changes |
|---|---|
| `plugin.json` | Add `userConfig`; change MCP command to `uv run` |
| `mcp_server.py` | Read credentials from env vars; restore `checkConfig`; remove crypto |
| `SKILL.md` | Rewrite Step 0 to use `checkConfig` MCP tool |

## Files Unchanged

| Path | Note |
|---|---|
| `pyproject.toml` | Already correct; source of truth for deps |
| All other MCP tools | `readHistory`, `listTasks`, `checkExisting`, `submitTimesheet`, `createTask`, `updateSettings`, `listProjects` |

## Credential Update Flow

If the user's ERPNext password changes or they need to reconfigure:

```
/plugin config erpnext-timesheet
```

Claude Code reopens the config dialog. Keychain entry is updated. No re-install needed.

## Open Questions for Implementation

- Verify exact command to re-open userConfig dialog (`/plugin config` or other)
- Confirm `${CLAUDE_PLUGIN_ROOT}` substitution works in `uv run --project` arg
- Confirm `CLAUDE_PLUGIN_OPTION_*` env vars are set before MCP server process starts
