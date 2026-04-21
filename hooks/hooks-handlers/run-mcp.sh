#!/usr/bin/env bash
# Starts the MCP server.
# session-start.sh owns setup on the fast path (stamp file, skip if up-to-date).
# This script installs the venv and packages as a fallback for the first boot,
# since run-mcp.sh runs before the SessionStart hook fires.

VENV_DIR="$HOME/.claude/timesheet-venv"
PLUGIN_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
MCP_SERVER="$PLUGIN_ROOT/skills/timesheet/mcp_server.py"

if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR" >/dev/null 2>&1 || exit 1
fi

venv_site="$VENV_DIR/lib/$(ls "$VENV_DIR/lib" 2>/dev/null | head -1)/site-packages"

if [ ! -d "$venv_site/requests" ] || [ ! -d "$venv_site/cryptography" ] || [ ! -d "$venv_site/mcp" ]; then
    "$VENV_DIR/bin/pip" install --quiet requests cryptography "mcp[cli]" >/dev/null 2>&1 || exit 1
fi

exec "$VENV_DIR/bin/python3" "$MCP_SERVER"
