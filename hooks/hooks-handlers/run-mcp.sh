#!/usr/bin/env bash
# Starts the MCP server. All setup (venv creation, package installation) is
# handled exclusively by the SessionStart hook. This script fails fast if the
# environment isn't ready — start a new Claude session to trigger setup.

VENV_DIR="$HOME/.claude/timesheet-venv"
PLUGIN_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
MCP_SERVER="$PLUGIN_ROOT/skills/timesheet/mcp_server.py"

venv_site="$VENV_DIR/lib/$(ls "$VENV_DIR/lib" 2>/dev/null | head -1)/site-packages"

if [ ! -d "$VENV_DIR" ] || [ ! -d "$venv_site/requests" ] || [ ! -d "$venv_site/cryptography" ] || [ ! -d "$venv_site/mcp" ]; then
    exit 1
fi

exec "$VENV_DIR/bin/python3" "$MCP_SERVER"
