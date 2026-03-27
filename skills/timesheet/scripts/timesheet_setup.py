"""Interactive terminal setup CLI for erpnext-timesheet."""
import getpass
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import requests

from mcp_server import discover, write_config
from scripts.crypto import encrypt_password


def main():
    while True:
        url = input("ERPNext URL: ").strip()
        username = input("Username: ").strip()
        password = getpass.getpass("Password: ")

        try:
            result = discover(url, username, password)
        except (requests.HTTPError, ValueError) as e:
            print(f"Error: {e}")
            continue
        except (ConnectionError, requests.exceptions.Timeout) as e:
            print(f"Connection error: {e}")
            continue

        print(f"\nFull name:   {result['full_name']}")
        print(f"Employee ID: {result['employee']}")
        print(f"Company:     {result['company']}")
        confirm = input("\nIs this the right account? (y/n): ").strip().lower()
        if confirm == "n":
            continue

        projects = result.get("projects", [])
        print("\nAvailable projects:")
        for i, p in enumerate(projects, 1):
            print(f"  {i}. {p}")
        if result.get("projects_truncated"):
            print("  (list truncated — more projects exist)")
        first_project = projects[0] if projects else ""
        raw = input(f"Default project [{first_project}]: ").strip()
        project = raw if raw else first_project

        activity_types = result.get("activity_types", [])
        print("\nAvailable activity types:")
        for i, a in enumerate(activity_types, 1):
            print(f"  {i}. {a}")
        if result.get("activity_types_truncated"):
            print("  (list truncated — more activity types exist)")
        first_activity = activity_types[0] if activity_types else ""
        raw = input(f"Default activity type [{first_activity}]: ").strip()
        default_activity = raw if raw else first_activity

        raw = input("Working hours per day [8]: ").strip()
        work_hours = float(raw) if raw else 8.0

        raw = input("Workday start time [09:00]: ").strip()
        start_time = raw if raw else "09:00"

        detected_tz = "UTC"
        try:
            detected_tz = subprocess.check_output(
                ["timedatectl", "show", "--property=Timezone", "--value"],
                text=True,
            ).strip() or "UTC"
        except Exception:
            detected_tz = "UTC"

        raw = input(f"Timezone [{detected_tz}]: ").strip()
        timezone = raw if raw else detected_tz

        config = {
            "url": url,
            "username": username,
            "password": encrypt_password(password),
            "employee": result["employee"],
            "company": result["company"],
            "project": project,
            "default_activity": default_activity,
            "work_hours": work_hours,
            "start_time": start_time,
            "timezone": timezone,
        }

        config_path = str(Path.home() / ".claude" / "timesheet.json")
        write_config(config, config_path)
        print("Config saved to ~/.claude/timesheet.json")
        break


if __name__ == "__main__":
    main()
