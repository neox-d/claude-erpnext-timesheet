#!/usr/bin/env python3
"""
ERPNext setup wizard helper.

Usage:
  python3 setup.py --url URL --username USER --password PASS --action discover
  python3 setup.py --action write-config --config-data '{"url": ...}'
"""
import argparse
import json
import sys
from pathlib import Path

import requests


def discover(url: str, username: str, password: str) -> dict:
    """
    Login to ERPNext and discover employee, company, projects, and activity types.
    Returns dict with keys: employee, company, projects (list), activity_types (list).
    Raises requests.HTTPError on login failure.
    Raises ValueError if no employee record found for the user.
    """
    base = url.rstrip("/")
    session = requests.Session()

    # Login
    resp = session.post(f"{base}/api/method/login", data={"usr": username, "pwd": password})
    resp.raise_for_status()

    # Discover employee (filter by user_id = username)
    resp = session.get(
        f"{base}/api/resource/Employee",
        params={
            "filters": json.dumps([["user_id", "=", username]]),
            "fields": json.dumps(["name", "company"]),
            "limit": 1,
        },
    )
    resp.raise_for_status()
    employees = resp.json().get("data", [])
    if not employees:
        raise ValueError(f"No employee record found for {username}. Ask your ERPNext admin to link your user to an Employee.")
    employee = employees[0]["name"]
    company = employees[0]["company"]

    # Discover projects
    resp = session.get(
        f"{base}/api/resource/Project",
        params={"fields": json.dumps(["name"]), "limit": 50},
    )
    resp.raise_for_status()
    projects = [p["name"] for p in resp.json().get("data", [])]

    # Discover activity types
    resp = session.get(
        f"{base}/api/resource/Activity Type",
        params={"fields": json.dumps(["name"]), "limit": 50},
    )
    resp.raise_for_status()
    activity_types = [a["name"] for a in resp.json().get("data", [])]

    return {
        "employee": employee,
        "company": company,
        "projects": projects,
        "activity_types": activity_types,
    }


def write_config(config: dict, path: str) -> None:
    """Write config dict to JSON file at path."""
    Path(path).write_text(json.dumps(config, indent=2))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--action", choices=["discover", "write-config"], required=True)
    parser.add_argument("--url")
    parser.add_argument("--username")
    parser.add_argument("--password")
    parser.add_argument("--config-data", help="JSON string of config to write")
    parser.add_argument("--config-out", default=str(Path.home() / ".claude" / "timesheet.json"))
    args = parser.parse_args()

    if args.action == "discover":
        for field in ["url", "username", "password"]:
            if not getattr(args, field):
                print(f"ERROR: --{field} required for discover action", file=sys.stderr)
                sys.exit(1)
        try:
            result = discover(args.url, args.username, args.password)
            print(json.dumps(result, indent=2))
        except requests.HTTPError as e:
            print(f"ERROR: Login failed ({e.response.status_code}). Check your URL and credentials.", file=sys.stderr)
            sys.exit(1)
        except ValueError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.action == "write-config":
        if not args.config_data:
            print("ERROR: --config-data required for write-config action", file=sys.stderr)
            sys.exit(1)
        try:
            config = json.loads(args.config_data)
        except json.JSONDecodeError as e:
            print(f"ERROR: Invalid JSON in --config-data: {e}", file=sys.stderr)
            sys.exit(1)
        write_config(config, args.config_out)
        print(f"Config written to {args.config_out}")


if __name__ == "__main__":
    main()
