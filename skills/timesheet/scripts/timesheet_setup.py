"""Interactive terminal setup CLI for erpnext-timesheet."""
import getpass
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import requests
    import cryptography  # noqa: F401
    import mcp  # noqa: F401
except ImportError as e:
    venv_pip = Path(__file__).parents[4] / ".claude" / "timesheet-venv" / "bin" / "pip"
    print(f"Error: required package missing — {e}")
    print(f"Run: {venv_pip} install requests cryptography 'mcp[cli]'")
    sys.exit(1)

from mcp_server import discover, write_config
from scripts.crypto import encrypt_password

DEFAULT_URL = "https://erpnext.example.com/"


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

    while True:
        default_url = existing.get("url") or DEFAULT_URL
        raw = input(f"ERPNext URL [{default_url}]: ").strip()
        url = raw if raw else default_url
        username = input("User (Email): ").strip()
        password = getpass.getpass("Password: ")

        print("Connecting to ERPNext...", end="", flush=True)
        try:
            result = discover(url, username, password)
            print(" done.")
        except (requests.HTTPError, ValueError) as e:
            print(f"\nError: {e}")
            continue
        except (ConnectionError, requests.exceptions.Timeout) as e:
            print(f"\nConnection error: {e}")
            continue

        print(f"\nFull name:   {result['full_name']}")
        print(f"Employee ID: {result['employee']}")
        print(f"Company:     {result['company']}")
        confirm = input("\nIs this the right account? (y/n): ").strip().lower()
        if confirm == "n":
            continue

        projects = result.get("projects", [])
        activity_types = result.get("activity_types", [])

        config = {
            "url": url,
            "username": username,
            "password": encrypt_password(password),
            "employee": result["employee"],
            "company": result["company"],
            "project": existing.get("project", ""),
            "default_activity": existing.get("default_activity", ""),
            "work_hours": existing.get("work_hours", 8.0),
            "start_time": existing.get("start_time", "09:00"),
            "timezone": existing.get("timezone") or detect_timezone(),
            "_projects": projects,
            "_activity_types": activity_types,
        }

        print("Saving credentials...", end="", flush=True)
        write_config(config, str(config_path))
        print(" done.")
        print("\nSetup complete. Return to Claude and re-run /timesheet.")
        break


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nCancelled.")
        sys.exit(0)
