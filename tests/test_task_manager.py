import json
import sys
from unittest.mock import MagicMock, patch, call

import pytest
import requests

from scripts.task_manager import get_tasks, create_task, extend_project_end_date


def mock_response(status_code=200, json_data=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.ok = status_code < 400
    resp.json.return_value = json_data or {}
    if status_code >= 400:
        resp.raise_for_status.side_effect = requests.HTTPError(response=resp)
    else:
        resp.raise_for_status.return_value = None
    return resp


BASE_CONFIG = {
    "url": "https://erp.example.com",
    "username": "user@example.com",
    "password": "pass",
    "project": "PROJ-001",
}


# --- get_tasks ---

def test_get_tasks_returns_list():
    """get_tasks() returns a list of task dicts."""
    task_data = [
        {"name": "TASK-001", "subject": "Fix login", "status": "Open"},
        {"name": "TASK-002", "subject": "Add tests", "status": "Overdue"},
    ]
    with patch("scripts.task_manager.requests.Session") as mock_cls:
        session = MagicMock()
        mock_cls.return_value = session
        session.post.return_value = mock_response(200)
        session.get.return_value = mock_response(200, {"data": task_data})

        result = get_tasks(BASE_CONFIG, "PROJ-001")

    assert result == task_data


def test_get_tasks_returns_empty_list():
    """get_tasks() returns [] when no tasks found."""
    with patch("scripts.task_manager.requests.Session") as mock_cls:
        session = MagicMock()
        mock_cls.return_value = session
        session.post.return_value = mock_response(200)
        session.get.return_value = mock_response(200, {"data": []})

        result = get_tasks(BASE_CONFIG, "PROJ-001")

    assert result == []


def test_get_tasks_raises_on_http_error():
    """get_tasks() raises HTTPError on failed request."""
    with patch("scripts.task_manager.requests.Session") as mock_cls:
        session = MagicMock()
        mock_cls.return_value = session
        session.post.return_value = mock_response(200)
        session.get.return_value = mock_response(403)

        with pytest.raises(requests.HTTPError):
            get_tasks(BASE_CONFIG, "PROJ-001")


# --- create_task ---

def test_create_task_success():
    """create_task() returns task name on success."""
    task_input = {
        "subject": "Build feature",
        "description": "Details here",
        "project": "PROJ-001",
        "hours": 4.0,
        "date": "2026-03-24",
    }
    with patch("scripts.task_manager.requests.Session") as mock_cls:
        session = MagicMock()
        mock_cls.return_value = session
        session.post.return_value = mock_response(200)
        session.request.return_value = mock_response(200, {"data": {"name": "TASK-999"}})

        name, notes = create_task(BASE_CONFIG, task_input)

    assert name == "TASK-999"
    assert notes == []


def test_create_task_auto_extends_on_invalid_dates(capsys):
    """create_task() extends project end date when ERPNext returns InvalidDates, then retries."""
    task_input = {
        "subject": "Build feature",
        "description": "Details",
        "project": "PROJ-001",
        "hours": 4.0,
        "date": "2026-03-24",
    }
    invalid_dates_resp = MagicMock()
    invalid_dates_resp.status_code = 417
    invalid_dates_resp.ok = False
    invalid_dates_resp.json.return_value = {"exc_type": "InvalidDates"}
    invalid_dates_resp.raise_for_status.side_effect = requests.HTTPError(response=invalid_dates_resp)

    success_resp = mock_response(200, {"data": {"name": "TASK-999"}})
    extend_resp = mock_response(200, {"data": {}})

    with patch("scripts.task_manager.requests.Session") as mock_cls:
        session = MagicMock()
        mock_cls.return_value = session
        session.post.return_value = mock_response(200)
        session.request.side_effect = [
            invalid_dates_resp,  # first create attempt
            extend_resp,          # extend project
            success_resp,         # retry create
        ]

        name, notes = create_task(BASE_CONFIG, task_input)

    assert name == "TASK-999"
    assert any("extended" in n for n in notes)


def test_create_task_exits_nonzero_on_unrecoverable_error():
    """create_task() raises SystemExit when retry also fails."""
    task_input = {
        "subject": "Build feature",
        "description": "Details",
        "project": "PROJ-001",
        "hours": 4.0,
        "date": "2026-03-24",
    }
    invalid_dates_resp = MagicMock()
    invalid_dates_resp.status_code = 417
    invalid_dates_resp.ok = False
    invalid_dates_resp.json.return_value = {"exc_type": "InvalidDates"}
    invalid_dates_resp.raise_for_status.side_effect = requests.HTTPError(response=invalid_dates_resp)

    extend_resp = mock_response(200, {"data": {}})

    with patch("scripts.task_manager.requests.Session") as mock_cls:
        session = MagicMock()
        mock_cls.return_value = session
        session.post.return_value = mock_response(200)
        # Both create attempts fail with InvalidDates; extend succeeds
        session.request.side_effect = [
            invalid_dates_resp,
            extend_resp,
            invalid_dates_resp,
        ]

        with pytest.raises(SystemExit) as exc_info:
            create_task(BASE_CONFIG, task_input)

    assert exc_info.value.code != 0


# --- extend_project_end_date ---

def test_extend_project_end_date_success():
    """extend_project_end_date() returns success dict."""
    with patch("scripts.task_manager.requests.Session") as mock_cls:
        session = MagicMock()
        mock_cls.return_value = session
        session.post.return_value = mock_response(200)
        session.request.return_value = mock_response(200, {"data": {}})

        result = extend_project_end_date(BASE_CONFIG, "PROJ-001", "2026-04-30")

    assert result == {"success": True}


def test_extend_project_end_date_raises_on_failure():
    """extend_project_end_date() raises HTTPError on failure."""
    with patch("scripts.task_manager.requests.Session") as mock_cls:
        session = MagicMock()
        mock_cls.return_value = session
        session.post.return_value = mock_response(200)
        session.request.return_value = mock_response(500)

        with pytest.raises(requests.HTTPError):
            extend_project_end_date(BASE_CONFIG, "PROJ-001", "2026-04-30")
