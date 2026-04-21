#!/usr/bin/env bash
# Installs/updates the timesheet-setup command on session start.
# - Creates a venv with required dependencies
# - Writes ~/.local/bin/timesheet-setup pointing to the current plugin version
# - Uses a stamp file inside the venv to skip work when already up-to-date

VENV_DIR="$HOME/.claude/timesheet-venv"
STAMP_FILE="$VENV_DIR/.stamp"
BIN_DIR="$HOME/.local/bin"
SETUP_SCRIPT="${CLAUDE_PLUGIN_ROOT}/skills/timesheet/scripts/timesheet_setup.py"
VENV_PYTHON="$VENV_DIR/bin/python3"

# Read current plugin version from plugin.json
PLUGIN_VERSION=$(python3 -c "import json; print(json.load(open('${CLAUDE_PLUGIN_ROOT}/.claude-plugin/plugin.json'))['version'])" 2>/dev/null || echo "unknown")

# Fast path: stamp matches current version and launcher exists — nothing to do
if [ -f "$STAMP_FILE" ] && [ "$(cat "$STAMP_FILE")" = "$PLUGIN_VERSION" ] && [ -f "$BIN_DIR/timesheet-setup" ]; then
    exit 0
fi

# Create venv if missing
if [ ! -d "$VENV_DIR" ]; then
    if ! python3 -m venv "$VENV_DIR" 2>/dev/null; then
        exit 1
    fi
fi

# Install deps if not already in the venv's own site-packages
venv_site="$VENV_DIR/lib/$(ls "$VENV_DIR/lib" 2>/dev/null | head -1)/site-packages"
if [ ! -d "$venv_site/requests" ] || [ ! -d "$venv_site/cryptography" ] || [ ! -d "$venv_site/mcp" ]; then
    if ! "$VENV_DIR/bin/pip" install --quiet requests cryptography "mcp[cli]" 2>/dev/null; then
        exit 1
    fi
fi

mkdir -p "$BIN_DIR"
printf '#!/usr/bin/env bash\nexec "%s" "%s" "$@"\n' "$VENV_PYTHON" "$SETUP_SCRIPT" > "$BIN_DIR/timesheet-setup"
chmod +x "$BIN_DIR/timesheet-setup"
echo "$PLUGIN_VERSION" > "$STAMP_FILE"
