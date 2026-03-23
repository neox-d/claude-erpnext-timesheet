#!/usr/bin/env bash
# Manual install helper for claude-erpnext-timesheet.
# Run once after cloning: bash install.sh

set -euo pipefail

PLUGIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$HOME/.claude/skills/timesheet"
SETTINGS="$HOME/.claude/settings.json"

echo "Installing claude-erpnext-timesheet from $PLUGIN_DIR"

# 1. Symlink skill
mkdir -p "$SKILL_DIR"
ln -sf "$PLUGIN_DIR/skills/timesheet/SKILL.md" "$SKILL_DIR/SKILL.md"
echo "  Skill linked -> $SKILL_DIR/SKILL.md"

# 2. Patch settings.json with CLAUDE_PLUGIN_ROOT
if [ ! -f "$SETTINGS" ]; then
  echo '{}' > "$SETTINGS"
fi

python3 - "$SETTINGS" "$PLUGIN_DIR" <<'EOF'
import json, sys
settings_path, plugin_root = sys.argv[1], sys.argv[2]
with open(settings_path) as f:
    settings = json.load(f)
settings.setdefault("env", {})["CLAUDE_PLUGIN_ROOT"] = plugin_root
with open(settings_path, "w") as f:
    json.dump(settings, f, indent=2)
    f.write("\n")
EOF
echo "  CLAUDE_PLUGIN_ROOT set in $SETTINGS"

# 3. Install Python dependencies
pip install --quiet . 2>/dev/null || pip3 install --quiet .
echo "  Python dependencies installed"

echo ""
echo "Done! Run /timesheet in Claude Code to get started."
