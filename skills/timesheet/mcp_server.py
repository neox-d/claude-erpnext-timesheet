import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import calendar
import json
import re
import requests
from datetime import date as date_type, datetime, timedelta
from urllib.parse import quote

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("erpnext-timesheet")

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo  # type: ignore

from scripts.crypto import decrypt_password, encrypt_password


# ---------------------------------------------------------------------------
# ERPNext client (from scripts/erpnext_client.py)
# ---------------------------------------------------------------------------

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


def build_timesheet_doc(config: dict, entries: list, date_str: str = None) -> dict:
    if date_str:
        base = datetime.strptime(date_str, "%Y-%m-%d")
    else:
        base = datetime.today()
    today = base.strftime("%Y-%m-%d")
    start_time_str = config.get("start_time", "09:00")
    h, m = map(int, start_time_str.split(":"))
    current = base.replace(hour=h, minute=m, second=0, microsecond=0)

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


# ---------------------------------------------------------------------------
# Log-parsing logic (from scripts/parse_logs.py)
# ---------------------------------------------------------------------------

def _validate_config_fields(config: dict) -> list:
    required = ["url", "username", "password", "employee", "company",
                "project", "default_activity", "work_hours"]
    errors = []
    for field in required:
        if not config.get(field) and config.get(field) != 0:
            errors.append(f"Missing required field: {field}")

    wh = config.get("work_hours")
    if wh is not None:
        try:
            if float(wh) <= 0:
                errors.append("work_hours must be a positive number")
        except (TypeError, ValueError):
            errors.append("work_hours must be a number")

    st = config.get("start_time")
    if st:
        if not re.match(r"^\d{2}:\d{2}$", str(st)):
            errors.append("start_time must be in HH:MM format")

    return errors


def get_timezone(config: dict):
    tz_name = config.get("timezone")
    if tz_name:
        return ZoneInfo(tz_name)
    return None


def parse_content_blocks(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        return " ".join(filter(None, parts)).strip()
    return ""


def get_today_messages(tz=None, target_date=None) -> list:
    projects_dir = Path.home() / ".claude" / "projects"
    if not projects_dir.exists():
        return []

    if target_date is None:
        if tz is not None:
            target_date = datetime.now(tz).date()
        else:
            target_date = date_type.today()
    messages = []

    for project_dir in projects_dir.iterdir():
        if not project_dir.is_dir():
            continue
        for jsonl_file in project_dir.glob("*.jsonl"):
            # mtime pre-filter: skip files modified AFTER target_date
            # (they can't contain messages from that date)
            if tz is not None:
                mtime = datetime.fromtimestamp(jsonl_file.stat().st_mtime, tz=tz).date()
            else:
                mtime = datetime.fromtimestamp(jsonl_file.stat().st_mtime).date()
            if mtime > target_date:
                continue

            try:
                for line in jsonl_file.read_text(errors="replace").splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    if entry.get("type") not in ("user", "assistant"):
                        continue

                    ts_str = entry.get("timestamp", "")
                    if not ts_str:
                        continue

                    ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    ts_local = ts.astimezone(tz) if tz else ts.astimezone()

                    if ts_local.date() != target_date:
                        continue

                    msg = entry.get("message", {})
                    content = msg.get("content", "")
                    text = parse_content_blocks(content)
                    if not text:
                        continue

                    messages.append({
                        "role": entry["type"],
                        "text": text[:500],
                        "cwd": entry.get("cwd", ""),
                        "timestamp": ts_local.isoformat(),
                    })
            except Exception:
                continue

    return sorted(messages, key=lambda m: m["timestamp"])


# ---------------------------------------------------------------------------
# Task-management logic (from scripts/task_manager.py)
# ---------------------------------------------------------------------------

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


def _get_tasks_from_erpnext(config: dict, project: str) -> list:
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
            "fields": json.dumps(["name", "subject", "status", "exp_end_date"]),
            "limit": 50,
        },
    )
    resp.raise_for_status()
    return resp.json().get("data", [])


def _next_month_end(today: date_type) -> str:
    """Return last calendar day of the month following today, as YYYY-MM-DD."""
    if today.month == 12:
        next_year, next_month = today.year + 1, 1
    else:
        next_year, next_month = today.year, today.month + 1
    last_day = calendar.monthrange(next_year, next_month)[1]
    return date_type(next_year, next_month, last_day).isoformat()


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


def _create_task_in_erpnext(config: dict, task_input: dict) -> tuple[str, list[str]]:
    """
    Create a task in ERPNext. Returns (task_name, notes).
    notes is a list of informational strings (e.g. about project extension).
    Auto-extends project end date on InvalidDates, then retries once.
    Raises requests.HTTPError on unrecoverable error.
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
        new_end = _next_month_end(date_type.today())
        _extend_project(session, base, doc["project"], new_end)
        notes.append(f"Note: project end date extended to {new_end}")

        # Retry once
        resp = _attempt_create()

    if not resp.ok:
        raise requests.HTTPError(response=resp)

    task_name = resp.json()["data"]["name"]
    return task_name, notes


# ---------------------------------------------------------------------------
# Setup / discover logic (from scripts/setup.py)
# ---------------------------------------------------------------------------

def discover(url: str, username: str, password: str) -> dict:
    """
    Login to ERPNext and discover employee, company, projects, activity types, and full name.
    Returns dict with keys: employee, company, projects, activity_types, full_name.
    Raises requests.HTTPError on login failure.
    Raises ValueError if no employee record found for the user.
    """
    base = url.rstrip("/")
    session = requests.Session()

    # Login
    resp = session.post(f"{base}/api/method/login", data={"usr": username, "pwd": password})
    resp.raise_for_status()

    # Discover employee
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
        params={"fields": json.dumps(["name", "project_name"]), "limit": 50},
    )
    resp.raise_for_status()
    projects = [
        {"id": p["name"], "label": f"{p['name']} — {p['project_name']}" if p.get("project_name") and p["project_name"] != p["name"] else p["name"]}
        for p in resp.json().get("data", [])
    ]

    # Discover activity types
    resp = session.get(
        f"{base}/api/resource/{quote('Activity Type')}",
        params={"fields": json.dumps(["name"]), "limit": 50},
    )
    resp.raise_for_status()
    activity_types = [a["name"] for a in resp.json().get("data", [])]

    # Fetch user's full name for identity confirmation
    encoded_username = quote(username, safe="")
    try:
        resp = session.get(
            f"{base}/api/resource/User/{encoded_username}",
            params={"fields": json.dumps(["full_name"])},
        )
        resp.raise_for_status()
        full_name = resp.json().get("data", {}).get("full_name") or username
    except requests.RequestException:
        full_name = username

    result = {
        "employee": employee,
        "company": company,
        "projects": projects,
        "activity_types": activity_types,
        "full_name": full_name,
    }
    if len(projects) == 50:
        result["projects_truncated"] = True
    if len(activity_types) == 50:
        result["activity_types_truncated"] = True
    return result


def write_config(config: dict, path: str) -> None:
    """Write config dict to JSON file at path. Creates parent directories if needed."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(config, indent=2))


# ---------------------------------------------------------------------------
# MCP tools
# ---------------------------------------------------------------------------

@mcp.tool()
def checkConfig() -> dict:
    """Return the current configuration status of the timesheet plugin."""
    config_path = Path.home() / ".claude" / "timesheet.json"

    if not config_path.exists():
        return {"configured": False, "setup_command": "timesheet-setup"}

    config = json.loads(config_path.read_text())
    return {
        "configured": True,
        "username": config.get("username"),
        "url": config.get("url"),
        "work_hours": config.get("work_hours", 8),
        "project": config.get("project"),
        "default_activity": config.get("default_activity"),
        "setup_command": "timesheet-setup",
    }


@mcp.tool()
def validateConfig() -> dict:
    """Validate the timesheet configuration file."""
    config_path = Path.home() / ".claude" / "timesheet.json"
    if not config_path.exists():
        return {
            "valid": False,
            "errors": ["Config file not found. Run timesheet-setup to set up."],
        }
    config = json.loads(config_path.read_text())
    errors = _validate_config_fields(config)
    if errors:
        return {"valid": False, "errors": errors}
    return {"valid": True, "errors": []}


@mcp.tool()
def readHistory(date: str) -> list:
    """Read Claude conversation messages for the given date (YYYY-MM-DD)."""
    config_path = Path.home() / ".claude" / "timesheet.json"
    tz = None
    if config_path.exists():
        config = json.loads(config_path.read_text())
        tz = get_timezone(config)
    return get_today_messages(tz=tz, target_date=date_type.fromisoformat(date))


@mcp.tool()
def checkExisting(date: str) -> dict:
    """Check whether a timesheet already exists for the given date (YYYY-MM-DD)."""
    config_path = Path.home() / ".claude" / "timesheet.json"
    config = json.loads(config_path.read_text())
    password = decrypt_password(config["password"])
    client = ERPNextClient(config["url"], config["username"], password)
    client.login()
    result = client.check_duplicate(config["employee"], date)
    return {"exists": result}


@mcp.tool()
def submitTimesheet(date: str, entries: list) -> dict:
    """Build and submit a timesheet for the given date (YYYY-MM-DD) with the provided entries."""
    config_path = Path.home() / ".claude" / "timesheet.json"
    config = json.loads(config_path.read_text())
    password = decrypt_password(config["password"])
    client = ERPNextClient(config["url"], config["username"], password)
    client.login()
    doc = build_timesheet_doc(config, entries, date_str=date)
    name = client.create_timesheet(doc)
    client.submit_timesheet(name)
    return {"success": True, "name": name}


@mcp.tool()
def listTasks(project: str) -> list:
    """Return all non-cancelled tasks for the given project."""
    config_path = Path.home() / ".claude" / "timesheet.json"
    config = json.loads(config_path.read_text())
    return _get_tasks_from_erpnext(config, project)


@mcp.tool()
def createTask(subject: str, description: str, project: str, hours: float, date: str) -> dict:
    """Create a task in ERPNext. Auto-extends project end date on InvalidDates errors."""
    config_path = Path.home() / ".claude" / "timesheet.json"
    config = json.loads(config_path.read_text())
    task_input = {
        "subject": subject,
        "description": description,
        "project": project,
        "hours": hours,
        "date": date,
    }
    name, notes = _create_task_in_erpnext(config, task_input)
    return {"name": name, "notes": notes}


@mcp.tool()
def updateSettings(project: str = None, activity_type: str = None,
                   work_hours: float = None, start_time: str = None,
                   timezone: str = None) -> dict:
    """Update one or more config settings. Clears temporary _projects/_activity_types lists."""
    config_path = Path.home() / ".claude" / "timesheet.json"
    config = json.loads(config_path.read_text())

    if project is not None:
        config["project"] = project
    if activity_type is not None:
        config["default_activity"] = activity_type
    if work_hours is not None:
        config["work_hours"] = work_hours
    if start_time is not None:
        config["start_time"] = start_time
    if timezone is not None:
        config["timezone"] = timezone

    # Remove temp keys written by set_password.py
    config.pop("_projects", None)
    config.pop("_activity_types", None)

    config_path.write_text(json.dumps(config, indent=2))
    return {"updated": True}


if __name__ == "__main__":
    mcp.run()
