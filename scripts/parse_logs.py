#!/usr/bin/env python3
"""
Parse today's Claude Code conversation logs.
Outputs a JSON array of {role, text, cwd, timestamp}.
"""
import argparse
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo  # type: ignore


def load_config(config_path: str) -> dict:
    path = Path(config_path)
    if not path.exists():
        print(f"ERROR: Config file not found: {config_path}", file=sys.stderr)
        sys.exit(1)
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON in config: {e}", file=sys.stderr)
        sys.exit(1)


def validate_config(config: dict) -> list:
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


def get_today_messages(tz=None) -> list:
    projects_dir = Path.home() / ".claude" / "projects"
    if not projects_dir.exists():
        return []

    if tz is not None:
        today = datetime.now(tz).date()
    else:
        today = date.today()
    messages = []

    for project_dir in projects_dir.iterdir():
        if not project_dir.is_dir():
            continue
        for jsonl_file in project_dir.glob("*.jsonl"):
            # mtime pre-filter: skip files not modified today
            if tz is not None:
                mtime = datetime.fromtimestamp(jsonl_file.stat().st_mtime, tz=tz).date()
            else:
                mtime = datetime.fromtimestamp(jsonl_file.stat().st_mtime).date()
            if mtime < today:
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

                    if ts_local.date() != today:
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


def main():
    parser = argparse.ArgumentParser(description="Parse Claude conversation logs")
    parser.add_argument("--config", required=True, help="Path to timesheet.json")
    parser.add_argument("--validate-only", action="store_true",
                        help="Validate config and exit")
    args = parser.parse_args()

    config = load_config(args.config)
    errors = validate_config(config)
    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    if args.validate_only:
        print("OK")
        return

    tz = get_timezone(config)
    messages = get_today_messages(tz)
    print(json.dumps(messages, indent=2))


if __name__ == "__main__":
    main()
