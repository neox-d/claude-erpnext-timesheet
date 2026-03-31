#!/usr/bin/env bash
# Bootstraps the venv if missing, then runs the MCP server from it.
# This ensures the MCP server always uses the same isolated dependencies
# as timesheet-setup, regardless of what's on the system python.

VENV_DIR="$HOME/.claude/timesheet-venv"
PLUGIN_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
MCP_SERVER="$PLUGIN_ROOT/skills/timesheet/mcp_server.py"

if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR" >/dev/null 2>&1
fi

if ! "$VENV_DIR/bin/python3" -c "import mcp, requests, cryptography" >/dev/null 2>&1; then
    "$VENV_DIR/bin/pip" install --quiet requests cryptography "mcp[cli]" >/dev/null 2>&1
fi

exec "$VENV_DIR/bin/python3" "$MCP_SERVER"
