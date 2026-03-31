"""Interactive terminal setup CLI for erpnext-timesheet."""
DEFAULT_URL = "https://erp.sanskartechnolab.com/"

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
        raw = input(f"ERPNext URL [{DEFAULT_URL}]: ").strip()
        url = raw if raw else DEFAULT_URL
        username = input("User (Email): ").strip()
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

        detected_tz = "UTC"
        try:
            detected_tz = subprocess.check_output(
                ["timedatectl", "show", "--property=Timezone", "--value"],
                text=True,
            ).strip() or "UTC"
        except Exception:
            detected_tz = "UTC"

        config = {
            "url": url,
            "username": username,
            "password": encrypt_password(password),
            "employee": result["employee"],
            "company": result["company"],
            "work_hours": 8.0,
            "start_time": "09:00",
            "timezone": detected_tz,
            "_projects": result.get("projects", []),
            "_activity_types": result.get("activity_types", []),
        }

        config_path = str(Path.home() / ".claude" / "timesheet.json")
        write_config(config, config_path)
        print("\nCredentials saved. Return to Claude to finish setup.")
        break


if __name__ == "__main__":
    main()
