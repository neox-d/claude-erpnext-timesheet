#!/usr/bin/env python3
"""
ERPNext REST API client for timesheet operations.

Usage:
  python3 erpnext_client.py --config ~/.claude/timesheet.json --action check-duplicate
  python3 erpnext_client.py --config ~/.claude/timesheet.json --action submit --entries-file /tmp/entries.json
"""
import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import requests

from scripts.crypto import decrypt_password


class ERPNextClient:
    def __init__(self, url: str, username: str, password: str):
        self.base_url = url.rstrip("/")
        self.username = username
        self.password = password
        self.session = requests.Session()
        self._authenticated = False

    def login(self):
        resp = self.session.post(
            f"{self.base_url}/api/method/login",
            data={"usr": self.username, "pwd": self.password},
        )
        resp.raise_for_status()
        self._authenticated = True

    def _request(self, method: str, path: str, **kwargs):
        if not self._authenticated:
            self.login()
        resp = self.session.request(method, f"{self.base_url}{path}", **kwargs)
        if resp.status_code in (401, 403):
            self._authenticated = False
            self.login()
            resp = self.session.request(method, f"{self.base_url}{path}", **kwargs)
        resp.raise_for_status()
        return resp.json()

    def check_duplicate(self, employee: str, date_str: str) -> bool:
        result = self._request(
            "GET",
            "/api/resource/Timesheet",
            params={
                "filters": json.dumps([
                    ["start_date", "=", date_str],
                    ["employee", "=", employee],
                ])
            },
        )
        return len(result.get("data", [])) > 0

    def create_timesheet(self, doc: dict) -> str:
        result = self._request("POST", "/api/resource/Timesheet", json=doc)
        return result["data"]["name"]

    def submit_timesheet(self, name: str):
        self._request(
            "PUT",
            f"/api/resource/Timesheet/{name}",
            json={"docstatus": 1},
        )


def build_timesheet_doc(config: dict, entries: list) -> dict:
    now = datetime.today()
    today = now.strftime("%Y-%m-%d")
    start_time_str = config.get("start_time", "09:00")
    h, m = map(int, start_time_str.split(":"))
    current = now.replace(hour=h, minute=m, second=0, microsecond=0)

    time_logs = []
    for entry in entries:
        hours = float(entry["hours"])
        from_time = current.strftime("%Y-%m-%d %H:%M:%S")
        current += timedelta(hours=hours)
        to_time = current.strftime("%Y-%m-%d %H:%M:%S")
        log = {
            "activity_type": entry.get("activity_type", config["default_activity"]),
            "description": entry["description"],
            "hours": hours,
            "from_time": from_time,
            "to_time": to_time,
            "project": config["project"],
        }
        if entry.get("task"):
            log["task"] = entry["task"]
        time_logs.append(log)

    return {
        "employee": config["employee"],
        "company": config["company"],
        "user": config["username"],
        "start_date": today,
        "end_date": today,
        "time_logs": time_logs,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--action", choices=["check-duplicate", "submit"], required=True)
    parser.add_argument("--entries", help="JSON array of approved entries (inline)")
    parser.add_argument("--entries-file", help="Path to JSON file with approved entries (preferred)")
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.exists():
        print(f"ERROR: Config file not found: {args.config}", file=sys.stderr)
        sys.exit(1)
    try:
        config = json.loads(config_path.read_text())
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON in config: {e}", file=sys.stderr)
        sys.exit(1)
    client = ERPNextClient(config["url"], config["username"], decrypt_password(config["password"]))
    today = datetime.today().strftime("%Y-%m-%d")

    if args.action == "check-duplicate":
        exists = client.check_duplicate(config["employee"], today)
        print(json.dumps({"exists": exists}))

    elif args.action == "submit":
        if args.entries_file:
            try:
                entries = json.loads(Path(args.entries_file).read_text())
            except (OSError, json.JSONDecodeError) as e:
                print(f"ERROR: Could not read entries file: {e}", file=sys.stderr)
                sys.exit(1)
        elif args.entries:
            entries = json.loads(args.entries)
        else:
            print("ERROR: --entries-file or --entries required for submit action", file=sys.stderr)
            sys.exit(1)
        doc = build_timesheet_doc(config, entries)
        name = client.create_timesheet(doc)
        client.submit_timesheet(name)
        print(json.dumps({"success": True, "name": name}))


if __name__ == "__main__":
    main()
