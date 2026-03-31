"""
Arrow-key selector for default project and activity type.
Reads available options from ~/.claude/timesheet.json (_projects, _activity_types).
Prints selected values as JSON to stdout. Interactive display goes to stderr.
"""
import json
import sys
import termios
import tty
from pathlib import Path


def arrow_select(options: list, labels: list, title: str, current_default: str = "") -> str:
    """Select from options (IDs), displaying labels. Returns selected option ID."""
    idx = 0
    if current_default in options:
        idx = options.index(current_default)

    n = len(options)

    def render(first=False):
        if not first:
            sys.stderr.write(f"\033[{n + 1}A")
        sys.stderr.write(f"\r{title}\n")
        for i, label in enumerate(labels):
            marker = "  \033[32m›\033[0m " if i == idx else "    "
            sys.stderr.write(f"\r{marker}{label}\033[K\n")
        sys.stderr.flush()

    render(first=True)

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        while True:
            ch = sys.stdin.read(1)
            if ch == "\x1b":
                ch2 = sys.stdin.read(1)
                ch3 = sys.stdin.read(1)
                key = f"\x1b{ch2}{ch3}"
            else:
                key = ch

            if key in ("\r", "\n"):
                sys.stderr.write("\n")
                return options[idx]
            elif key == "\x03":
                raise KeyboardInterrupt
            elif key == "\x1b[A" and idx > 0:
                idx -= 1
            elif key == "\x1b[B" and idx < n - 1:
                idx += 1
            else:
                continue

            render()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def main():
    config_path = Path.home() / ".claude" / "timesheet.json"
    config = json.loads(config_path.read_text())

    projects = config.get("_projects", [])  # list of {"id": ..., "label": ...}
    activity_types = config.get("_activity_types", [])  # list of strings
    result = {}

    if projects:
        proj_ids = [p["id"] for p in projects]
        proj_labels = [p["label"] for p in projects]
        result["project"] = arrow_select(proj_ids, proj_labels, "Default Project:", config.get("project", ""))

    sys.stderr.write("\n")

    if activity_types:
        result["activity_type"] = arrow_select(activity_types, activity_types, "Default Activity:", config.get("default_activity", ""))

    sys.stderr.write("\n")
    print(json.dumps(result))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.stderr.write("\nCancelled.\n")
        sys.exit(1)
