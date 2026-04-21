#!/usr/bin/env bash
# Installs/updates the timesheet-setup command on session start.
# - Creates a venv with required dependencies
# - Writes ~/.local/bin/timesheet-setup pointing to the current plugin version
# - Reports installation progress and any errors as additionalContext for Claude
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

messages=()
errors=()
fresh_venv=0

# Create venv if missing
if [ ! -d "$VENV_DIR" ]; then
    if ! python3 -m venv "$VENV_DIR" 2>/dev/null; then
        errors+=("Failed to create Python virtual environment at $VENV_DIR. Make sure python3-venv is installed (e.g. sudo apt install python3-venv on Debian/Ubuntu).")
    else
        fresh_venv=1
        messages+=("Created Python environment at $VENV_DIR")
    fi
fi

# Install deps: always on a fresh venv; otherwise only if not in the venv's own site-packages
venv_site="$VENV_DIR/lib/$(ls "$VENV_DIR/lib" 2>/dev/null | head -1)/site-packages"
needs_install=0
if [ "$fresh_venv" -eq 1 ]; then
    needs_install=1
elif [ ${#errors[@]} -eq 0 ] && { [ ! -d "$venv_site/requests" ] || [ ! -d "$venv_site/cryptography" ] || [ ! -d "$venv_site/mcp" ]; }; then
    needs_install=1
fi

if [ ${#errors[@]} -eq 0 ] && [ "$needs_install" -eq 1 ]; then
    if "$VENV_DIR/bin/pip" install --quiet requests cryptography "mcp[cli]" 2>/dev/null; then
        if [ -d "$venv_site/requests" ] && [ -d "$venv_site/cryptography" ] && [ -d "$venv_site/mcp" ]; then
            messages+=("Installed packages: requests, cryptography, mcp[cli]")
        else
            errors+=("Packages still missing after install. Run manually: $VENV_DIR/bin/pip install requests cryptography 'mcp[cli]'")
        fi
    else
        errors+=("Failed to install packages. Check your internet connection, then run: $VENV_DIR/bin/pip install requests cryptography 'mcp[cli]'")
    fi
fi

# Write the launcher and stamp — only reached when something changed
if [ ${#errors[@]} -eq 0 ]; then
    mkdir -p "$BIN_DIR"
    printf '#!/usr/bin/env bash\nexec "%s" "%s" "$@"\n' "$VENV_PYTHON" "$SETUP_SCRIPT" > "$BIN_DIR/timesheet-setup"
    chmod +x "$BIN_DIR/timesheet-setup"
    echo "$PLUGIN_VERSION" > "$STAMP_FILE"
    messages+=("Installed timesheet-setup to $BIN_DIR/timesheet-setup")
fi

# Output additionalContext for Claude — only when something happened
lines=()
for err in "${errors[@]}"; do lines+=("Error: $err"); done
for msg in "${messages[@]}"; do lines+=("$msg"); done
if [[ ":${PATH}:" != *":${BIN_DIR}:"* ]]; then
    lines+=("Note: $BIN_DIR is not on your PATH. To use timesheet-setup, run:")
    lines+=("  echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.bashrc && source ~/.bashrc")
    lines+=("(Use ~/.zshrc if on zsh. Only needed once.)")
fi

if [ ${#lines[@]} -gt 0 ]; then
    combined=$(printf '%s\n' "${lines[@]}" | sed 's/\\/\\\\/g; s/"/\\"/g' | awk '{printf "%s\\n", $0}')
    printf '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"%s"}}\n' "$combined"
fi
