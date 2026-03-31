"""
Credential setup for erpnext-timesheet.
Only prompts for username and password — everything else is handled in Claude Code.
"""
import getpass
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import requests

from mcp_server import discover, write_config
from scripts.crypto import encrypt_password


def detect_timezone() -> str:
    try:
        return subprocess.check_output(
            ["timedatectl", "show", "--property=Timezone", "--value"],
            text=True,
        ).strip() or "UTC"
    except Exception:
        return "UTC"


def main():
    config_path = Path.home() / ".claude" / "timesheet.json"
    existing = {}
    if config_path.exists():
        try:
            existing = json.loads(config_path.read_text())
        except Exception:
            pass

    url = existing.get("url", "").rstrip("/")
    if not url:
        url = input("ERPNext URL: ").strip().rstrip("/")

    print(f"URL: {url}")
    username = input("User (Email): ").strip()
    password = getpass.getpass("Password: ")

    print("\nConnecting…")
    try:
        result = discover(url, username, password)
    except requests.HTTPError as e:
        print(f"Login failed: {e}")
        sys.exit(1)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except (ConnectionError, requests.exceptions.Timeout) as e:
        print(f"Connection error: {e}")
        sys.exit(1)

    projects = result.get("projects", [])
    activity_types = result.get("activity_types", [])

    config = {
        "url": url,
        "username": username,
        "password": encrypt_password(password),
        "employee": result["employee"],
        "company": result["company"],
        # Keep existing defaults if reconfiguring, otherwise use first discovered
        "project": existing.get("project") or (projects[0]["id"] if projects else ""),
        "default_activity": existing.get("default_activity") or (activity_types[0] if activity_types else ""),
        "work_hours": existing.get("work_hours", 8.0),
        "start_time": existing.get("start_time", "09:00"),
        "timezone": existing.get("timezone") or detect_timezone(),
        # Temp: available options for Claude Code to present as selectors
        "_projects": projects,
        "_activity_types": activity_types,
    }

    write_config(config, str(config_path))
    print(f"\nSaved. Return to Claude Code to finish setup.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nCancelled.")
        sys.exit(0)
