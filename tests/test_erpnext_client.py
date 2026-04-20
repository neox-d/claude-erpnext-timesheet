import json
import re
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
import requests

from mcp_server import ERPNextClient, build_timesheet_doc, _build_tree


def make_client():
    return ERPNextClient("https://erp.example.com", "user@example.com", "pass")


def mock_response(status_code=200, json_data=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    if status_code >= 400:
        resp.raise_for_status.side_effect = requests.HTTPError(response=resp)
    else:
        resp.raise_for_status.return_value = None
    return resp


# --- login ---

def test_login_sets_authenticated():
    client = make_client()
    with patch.object(client.session, "post", return_value=mock_response(200)):
        client.login()
    assert client._authenticated is True


def test_login_called_with_correct_payload():
    client = make_client()
    with patch.object(client.session, "post", return_value=mock_response(200)) as mock_post:
        client.login()
    mock_post.assert_called_once_with(
        "https://erp.example.com/api/method/login",
        data={"usr": "user@example.com", "pwd": "pass"},
    )


def test_login_raises_on_failure():
    client = make_client()
    with patch.object(client.session, "post", return_value=mock_response(401)):
        with pytest.raises(requests.HTTPError):
            client.login()


# --- check_duplicate ---

def test_check_duplicate_true():
    client = make_client()
    client._authenticated = True
    with patch.object(client.session, "request",
                      return_value=mock_response(200, {"data": [{"name": "TS-0001"}]})):
        assert client.check_duplicate("EMP-001", "2026-03-23") is True


def test_check_duplicate_false():
    client = make_client()
    client._authenticated = True
    with patch.object(client.session, "request",
                      return_value=mock_response(200, {"data": []})):
        assert client.check_duplicate("EMP-001", "2026-03-23") is False


def test_check_duplicate_reauths_on_401():
    """On 401, re-auths once and retries."""
    client = make_client()
    client._authenticated = True

    responses = [
        mock_response(401),               # first request: 401
        mock_response(200),               # re-auth login
        mock_response(200, {"data": []}), # retry request
    ]

    with patch.object(client.session, "request", side_effect=[responses[0], responses[2]]) as mock_req, \
         patch.object(client.session, "post", return_value=responses[1]):
        result = client.check_duplicate("EMP-001", "2026-03-23")

    assert result is False


# --- create_timesheet ---

def test_create_timesheet_returns_name():
    client = make_client()
    client._authenticated = True
    with patch.object(client.session, "request",
                      return_value=mock_response(200, {"data": {"name": "TS-0042"}})):
        name = client.create_timesheet({"employee": "EMP-001"})
    assert name == "TS-0042"


# --- submit_timesheet ---

def test_submit_timesheet_calls_put():
    client = make_client()
    client._authenticated = True
    with patch.object(client.session, "request",
                      return_value=mock_response(200, {"data": {}})) as mock_req:
        client.submit_timesheet("TS-0042")
    mock_req.assert_called_once_with(
        "PUT",
        "https://erp.example.com/api/resource/Timesheet/TS-0042",
        json={"docstatus": 1},
    )


# --- build_timesheet_doc ---

BASE_CONFIG = {
    "employee": "EMP-001",
    "company": "ACME Corp",
    "username": "user@example.com",
    "project": "PROJ-001",
    "default_activity": "Development",
    "work_hours": 4,
    "start_time": "09:00",
}


def test_build_timesheet_doc_sequential_no_overlap():
    entries = [
        {"description": "Task A", "hours": 2.0},
        {"description": "Task B", "hours": 2.0},
    ]
    doc = build_timesheet_doc(BASE_CONFIG, entries)
    logs = doc["time_logs"]
    assert len(logs) == 2
    assert logs[0]["to_time"] == logs[1]["from_time"]


def test_build_timesheet_doc_fields():
    entries = [{"description": "Did stuff", "hours": 4.0}]
    doc = build_timesheet_doc(BASE_CONFIG, entries)
    assert doc["employee"] == "EMP-001"
    assert doc["company"] == "ACME Corp"
    assert doc["time_logs"][0]["project"] == "PROJ-001"
    assert doc["time_logs"][0]["activity_type"] == "Development"
    assert doc["time_logs"][0]["description"] == "Did stuff"
    assert doc["time_logs"][0]["hours"] == 4.0


def test_build_timesheet_doc_activity_override():
    entries = [{"description": "Design session", "hours": 4.0, "activity_type": "Design"}]
    doc = build_timesheet_doc(BASE_CONFIG, entries)
    assert doc["time_logs"][0]["activity_type"] == "Design"


def test_build_timesheet_doc_time_format():
    entries = [{"description": "Task", "hours": 1.0}]
    doc = build_timesheet_doc(BASE_CONFIG, entries)
    log = doc["time_logs"][0]
    pattern = r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}"
    assert re.match(pattern, log["from_time"])
    assert re.match(pattern, log["to_time"])


def test_build_timesheet_doc_includes_task_when_present():
    """task field is included in time log row when entry has a non-empty task key."""
    entries = [{"description": "Task A", "hours": 4.0, "task": "TASK-2026-01052"}]
    doc = build_timesheet_doc(BASE_CONFIG, entries)
    assert doc["time_logs"][0]["task"] == "TASK-2026-01052"


def test_build_timesheet_doc_omits_task_when_absent():
    """task field is absent in time log row when entry has no task key."""
    entries = [{"description": "Task A", "hours": 4.0}]
    doc = build_timesheet_doc(BASE_CONFIG, entries)
    assert "task" not in doc["time_logs"][0]


def test_build_timesheet_doc_omits_task_when_empty_string():
    """task field is omitted when entry has task key set to empty string."""
    entries = [{"description": "Task A", "hours": 4.0, "task": ""}]
    doc = build_timesheet_doc(BASE_CONFIG, entries)
    assert "task" not in doc["time_logs"][0]


def test_build_timesheet_doc_with_date_str_uses_that_date():
    """date_str overrides today for start_date, end_date, and time log timestamps."""
    entries = [{"description": "Task A", "hours": 2.0}]
    doc = build_timesheet_doc(BASE_CONFIG, entries, date_str="2026-03-24")
    assert doc["start_date"] == "2026-03-24"
    assert doc["end_date"] == "2026-03-24"
    assert doc["time_logs"][0]["from_time"].startswith("2026-03-24")
    assert doc["time_logs"][0]["to_time"].startswith("2026-03-24")


def test_build_timesheet_doc_without_date_str_uses_today():
    """No date_str → dates use today (backward compat)."""
    from datetime import date as date_cls
    entries = [{"description": "Task A", "hours": 2.0}]
    doc = build_timesheet_doc(BASE_CONFIG, entries)
    today_str = date_cls.today().strftime("%Y-%m-%d")
    assert doc["start_date"] == today_str
    assert doc["end_date"] == today_str


# --- _build_tree ---

def test_build_tree_empty():
    assert _build_tree([]) == []


def test_build_tree_flat_list_no_parents():
    tasks = [
        {"name": "T-1", "subject": "Alpha", "is_group": 0, "status": "Open",
         "exp_end_date": "", "parent_task": None},
        {"name": "T-2", "subject": "Beta", "is_group": 0, "status": "Open",
         "exp_end_date": "", "parent_task": None},
    ]
    result = _build_tree(tasks)
    assert len(result) == 2
    assert result[0]["children"] == []
    assert result[1]["children"] == []


def test_build_tree_one_level_nesting():
    tasks = [
        {"name": "T-1", "subject": "Group", "is_group": 1, "status": "Open",
         "exp_end_date": "", "parent_task": None},
        {"name": "T-2", "subject": "Child", "is_group": 0, "status": "Open",
         "exp_end_date": "", "parent_task": "T-1"},
    ]
    result = _build_tree(tasks)
    assert len(result) == 1
    assert result[0]["name"] == "T-1"
    assert len(result[0]["children"]) == 1
    assert result[0]["children"][0]["name"] == "T-2"


def test_build_tree_two_level_nesting():
    tasks = [
        {"name": "T-1", "subject": "Top Group", "is_group": 1, "status": "Open",
         "exp_end_date": "", "parent_task": None},
        {"name": "T-2", "subject": "Sub Group", "is_group": 1, "status": "Open",
         "exp_end_date": "", "parent_task": "T-1"},
        {"name": "T-3", "subject": "Leaf", "is_group": 0, "status": "Open",
         "exp_end_date": "", "parent_task": "T-2"},
    ]
    result = _build_tree(tasks)
    assert len(result) == 1
    assert result[0]["children"][0]["name"] == "T-2"
    assert result[0]["children"][0]["children"][0]["name"] == "T-3"


def test_build_tree_orphan_parent_treated_as_root():
    """Task whose parent_task is not in the fetched set (e.g. Completed) → root."""
    tasks = [
        {"name": "T-2", "subject": "Orphan", "is_group": 0, "status": "Open",
         "exp_end_date": "", "parent_task": "T-MISSING"},
    ]
    result = _build_tree(tasks)
    assert len(result) == 1
    assert result[0]["name"] == "T-2"


# --- list_tasks (updated) ---

def test_list_tasks_filter_excludes_completed_and_cancelled():
    client = make_client()
    client._authenticated = True
    with patch.object(client, "_request", return_value={"data": []}) as mock_req:
        client.list_tasks("PROJ-001")
    params = mock_req.call_args[1]["params"]
    filters = json.loads(params["filters"])
    assert ["status", "not in", ["Completed", "Cancelled"]] in filters


def test_list_tasks_fetches_is_group_and_parent_task_fields():
    client = make_client()
    client._authenticated = True
    with patch.object(client, "_request", return_value={"data": []}) as mock_req:
        client.list_tasks("PROJ-001")
    params = mock_req.call_args[1]["params"]
    fields = json.loads(params["fields"])
    assert "is_group" in fields
    assert "parent_task" in fields


def test_list_tasks_paginates_until_short_page():
    client = make_client()
    client._authenticated = True
    page1 = {"data": [{"name": f"T-{i}"} for i in range(100)]}
    page2 = {"data": [{"name": "T-100"}, {"name": "T-101"}]}
    with patch.object(client, "_request", side_effect=[page1, page2]) as mock_req:
        result = client.list_tasks("PROJ-001")
    assert len(result) == 102
    assert mock_req.call_count == 2


def test_list_tasks_stops_after_single_short_page():
    client = make_client()
    client._authenticated = True
    page = {"data": [{"name": "T-001"}]}
    with patch.object(client, "_request", side_effect=[page]) as mock_req:
        result = client.list_tasks("PROJ-001")
    assert len(result) == 1
    assert mock_req.call_count == 1


def test_list_tasks_stops_on_empty_page():
    """Exact multiple of page_size: full page + empty page → loop terminates cleanly."""
    client = make_client()
    client._authenticated = True
    page1 = {"data": [{"name": f"T-{i}"} for i in range(100)]}
    page2 = {"data": []}
    with patch.object(client, "_request", side_effect=[page1, page2]) as mock_req:
        result = client.list_tasks("PROJ-001")
    assert len(result) == 100
    assert mock_req.call_count == 2


# --- create_task (parent_task / is_group) ---

def test_create_task_with_parent_task():
    client = make_client()
    client._authenticated = True
    with patch.object(client, "_request",
                      return_value={"data": {"name": "TASK-0001"}}) as mock_req:
        name, notes = client.create_task({
            "subject": "Child task",
            "description": "desc",
            "project": "PROJ-001",
            "hours": 2.0,
            "date": "2026-04-20",
            "parent_task": "TASK-GROUP-001",
        })
    doc = mock_req.call_args[1]["json"]
    assert doc["parent_task"] == "TASK-GROUP-001"
    assert doc["status"] == "Completed"
    assert doc["expected_time"] == 2.0
    assert "exp_start_date" in doc
    assert "exp_end_date" in doc
    assert "custom_planned_completion_date" in doc
    assert "is_group" not in doc
    assert name == "TASK-0001"
    assert notes == []


def test_create_task_is_group_true():
    client = make_client()
    client._authenticated = True
    with patch.object(client, "_request",
                      return_value={"data": {"name": "TASK-GRP-001"}}) as mock_req:
        name, notes = client.create_task({
            "subject": "My Group",
            "description": "group desc",
            "project": "PROJ-001",
            "hours": 0,
            "date": "2026-04-20",
            "is_group": True,
        })
    doc = mock_req.call_args[1]["json"]
    assert doc["is_group"] == 1
    assert "status" not in doc
    assert "expected_time" not in doc
    assert "exp_start_date" not in doc
    assert "exp_end_date" not in doc
    assert "custom_planned_completion_date" not in doc
    assert name == "TASK-GRP-001"
    assert notes == []


def test_create_task_leaf_omits_is_group_field():
    client = make_client()
    client._authenticated = True
    with patch.object(client, "_request",
                      return_value={"data": {"name": "TASK-0002"}}) as mock_req:
        client.create_task({
            "subject": "Leaf task",
            "description": "desc",
            "project": "PROJ-001",
            "hours": 2.0,
            "date": "2026-04-20",
        })
    doc = mock_req.call_args[1]["json"]
    assert "is_group" not in doc
    assert doc["status"] == "Completed"
    assert doc["expected_time"] == 2.0


# --- list_projects ---

def test_list_projects_returns_label():
    client = make_client()
    client._authenticated = True
    page = {"data": [
        {"name": "PROJ-0001", "project_name": "My Project"},
        {"name": "PROJ-0050", "project_name": "PROJ-0050"},
    ]}
    with patch.object(client, "_request", side_effect=[page]) as mock_req:
        result = client.list_projects()
    assert result == [
        {"id": "PROJ-0001", "label": "PROJ-0001 — My Project"},
        {"id": "PROJ-0050", "label": "PROJ-0050"},
    ]


def test_list_projects_filter_excludes_completed_cancelled():
    client = make_client()
    client._authenticated = True
    with patch.object(client, "_request", return_value={"data": []}) as mock_req:
        client.list_projects()
    params = mock_req.call_args[1]["params"]
    filters = json.loads(params["filters"])
    assert ["status", "not in", ["Completed", "Cancelled"]] in filters


def test_list_projects_paginates():
    client = make_client()
    client._authenticated = True
    page1 = {"data": [{"name": f"PROJ-{i:04d}", "project_name": f"Project {i}"}
                       for i in range(100)]}
    page2 = {"data": [{"name": "PROJ-0100", "project_name": "Last"}]}
    with patch.object(client, "_request", side_effect=[page1, page2]):
        result = client.list_projects()
    assert len(result) == 101


# --- build_timesheet_doc (per-entry project) ---

def test_build_timesheet_doc_per_entry_project_override():
    """Entry-level project overrides config project in the time log."""
    entries = [
        {"description": "Task A", "hours": 2.0, "project": "PROJ-0050"},
        {"description": "Task B", "hours": 2.0},
    ]
    doc = build_timesheet_doc(BASE_CONFIG, entries)
    assert doc["time_logs"][0]["project"] == "PROJ-0050"
    assert doc["time_logs"][1]["project"] == "PROJ-001"   # falls back to config
