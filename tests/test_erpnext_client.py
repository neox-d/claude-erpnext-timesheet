import json
import re
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
import requests

from scripts.erpnext_client import ERPNextClient, build_timesheet_doc


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
