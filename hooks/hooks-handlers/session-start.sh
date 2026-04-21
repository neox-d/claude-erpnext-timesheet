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

# Create venv if missing
if [ ! -d "$VENV_DIR" ]; then
    echo "Setting up timesheet environment..." >&2
    if ! python3 -m venv "$VENV_DIR" 2>/dev/null; then
        errors+=("Failed to create Python virtual environment at $VENV_DIR. Make sure python3-venv is installed (e.g. sudo apt install python3-venv on Debian/Ubuntu).")
    else
        messages+=("Created Python environment at $VENV_DIR")
    fi
fi

# Install deps if any are missing
if [ ${#errors[@]} -eq 0 ] && ! "$VENV_PYTHON" -c "import mcp, requests, cryptography" >/dev/null 2>&1; then
    echo "Installing timesheet packages..." >&2
    if "$VENV_DIR/bin/pip" install --quiet requests cryptography "mcp[cli]" 2>/dev/null; then
        if "$VENV_PYTHON" -c "import mcp, requests, cryptography" >/dev/null 2>&1; then
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

# Collect context to surface to Claude
lines=()

if [ ${#errors[@]} -gt 0 ]; then
    for err in "${errors[@]}"; do
        lines+=("Error: $err")
    done
fi

if [ ${#messages[@]} -gt 0 ]; then
    for msg in "${messages[@]}"; do
        lines+=("$msg")
    done
fi

if [[ ":${PATH}:" != *":${BIN_DIR}:"* ]]; then
    lines+=("Note: $BIN_DIR is not on your PATH. To fix, run:")
    lines+=("  echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.bashrc && source ~/.bashrc")
    lines+=("(Use ~/.zshrc instead if you are on zsh. Only needed once.)")
fi

if [ ${#lines[@]} -gt 0 ]; then
    combined=$(printf '%s\n' "${lines[@]}" | sed 's/"/\\"/g' | tr '\n' '|')
    printf '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"%s"}}\n' "$combined"
fi
