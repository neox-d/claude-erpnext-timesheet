#!/usr/bin/env bash
# Installs/updates the timesheet-setup command on every session start.
# - Creates a venv with required dependencies
# - Writes ~/.local/bin/timesheet-setup pointing to the current plugin version
# - Warns Claude if ~/.local/bin is not on PATH so it can inform the user

VENV_DIR="$HOME/.claude/timesheet-venv"
BIN_DIR="$HOME/.local/bin"
SETUP_SCRIPT="${CLAUDE_PLUGIN_ROOT}/skills/timesheet/scripts/timesheet_setup.py"
VENV_PYTHON="$VENV_DIR/bin/python3"

# Create venv if missing
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR" >/dev/null 2>&1
fi

# Install deps if any are missing
if ! "$VENV_DIR/bin/python3" -c "import mcp, requests, cryptography" >/dev/null 2>&1; then
    "$VENV_DIR/bin/pip" install --quiet requests cryptography "mcp[cli]" >/dev/null 2>&1 || true
fi

# Write the launcher — always overwrite so the path stays current after plugin upgrades
mkdir -p "$BIN_DIR"
printf '#!/usr/bin/env bash\nexec "%s" "%s" "$@"\n' "$VENV_PYTHON" "$SETUP_SCRIPT" > "$BIN_DIR/timesheet-setup"
chmod +x "$BIN_DIR/timesheet-setup"

# Warn if ~/.local/bin is not on PATH
if [[ ":${PATH}:" != *":${BIN_DIR}:"* ]]; then
    cat << 'EOF'
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "WARNING for Claude: ~/.local/bin is not on the user's PATH. The `timesheet-setup` command has been installed there but the user won't be able to run it until they add it to their PATH. If the timesheet skill needs to guide the user through setup, also tell them to run: echo 'export PATH=\"$HOME/.local/bin:$PATH\"' >> ~/.bashrc && source ~/.bashrc (or ~/.zshrc if using zsh). They only need to do this once."
  }
}
EOF
fi
