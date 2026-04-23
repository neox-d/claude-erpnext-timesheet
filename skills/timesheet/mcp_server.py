import atexit
import calendar
import json
import os
import re
import signal
import sys
from datetime import date as date_type, datetime, timedelta
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).parent))

import requests
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("erpnext-timesheet")

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo  # type: ignore


# ---------------------------------------------------------------------------
# ERPNext client
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

    def logout(self):
        if self._authenticated:
            try:
                self.session.get(f"{self.base_url}/api/method/logout")
            except Exception:
                pass
        self._authenticated = False

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
            params={"filters": json.dumps([
                ["start_date", "=", date_str],
                ["employee", "=", employee],
            ])}
        )
        return len(result.get("data", [])) > 0

    def create_timesheet(self, doc: dict) -> str:
        result = self._request("POST", "/api/resource/Timesheet", json=doc)
        return result["data"]["name"]

    def submit_timesheet(self, name: str):
        self._request("PUT", f"/api/resource/Timesheet/{name}", json={"docstatus": 1})

    def list_tasks(self, project: str) -> list:
        tasks = []
        page_size = 100
        start = 0
        while True:
            result = self._request(
                "GET",
                "/api/resource/Task",
                params={
                    "filters": json.dumps([
                        ["project", "=", project],
                        ["status", "not in", ["Completed", "Cancelled"]],
                    ]),
                    "fields": json.dumps([
                        "name", "subject", "status", "exp_end_date",
                        "is_group", "parent_task",
                    ]),
                    "limit_page_length": page_size,
                    "limit_start": start,
                },
            )
            page = result.get("data", [])
            tasks.extend(page)
            if len(page) < page_size:
                break
            start += page_size
        return tasks

    def list_projects(self) -> list:
        projects = []
        page_size = 100
        start = 0
        while True:
            result = self._request(
                "GET",
                "/api/resource/Project",
                params={
                    "filters": json.dumps([
                        ["status", "not in", ["Completed", "Cancelled"]],
                    ]),
                    "fields": json.dumps(["name", "project_name"]),
                    "limit_page_length": page_size,
                    "limit_start": start,
                },
            )
            page = result.get("data", [])
            for p in page:
                label = (
                    f"{p['name']} — {p['project_name']}"
                    if p.get("project_name") and p["project_name"] != p["name"]
                    else p["name"]
                )
                projects.append({"id": p["name"], "label": label})
            if len(page) < page_size:
                break
            start += page_size
        return projects

    def extend_project(self, project: str, new_date: str) -> None:
        self._request(
            "PUT",
            f"/api/resource/Project/{project}",
            json={"expected_end_date": new_date},
        )

    def create_task(self, task_input: dict) -> tuple[str, list[str]]:
        notes = []
        is_group = task_input.get("is_group", False)
        doc = {
            "subject": task_input["subject"],
            "description": task_input["description"],
            "project": task_input["project"],
        }
        if task_input.get("parent_task"):
            doc["parent_task"] = task_input["parent_task"]
        if is_group:
            doc["is_group"] = 1
            doc["status"] = "Open"
        else:
            doc["expected_time"] = task_input["hours"]
            doc["exp_start_date"] = task_input["date"]
            doc["exp_end_date"] = task_input["date"]
            doc["custom_planned_completion_date"] = task_input["date"]
            doc["status"] = "Completed"
        try:
            result = self._request("POST", "/api/resource/Task", json=doc)
        except requests.HTTPError as e:
            if (e.response is not None
                    and e.response.status_code == 417
                    and e.response.json().get("exc_type") == "InvalidDates"):
                new_end = _next_month_end(date_type.today())
                self.extend_project(doc["project"], new_end)
                notes.append(f"Note: project end date extended to {new_end}")
                result = self._request("POST", "/api/resource/Task", json=doc)
            else:
                raise
        return result["data"]["name"], notes


def _build_tree(tasks: list[dict]) -> list[dict]:
    by_name = {t["name"]: dict(t, children=[]) for t in tasks}
    roots = []
    for node in by_name.values():
        parent = node.get("parent_task")
        if parent and parent in by_name:
            by_name[parent]["children"].append(node)
        else:
            roots.append(node)
    return roots


# ---------------------------------------------------------------------------
# Client cache — one login per MCP server session
# ---------------------------------------------------------------------------

_client: ERPNextClient | None = None
_client_url: str | None = None
_client_username: str | None = None

_AUTH_ERROR = {
    "error": "auth_failed",
    "message": "ERPNext authentication failed. Run `/plugin config erpnext-timesheet` to update your credentials, then re-invoke the skill.",
}


def _load_credentials() -> dict | None:
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT", "")
    if not plugin_root:
        return None
    root = Path(plugin_root)
    plugin_id = f"{root.parent.name}@{root.parent.parent.name}"

    claude_dir = Path.home() / ".claude"

    settings_path = claude_dir / "settings.json"
    if not settings_path.exists():
        return None
    try:
        settings = json.loads(settings_path.read_text())
        options = settings.get("pluginConfigs", {}).get(plugin_id, {}).get("options", {})
    except (json.JSONDecodeError, KeyError):
        return None

    creds_path = claude_dir / ".credentials.json"
    password = ""
    if creds_path.exists():
        try:
            creds_data = json.loads(creds_path.read_text())
            password = creds_data.get("pluginSecrets", {}).get(plugin_id, {}).get("password", "")
        except (json.JSONDecodeError, KeyError):
            pass

    url = options.get("url", "").rstrip("/")
    username = options.get("username", "")
    if not all([url, username, password]):
        return None
    return {"url": url, "username": username, "password": password}


def _get_client() -> ERPNextClient:
    global _client, _client_url, _client_username
    creds = _load_credentials()
    if creds is None:
        raise RuntimeError("ERPNext credentials not configured")
    url, username, password = creds["url"], creds["username"], creds["password"]
    if _client is None or _client_url != url or _client_username != username:
        if _client is not None:
            _client.logout()
        _client = ERPNextClient(url, username, password)
        _client_url = url
        _client_username = username
    return _client


def _clear_client():
    global _client, _client_url, _client_username
    if _client is not None:
        _client.logout()
    _client = None
    _client_url = None
    _client_username = None


atexit.register(_clear_client)
signal.signal(signal.SIGTERM, lambda *_: (_clear_client(), sys.exit(0)))


def _load_config() -> dict:
    return json.loads((Path.home() / ".claude" / "timesheet.json").read_text())


def _is_auth_error(e: requests.HTTPError) -> bool:
    return e.response is not None and e.response.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Timesheet document builder
# ---------------------------------------------------------------------------

def build_timesheet_doc(config: dict, entries: list, date_str: str = None) -> dict:
    base = datetime.strptime(date_str, "%Y-%m-%d") if date_str else datetime.today()
    today = base.strftime("%Y-%m-%d")
    h, m = map(int, config.get("start_time", "09:00").split(":"))
    current = base.replace(hour=h, minute=m, second=0, microsecond=0)

    time_logs = []
    for entry in entries:
        hours = float(entry["hours"])
        from_time = current.strftime("%Y-%m-%d %H:%M:%S")
        current += timedelta(hours=hours)
        log = {
            "activity_type": entry.get("activity_type", config["default_activity"]),
            "description": entry["description"],
            "hours": hours,
            "from_time": from_time,
            "to_time": current.strftime("%Y-%m-%d %H:%M:%S"),
            "project": entry.get("project", config["project"]),
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


def _next_month_end(today: date_type) -> str:
    if today.month == 12:
        next_year, next_month = today.year + 1, 1
    else:
        next_year, next_month = today.year, today.month + 1
    last_day = calendar.monthrange(next_year, next_month)[1]
    return date_type(next_year, next_month, last_day).isoformat()


# ---------------------------------------------------------------------------
# Log-parsing
# ---------------------------------------------------------------------------

def get_timezone(config: dict):
    tz_name = config.get("timezone")
    return ZoneInfo(tz_name) if tz_name else None


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


_NOISE_PREFIXES = (
    "<local-command-caveat>",
    "<command-name>",
    "<command-message>",
    "<local-command-stdout>",
    "Base directory for this skill:",
    "This session is being continued from",
    "[Request interrupted",
    "[Image",
)


def get_today_messages(tz=None, target_date=None) -> list:
    projects_dir = Path.home() / ".claude" / "projects"
    if not projects_dir.exists():
        return []

    if target_date is None:
        target_date = datetime.now(tz).date() if tz else date_type.today()

    messages = []
    for project_dir in projects_dir.iterdir():
        if not project_dir.is_dir():
            continue
        for jsonl_file in project_dir.glob("*.jsonl"):
            mtime = datetime.fromtimestamp(jsonl_file.stat().st_mtime, tz=tz).date() if tz \
                else datetime.fromtimestamp(jsonl_file.stat().st_mtime).date()
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

                    text = parse_content_blocks(entry.get("message", {}).get("content", ""))
                    if not text or len(text) <= 30:
                        continue

                    # Filter noise
                    if any(text.startswith(p) for p in _NOISE_PREFIXES):
                        continue

                    messages.append({
                        "role": entry["type"],
                        "text": text[:300],
                        "cwd": entry.get("cwd", ""),
                        "timestamp": ts_local.isoformat(),
                    })
            except Exception:
                continue

    return sorted(messages, key=lambda m: m["timestamp"])


# ---------------------------------------------------------------------------
# Setup / discover
# ---------------------------------------------------------------------------

def discover(url: str, username: str, password: str) -> dict:
    base = url.rstrip("/")
    session = requests.Session()

    resp = session.post(f"{base}/api/method/login", data={"usr": username, "pwd": password})
    resp.raise_for_status()

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
        raise ValueError(
            f"No employee record found for {username}. "
            "Ask your ERPNext admin to link your user to an Employee."
        )
    employee = employees[0]["name"]
    company = employees[0]["company"]

    resp = session.get(
        f"{base}/api/resource/Project",
        params={"fields": json.dumps(["name", "project_name"]), "limit": 50},
    )
    resp.raise_for_status()
    projects = [
        {
            "id": p["name"],
            "label": f"{p['name']} — {p['project_name']}"
            if p.get("project_name") and p["project_name"] != p["name"]
            else p["name"],
        }
        for p in resp.json().get("data", [])
    ]

    resp = session.get(
        f"{base}/api/resource/{quote('Activity Type')}",
        params={"fields": json.dumps(["name"]), "limit": 50},
    )
    resp.raise_for_status()
    activity_types = [a["name"] for a in resp.json().get("data", [])]

    try:
        resp = session.get(
            f"{base}/api/resource/User/{quote(username, safe='')}",
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
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(config, indent=2))


# ---------------------------------------------------------------------------
# MCP tools
# ---------------------------------------------------------------------------


@mcp.tool()
def checkConfig() -> dict:
    """Check plugin configuration. Runs ERPNext discovery on first call if timesheet.json is missing."""
    creds = _load_credentials()
    if creds is None:
        return {"configured": False, "reason": "credentials_missing"}

    config_path = Path.home() / ".claude" / "timesheet.json"
    if not config_path.exists():
        try:
            result = discover(creds["url"], creds["username"], creds["password"])
        except requests.HTTPError as e:
            if _is_auth_error(e):
                return {"configured": False, "reason": "auth_failed"}
            raise
        except (requests.ConnectionError, requests.Timeout):
            return {"configured": False, "reason": "connection_error"}

        config = {
            "username": creds["username"],
            "employee": result["employee"],
            "company": result["company"],
            "project": "",
            "default_activity": "",
            "work_hours": 8.0,
            "start_time": "09:00",
            "timezone": "",
            "_projects": result["projects"],
            "_activity_types": result["activity_types"],
        }
        write_config(config, str(config_path))
    else:
        config = json.loads(config_path.read_text())

    return {
        "configured": True,
        "username": config.get("username", creds["username"]),
        "url": creds["url"],
        "work_hours": config.get("work_hours", 8),
        "project": config.get("project", ""),
        "default_activity": config.get("default_activity", ""),
        "employee": config.get("employee", ""),
        "company": config.get("company", ""),
        "_projects": config.get("_projects", []),
        "_activity_types": config.get("_activity_types", []),
    }


@mcp.tool()
def readHistory(date: str) -> list:
    """Read Claude conversation messages for the given date (YYYY-MM-DD)."""
    config_path = Path.home() / ".claude" / "timesheet.json"
    tz = None
    if config_path.exists():
        tz = get_timezone(json.loads(config_path.read_text()))
    return get_today_messages(tz=tz, target_date=date_type.fromisoformat(date))


@mcp.tool()
def checkExisting(date: str) -> dict:
    """Check whether a timesheet already exists for the given date (YYYY-MM-DD)."""
    config = _load_config()
    try:
        client = _get_client()
        return {"exists": client.check_duplicate(config["employee"], date)}
    except requests.HTTPError as e:
        if _is_auth_error(e):
            _clear_client()
            return _AUTH_ERROR
        raise


@mcp.tool()
def submitTimesheet(date: str, entries: list) -> dict:
    """Build and submit a timesheet for the given date (YYYY-MM-DD) with the provided entries."""
    config = _load_config()
    try:
        client = _get_client()
        doc = build_timesheet_doc(config, entries, date_str=date)
        name = client.create_timesheet(doc)
        client.submit_timesheet(name)
        _clear_client()
        return {"success": True, "name": name}
    except requests.HTTPError as e:
        if _is_auth_error(e):
            _clear_client()
            return _AUTH_ERROR
        raise


@mcp.tool()
def listTasks(project: str) -> list:
    """Return active tasks for the given project as a nested tree (groups contain children)."""
    try:
        flat = _get_client().list_tasks(project)
        return _build_tree(flat)
    except requests.HTTPError as e:
        if _is_auth_error(e):
            _clear_client()
            return [_AUTH_ERROR]
        raise


@mcp.tool()
def listProjects() -> list:
    """Return all non-Completed/non-Cancelled projects as [{id, label}]."""
    try:
        return _get_client().list_projects()
    except requests.HTTPError as e:
        if _is_auth_error(e):
            _clear_client()
            return [_AUTH_ERROR]
        raise


@mcp.tool()
def createTask(subject: str, description: str, project: str, hours: float, date: str,
               parent_task: str = None, is_group: bool = False) -> dict:
    """Create a task in ERPNext. Auto-extends project end date on InvalidDates errors."""
    try:
        name, notes = _get_client().create_task({
            "subject": subject,
            "description": description,
            "project": project,
            "hours": hours,
            "date": date,
            "parent_task": parent_task,
            "is_group": is_group,
        })
        return {"name": name, "notes": notes}
    except requests.HTTPError as e:
        if _is_auth_error(e):
            _clear_client()
            return _AUTH_ERROR
        raise


@mcp.tool()
def updateSettings(project: str = None, activity_type: str = None,
                   work_hours: float = None, start_time: str = None,
                   timezone: str = None) -> dict:
    """Update one or more config settings. Clears temporary _projects/_activity_types lists."""
    config_path = Path.home() / ".claude" / "timesheet.json"
    if not config_path.exists():
        return {"configured": False, "reason": "not_configured"}
    config = json.loads(config_path.read_text())
    creds = _load_credentials()

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

    config.pop("_projects", None)
    config.pop("_activity_types", None)

    config_path.write_text(json.dumps(config, indent=2))
    return {
        "configured": True,
        "username": config.get("username", creds["username"] if creds else ""),
        "url": creds["url"] if creds else "",
        "work_hours": config.get("work_hours", 8),
        "project": config.get("project"),
        "default_activity": config.get("default_activity"),
    }


if __name__ == "__main__":
    mcp.run()
