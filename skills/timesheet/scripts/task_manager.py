#!/usr/bin/env python3
"""
ERPNext task and project management.

Usage:
  python3 task_manager.py --config ~/.claude/timesheet.json --action get-tasks --project PROJ-XXXX
  python3 task_manager.py --config ~/.claude/timesheet.json --action create-task --task-file /tmp/task.json
  python3 task_manager.py --config ~/.claude/timesheet.json --action extend-project --project PROJ-XXXX --date YYYY-MM-DD
"""
import argparse
import calendar
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import requests

from scripts.crypto import decrypt_password


def _login(config: dict) -> requests.Session:
    """Create an authenticated session."""
    session = requests.Session()
    base = config["url"].rstrip("/")
    resp = session.post(
        f"{base}/api/method/login",
        data={"usr": config["username"], "pwd": decrypt_password(config["password"])},
    )
    resp.raise_for_status()
    return session


def get_tasks(config: dict, project: str) -> list:
    """Fetch all non-cancelled tasks for a project."""
    base = config["url"].rstrip("/")
    session = _login(config)
    resp = session.get(
        f"{base}/api/resource/Task",
        params={
            "filters": json.dumps([
                ["project", "=", project],
                ["status", "!=", "Cancelled"],
            ]),
            "fields": json.dumps(["name", "subject", "status"]),
            "limit": 50,
        },
    )
    resp.raise_for_status()
    return resp.json().get("data", [])


def _next_month_end(today: date) -> str:
    """Return last calendar day of the month following today, as YYYY-MM-DD."""
    if today.month == 12:
        next_year, next_month = today.year + 1, 1
    else:
        next_year, next_month = today.year, today.month + 1
    last_day = calendar.monthrange(next_year, next_month)[1]
    return date(next_year, next_month, last_day).isoformat()


def _extend_project(session: requests.Session, base: str, project: str, new_date: str) -> None:
    """PUT extend on existing session. Raises HTTPError on failure."""
    resp = session.request(
        "PUT",
        f"{base}/api/resource/Project/{project}",
        json={"expected_end_date": new_date},
    )
    resp.raise_for_status()


def extend_project_end_date(config: dict, project: str, new_date: str) -> dict:
    """Extend a project's expected end date."""
    base = config["url"].rstrip("/")
    session = _login(config)
    _extend_project(session, base, project, new_date)
    return {"success": True}


def create_task(config: dict, task_input: dict) -> tuple[str, list[str]]:
    """
    Create a task in ERPNext. Returns (task_name, notes).
    notes is a list of informational strings (e.g. about project extension).
    Auto-extends project end date on InvalidDates, then retries once.
    Raises SystemExit(1) on unrecoverable error.
    """
    base = config["url"].rstrip("/")
    session = _login(config)
    notes = []

    doc = {
        "subject": task_input["subject"],
        "description": task_input["description"],
        "project": task_input["project"],
        "expected_time": task_input["hours"],
        "exp_start_date": task_input["date"],
        "exp_end_date": task_input["date"],
        "custom_planned_completion_date": task_input["date"],
        "status": "Completed",
    }

    def _attempt_create():
        return session.request("POST", f"{base}/api/resource/Task", json=doc)

    resp = _attempt_create()

    if resp.status_code == 417 and resp.json().get("exc_type") == "InvalidDates":
        # Auto-extend project end date to end of next month
        new_end = _next_month_end(date.today())
        _extend_project(session, base, doc["project"], new_end)
        notes.append(f"Note: project end date extended to {new_end}")

        # Retry once
        resp = _attempt_create()

    if not resp.ok:
        print(f"ERROR: Failed to create task: {resp.text[:300]}", file=sys.stderr)
        sys.exit(1)

    task_name = resp.json()["data"]["name"]
    return task_name, notes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--action", choices=["get-tasks", "create-task", "extend-project"], required=True)
    parser.add_argument("--project")
    parser.add_argument("--task-file")
    parser.add_argument("--date")
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

    try:
        if args.action == "get-tasks":
            if not args.project:
                print("ERROR: --project required for get-tasks", file=sys.stderr)
                sys.exit(1)
            tasks = get_tasks(config, args.project)
            print(json.dumps(tasks))

        elif args.action == "create-task":
            if not args.task_file:
                print("ERROR: --task-file required for create-task", file=sys.stderr)
                sys.exit(1)
            try:
                task_input = json.loads(Path(args.task_file).read_text())
            except (OSError, json.JSONDecodeError) as e:
                print(f"ERROR: Could not read task file: {e}", file=sys.stderr)
                sys.exit(1)
            task_name, notes = create_task(config, task_input)
            for note in notes:
                print(note)
            print(json.dumps({"name": task_name}))

        elif args.action == "extend-project":
            if not args.project or not args.date:
                print("ERROR: --project and --date required for extend-project", file=sys.stderr)
                sys.exit(1)
            result = extend_project_end_date(config, args.project, args.date)
            print(json.dumps(result))

    except requests.HTTPError as e:
        print(f"ERROR: HTTP {e.response.status_code}: {e.response.text[:200]}", file=sys.stderr)
        sys.exit(1)
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
        print("ERROR: Could not connect to ERPNext.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
