#!/usr/bin/env python
"""Local SQLite-backed assistant CLI.

Codex parses natural language into the JSON contract documented in AGENTS.md;
this CLI validates, writes, and reads back the committed rows.
"""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from stat import S_IWRITE
from typing import Any
from uuid import uuid4


APP_DIR = Path(__file__).resolve().parent
DEFAULT_DB = APP_DIR / "data" / "assistant.sqlite"
SCHEMA_PATH = APP_DIR / "schema.sql"
LOCAL_TZ = timezone(timedelta(hours=8))
APP_VERSION = "3.0.0"

VALID_ITEM_TYPES = {"task", "event"}
VALID_ITEM_STATUS = {"active", "completed", "cancelled", "needs_review"}
QUERY_ITEM_STATUS = {"active", "completed", "cancelled", "all"}
VALID_RECURRENCE_FREQUENCIES = {"daily", "weekly", "monthly"}
VALID_RECURRENCE_STATUS = {"completed", "cancelled"}
VALID_PARSE_STATUS = {"parsed", "needs_review", "ignored", "failed"}
VALID_RELATIONS = {"prepares_for", "related_to", "duplicate_of"}
VALID_REVIEW_STATUS = {"open", "resolved", "dismissed"}
QUERY_REVIEW_STATUS = {"active": "open", "completed": "resolved", "cancelled": "dismissed"}
ITEMS_BACKUP_FORMAT = "dailyassistant-items-backup"
ITEMS_BACKUP_VERSION = 1
ITEMS_BACKUP_BEGIN = "BEGIN_DAILY_ASSISTANT_ITEMS_BACKUP_JSON"
ITEMS_BACKUP_END = "END_DAILY_ASSISTANT_ITEMS_BACKUP_JSON"
ITEMS_BACKUP_TABLE_COLUMNS = {
    "records": (
        "id",
        "source",
        "input_type",
        "canonical_text",
        "raw_text",
        "extraction_method",
        "extraction_confidence",
        "original_retained",
        "language",
        "timezone",
        "parse_status",
        "parse_confidence",
        "created_at",
        "updated_at",
    ),
    "items": (
        "id",
        "type",
        "title",
        "content",
        "status",
        "confidence",
        "due_at",
        "start_at",
        "end_at",
        "all_day",
        "project",
        "people",
        "location",
        "created_from_record_id",
        "created_at",
        "updated_at",
        "completed_at",
    ),
    "item_relations": (
        "id",
        "from_item_id",
        "to_item_id",
        "relation_type",
        "source_record_id",
        "created_at",
    ),
    "recurrence_rules": (
        "id",
        "item_id",
        "frequency",
        "interval",
        "by_weekday",
        "by_month_day",
        "start_date",
        "active_until",
        "timezone",
        "created_at",
        "updated_at",
    ),
    "recurrence_status": (
        "id",
        "rule_id",
        "item_id",
        "occurrence_date",
        "status",
        "override_json",
        "completed_at",
        "cancelled_at",
        "created_at",
        "updated_at",
    ),
    "item_events": (
        "id",
        "item_id",
        "record_id",
        "action",
        "before_json",
        "after_json",
        "confidence",
        "note",
        "created_at",
    ),
    "review_queue": (
        "id",
        "record_id",
        "item_id",
        "reason",
        "question",
        "status",
        "created_at",
        "resolved_at",
    ),
}
ITEMS_BACKUP_TABLE_ORDER = {
    "records": "created_at, id",
    "items": "created_at, id",
    "item_relations": "created_at, id",
    "recurrence_rules": "created_at, id",
    "recurrence_status": "created_at, id",
    "item_events": "created_at, id",
    "review_queue": "created_at, id",
}
ITEMS_BACKUP_IMPORT_ORDER = (
    "records",
    "items",
    "item_relations",
    "recurrence_rules",
    "recurrence_status",
    "item_events",
    "review_queue",
)
ITEMS_BACKUP_DELETE_ORDER = tuple(reversed(ITEMS_BACKUP_IMPORT_ORDER))


class AppError(Exception):
    """User-facing CLI error."""


class NeedsInitError(AppError):
    """Raised when a command requires the local database before it exists."""


@dataclass(frozen=True)
class AppConfig:
    db_path: Path


def configure_text_io() -> None:
    """Use UTF-8 for JSON stdin/stdout on Windows and other local shells."""
    for stream_name in ("stdin", "stdout", "stderr"):
        stream = getattr(sys, stream_name)
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass


def now_iso() -> str:
    return datetime.now(LOCAL_TZ).replace(microsecond=0).isoformat()


def make_id(prefix: str) -> str:
    return f"{prefix}-{datetime.now(LOCAL_TZ):%Y%m%d}-{uuid4().hex[:8]}"


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def print_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def path_is_under_app(path: Path) -> bool:
    try:
        path.resolve().relative_to(APP_DIR)
    except ValueError:
        return False
    return True


def get_current_windows_sid() -> str | None:
    if os.name != "nt":
        return None
    try:
        result = subprocess.run(
            ["whoami", "/user", "/fo", "csv", "/nh"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None

    for row in csv.reader(result.stdout.splitlines()):
        if len(row) >= 2 and row[1].startswith("S-"):
            return row[1]
    for token in result.stdout.replace('"', "").split():
        if token.startswith("S-"):
            return token
    return None


def grant_windows_modify(path: Path, *, container: bool) -> bool:
    sid = get_current_windows_sid()
    if sid is None or not path.exists():
        return False

    permission = f"*{sid}:(OI)(CI)M" if container else f"*{sid}:M"
    try:
        result = subprocess.run(
            ["icacls", str(path), "/grant", permission],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError:
        return False
    return result.returncode == 0


def repair_workspace_database_permissions(db_path: Path) -> bool:
    """Best-effort Windows ACL repair for the project-local database path."""
    if os.name != "nt" or not path_is_under_app(db_path):
        return False

    repaired = False
    data_dir = db_path.parent
    if data_dir.exists():
        repaired = grant_windows_modify(data_dir, container=True) or repaired
    if db_path.exists():
        repaired = grant_windows_modify(db_path, container=False) or repaired
    return repaired


def probe_database_writable(db_path: Path) -> bool:
    probe_path = db_path.parent / f".write-probe-{uuid4().hex}.tmp"
    try:
        probe_path.write_text("ok", encoding="utf-8")
        probe_path.unlink()
        if db_path.exists():
            with db_path.open("r+b"):
                pass
    except OSError:
        try:
            if probe_path.exists():
                probe_path.unlink()
        except OSError:
            pass
        return False
    return True


def ensure_database_writable(db_path: Path) -> None:
    try:
        db_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        repair_workspace_database_permissions(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)

    if db_path.exists():
        try:
            os.chmod(db_path, db_path.stat().st_mode | S_IWRITE)
        except OSError:
            pass

    if not probe_database_writable(db_path):
        repair_workspace_database_permissions(db_path)
        if db_path.exists():
            try:
                os.chmod(db_path, db_path.stat().st_mode | S_IWRITE)
            except OSError:
                pass
    if not probe_database_writable(db_path):
        raise AppError(
            "Database directory is not writable inside the workspace. "
            f"Path: {db_path.parent}. Fix the local file permissions or move the database under this project."
        )


def connect(db_path: Path, *, writable: bool = False) -> sqlite3.Connection:
    if writable:
        ensure_database_writable(db_path)
    else:
        db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    if writable:
        conn.execute("PRAGMA query_only = OFF")
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection):
    try:
        conn.execute("BEGIN")
        yield
    except Exception:
        conn.rollback()
        raise
    else:
        conn.commit()


def ensure_initialized(db_path: Path) -> None:
    if not db_path.exists():
        raise NeedsInitError(f"Database not found: {db_path}.")


def needs_init_payload(db_path: Path) -> dict[str, Any]:
    return {
        "status": "needs_init",
        "message": "Local database is not initialized.",
        "db": str(db_path),
        "next_extension": "extensions/install.md",
        "next_action": "Read extensions/install.md and ask the user whether to start using this project.",
    }


def initialize_database(db_path: Path) -> bool:
    if not SCHEMA_PATH.exists():
        raise AppError(f"Schema not found: {SCHEMA_PATH}")
    repair_workspace_database_permissions(db_path)
    with connect(db_path, writable=True) as conn:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    return repair_workspace_database_permissions(db_path)


def init_db(config: AppConfig) -> None:
    permissions_repaired = initialize_database(config.db_path)
    print_json({"status": "ok", "db": str(config.db_path), "permissions_repaired": permissions_repaired})


def command_available(command: list[str]) -> dict[str, Any]:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError as exc:
        return {"ok": False, "message": str(exc)}
    output = (result.stdout or result.stderr).strip()
    return {"ok": result.returncode == 0, "returncode": result.returncode, "output": output}


def write_probe(dir_path: Path) -> dict[str, Any]:
    try:
        dir_path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return {"ok": False, "path": str(dir_path), "message": str(exc)}
    probe_path = dir_path / f".doctor-write-probe-{uuid4().hex}.tmp"
    try:
        probe_path.write_text("ok", encoding="utf-8")
        probe_path.unlink()
    except OSError as exc:
        try:
            if probe_path.exists():
                probe_path.unlink()
        except OSError:
            pass
        return {"ok": False, "path": str(dir_path), "message": str(exc)}
    return {"ok": True, "path": str(dir_path)}


def doctor(config: AppConfig) -> None:
    pip_check = command_available([sys.executable, "-m", "pip", "--version"])
    checks = {
        "python": {
            "ok": sys.version_info >= (3, 10),
            "version": sys.version.split()[0],
            "executable": sys.executable,
            "required": ">=3.10",
        },
        "pip": pip_check,
        "sqlite3": {"ok": True, "version": sqlite3.sqlite_version},
        "schema": {"ok": SCHEMA_PATH.exists(), "path": str(SCHEMA_PATH)},
        "data_dir_writable": write_probe(config.db_path.parent),
        "database": {"exists": config.db_path.exists(), "path": str(config.db_path)},
    }
    required_ok = all(
        [
            checks["python"]["ok"],
            checks["pip"]["ok"],
            checks["sqlite3"]["ok"],
            checks["schema"]["ok"],
            checks["data_dir_writable"]["ok"],
        ]
    )
    status = "ok" if required_ok else "environment_error"
    next_extension = "extensions/install.md" if not required_ok else None
    print_json({"status": status, "checks": checks, "next_extension": next_extension})


def load_json_arg(json_text: str | None, json_file: str | None, json_base64: str | None) -> dict[str, Any]:
    provided = [value is not None for value in (json_text, json_file, json_base64)].count(True)
    if provided > 1:
        raise AppError("Use only one of --json, --file, or --base64.")
    if json_base64:
        try:
            text = base64.b64decode(json_base64, validate=True).decode("utf-8")
        except (ValueError, UnicodeDecodeError) as exc:
            raise AppError(f"Invalid UTF-8 base64 JSON: {exc}") from exc
    elif json_file:
        text = Path(json_file).read_text(encoding="utf-8")
    elif json_text:
        text = json_text
    else:
        text = sys.stdin.read()
    if not text.strip():
        raise AppError("No JSON input provided.")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AppError(f"Invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise AppError("Top-level JSON must be an object.")
    return data


def require_object(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key)
    if not isinstance(value, dict):
        raise AppError(f"`{key}` must be an object.")
    return value


def optional_list(data: dict[str, Any], key: str) -> list[Any]:
    value = data.get(key, [])
    if value is None:
        return []
    if not isinstance(value, list):
        raise AppError(f"`{key}` must be a list.")
    return value


def validate_confidence(value: Any, path: str) -> float | None:
    if value is None:
        return None
    if not isinstance(value, (int, float)):
        raise AppError(f"`{path}` must be a number between 0 and 1.")
    score = float(value)
    if score < 0 or score > 1:
        raise AppError(f"`{path}` must be between 0 and 1.")
    return score


def json_or_none(value: Any, path: str) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    raise AppError(f"`{path}` must be a string, array, object, or null.")


def validate_weekdays(value: Any, path: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise AppError(f"`{path}` must be an array of weekday numbers.")
    weekdays: list[int] = []
    for index, item in enumerate(value):
        if not isinstance(item, int) or item < 1 or item > 7:
            raise AppError(f"`{path}[{index}]` must be an integer from 1 to 7.")
        weekdays.append(item)
    if not weekdays:
        raise AppError(f"`{path}` cannot be empty.")
    return json.dumps(sorted(set(weekdays)), ensure_ascii=False)


def validate_recurrence(value: Any, index: int) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise AppError(f"`operations[{index}].item.recurrence` must be an object.")

    frequency = value.get("frequency")
    if frequency not in VALID_RECURRENCE_FREQUENCIES:
        raise AppError(f"`operations[{index}].item.recurrence.frequency` must be daily, weekly, or monthly.")

    try:
        interval = int(value.get("interval", 1))
    except (TypeError, ValueError) as exc:
        raise AppError(f"`operations[{index}].item.recurrence.interval` must be an integer.") from exc
    if interval < 1:
        raise AppError(f"`operations[{index}].item.recurrence.interval` must be greater than 0.")

    start_date = parse_iso_date(value.get("start_date"), f"operations[{index}].item.recurrence.start_date")
    active_until_value = value.get("active_until")
    active_until = parse_iso_date(active_until_value, f"operations[{index}].item.recurrence.active_until") if active_until_value else None
    if active_until and active_until < start_date:
        raise AppError("`recurrence.active_until` must be on or after `recurrence.start_date`.")

    by_weekday = validate_weekdays(value.get("by_weekday"), f"operations[{index}].item.recurrence.by_weekday")
    by_month_day = value.get("by_month_day")
    if by_month_day is not None:
        try:
            by_month_day = int(by_month_day)
        except (TypeError, ValueError) as exc:
            raise AppError("`recurrence.by_month_day` must be an integer.") from exc
        if by_month_day < 1 or by_month_day > 31:
            raise AppError("`recurrence.by_month_day` must be between 1 and 31.")

    if frequency == "weekly" and by_weekday is None:
        by_weekday = json.dumps([start_date.isoweekday()], ensure_ascii=False)
    if frequency != "weekly" and by_weekday is not None:
        raise AppError("`recurrence.by_weekday` is only valid for weekly recurrence.")
    if frequency == "monthly" and by_month_day is None:
        by_month_day = start_date.day
    if frequency != "monthly" and by_month_day is not None:
        raise AppError("`recurrence.by_month_day` is only valid for monthly recurrence.")

    return {
        "id": value.get("id") or make_id("RR"),
        "frequency": frequency,
        "interval": interval,
        "by_weekday": by_weekday,
        "by_month_day": by_month_day,
        "start_date": start_date.isoformat(),
        "active_until": active_until.isoformat() if active_until else None,
        "timezone": value.get("timezone", "Asia/Shanghai"),
    }


def validate_record(payload: dict[str, Any], ts: str) -> dict[str, Any]:
    record = require_object(payload, "record")
    canonical_text = record.get("canonical_text")
    if not isinstance(canonical_text, str) or not canonical_text.strip():
        raise AppError("`record.canonical_text` is required.")

    input_type = record.get("input_type", "text")
    if input_type not in {"text", "image", "audio", "mixed"}:
        raise AppError("`record.input_type` must be text, image, audio, or mixed.")

    parse_status = record.get("parse_status", "parsed")
    if parse_status not in VALID_PARSE_STATUS:
        raise AppError("`record.parse_status` must be parsed, needs_review, ignored, or failed.")

    original_retained = int(record.get("original_retained", 0))
    if original_retained not in {0, 1}:
        raise AppError("`record.original_retained` must be 0 or 1.")

    return {
        "id": record.get("id") or make_id("R"),
        "source": record.get("source", "codex"),
        "input_type": input_type,
        "canonical_text": canonical_text.strip(),
        "raw_text": record.get("raw_text", canonical_text if input_type == "text" else None),
        "extraction_method": record.get("extraction_method", "user_text" if input_type == "text" else "mixed"),
        "extraction_confidence": validate_confidence(record.get("extraction_confidence", 1.0), "record.extraction_confidence"),
        "original_retained": original_retained,
        "language": record.get("language", "zh"),
        "timezone": record.get("timezone", "Asia/Shanghai"),
        "parse_status": parse_status,
        "parse_confidence": validate_confidence(record.get("parse_confidence"), "record.parse_confidence"),
        "created_at": record.get("created_at", ts),
        "updated_at": record.get("updated_at", ts),
    }


def validate_item(operation: dict[str, Any], index: int) -> tuple[str, dict[str, Any]]:
    if not isinstance(operation, dict):
        raise AppError(f"`operations[{index}]` must be an object.")
    action = operation.get("action")
    if action != "create":
        raise AppError(f"`operations[{index}].action` currently supports only `create`.")
    temp_id = operation.get("temp_id") or f"item_{index + 1}"
    if not isinstance(temp_id, str):
        raise AppError(f"`operations[{index}].temp_id` must be a string.")
    item = operation.get("item")
    if not isinstance(item, dict):
        raise AppError(f"`operations[{index}].item` must be an object.")

    item_type = item.get("type")
    if item_type not in VALID_ITEM_TYPES:
        raise AppError(f"`operations[{index}].item.type` must be task or event.")
    title = item.get("title")
    if not isinstance(title, str) or not title.strip():
        raise AppError(f"`operations[{index}].item.title` is required.")
    status = item.get("status", "active")
    if status not in VALID_ITEM_STATUS:
        raise AppError(f"`operations[{index}].item.status` is invalid.")

    all_day = int(item.get("all_day", 0))
    if all_day not in {0, 1}:
        raise AppError(f"`operations[{index}].item.all_day` must be 0 or 1.")

    if item_type == "task" and not item.get("due_at") and item.get("start_at"):
        raise AppError(f"`operations[{index}]` looks like a task but has start_at instead of due_at.")
    if item_type == "event" and not item.get("start_at") and not all_day:
        raise AppError(f"`operations[{index}]` event requires start_at unless all_day is 1.")

    return temp_id, {
        "id": item.get("id") or make_id("I"),
        "type": item_type,
        "title": title.strip(),
        "content": item.get("content"),
        "status": status,
        "confidence": validate_confidence(item.get("confidence"), f"operations[{index}].item.confidence"),
        "due_at": item.get("due_at"),
        "start_at": item.get("start_at"),
        "end_at": item.get("end_at"),
        "all_day": all_day,
        "project": item.get("project"),
        "people": json_or_none(item.get("people"), f"operations[{index}].item.people"),
        "location": item.get("location"),
        "recurrence": validate_recurrence(item.get("recurrence"), index),
    }


def insert_record(conn: sqlite3.Connection, record: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO records (
          id, source, input_type, canonical_text, raw_text, extraction_method,
          extraction_confidence, original_retained, language, timezone,
          parse_status, parse_confidence, created_at, updated_at
        )
        VALUES (
          :id, :source, :input_type, :canonical_text, :raw_text, :extraction_method,
          :extraction_confidence, :original_retained, :language, :timezone,
          :parse_status, :parse_confidence, :created_at, :updated_at
        )
        """,
        record,
    )


def insert_item(conn: sqlite3.Connection, item: dict[str, Any], record_id: str, ts: str) -> None:
    item_values = {key: value for key, value in item.items() if key != "recurrence"}
    conn.execute(
        """
        INSERT INTO items (
          id, type, title, content, status, confidence, due_at, start_at, end_at,
          all_day, project, people, location, created_from_record_id, created_at,
          updated_at, completed_at
        )
        VALUES (
          :id, :type, :title, :content, :status, :confidence, :due_at, :start_at,
          :end_at, :all_day, :project, :people, :location, :created_from_record_id,
          :created_at, :updated_at, :completed_at
        )
        """,
        {
            **item_values,
            "created_from_record_id": record_id,
            "created_at": ts,
            "updated_at": ts,
            "completed_at": ts if item["status"] == "completed" else None,
        },
    )


def insert_recurrence_rule(
    conn: sqlite3.Connection,
    item_id: str,
    recurrence: dict[str, Any],
    ts: str,
) -> dict[str, Any]:
    rule = {
        **recurrence,
        "item_id": item_id,
        "created_at": ts,
        "updated_at": ts,
    }
    conn.execute(
        """
        INSERT INTO recurrence_rules (
          id, item_id, frequency, interval, by_weekday, by_month_day,
          start_date, active_until, timezone, created_at, updated_at
        )
        VALUES (
          :id, :item_id, :frequency, :interval, :by_weekday, :by_month_day,
          :start_date, :active_until, :timezone, :created_at, :updated_at
        )
        """,
        rule,
    )
    return rule


def insert_item_event(
    conn: sqlite3.Connection,
    item_id: str,
    record_id: str,
    action: str,
    after_json: dict[str, Any] | None,
    confidence: float | None,
    note: str | None,
    ts: str,
    before_json: dict[str, Any] | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO item_events (
          id, item_id, record_id, action, before_json, after_json,
          confidence, note, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            make_id("E"),
            item_id,
            record_id,
            action,
            json.dumps(before_json, ensure_ascii=False) if before_json is not None else None,
            json.dumps(after_json, ensure_ascii=False) if after_json is not None else None,
            confidence,
            note,
            ts,
        ),
    )


def insert_relation(
    conn: sqlite3.Connection,
    from_item_id: str,
    to_item_id: str,
    relation_type: str,
    record_id: str,
    ts: str,
) -> None:
    if relation_type not in VALID_RELATIONS:
        raise AppError(f"Invalid relation_type: {relation_type}")
    conn.execute(
        """
        INSERT OR IGNORE INTO item_relations (
          id, from_item_id, to_item_id, relation_type, source_record_id, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (make_id("L"), from_item_id, to_item_id, relation_type, record_id, ts),
    )


def insert_review(
    conn: sqlite3.Connection,
    record_id: str,
    review: dict[str, Any],
    temp_to_item_id: dict[str, str],
    ts: str,
) -> dict[str, Any]:
    if not isinstance(review, dict):
        raise AppError("`review` must be an object when provided.")
    reason = review.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        raise AppError("`review.reason` is required.")
    status = review.get("status", "open")
    if status not in VALID_REVIEW_STATUS:
        raise AppError("`review.status` must be open, resolved, or dismissed.")
    item_ref = review.get("item_temp_id") or review.get("item_id")
    item_id = temp_to_item_id.get(item_ref, item_ref) if item_ref else None
    review_id = review.get("id") or make_id("Q")
    conn.execute(
        """
        INSERT INTO review_queue (
          id, record_id, item_id, reason, question, status, created_at, resolved_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            review_id,
            record_id,
            item_id,
            reason.strip(),
            review.get("question"),
            status,
            ts,
            review.get("resolved_at"),
        ),
    )
    return {"id": review_id, "reason": reason, "question": review.get("question"), "status": status}


def fetch_apply_verification(db_path: Path, record_id: str, item_ids: list[str]) -> dict[str, Any]:
    with connect(db_path) as conn:
        record_row = conn.execute(
            """
            SELECT id, source, input_type, canonical_text, parse_status,
                   parse_confidence, created_at, updated_at
            FROM records
            WHERE id = ?
            """,
            (record_id,),
        ).fetchone()
        if record_row is None:
            raise AppError(f"Read-back failed: record not found after write: {record_id}")

        item_rows: list[dict[str, Any]] = []
        if item_ids:
            placeholders = ",".join("?" for _ in item_ids)
            rows = conn.execute(
                f"""
                SELECT *
                FROM items
                WHERE id IN ({placeholders})
                """,
                item_ids,
            ).fetchall()
            by_id = {row["id"]: row_to_dict(row) for row in rows}
            item_rows = [by_id[item_id] for item_id in item_ids if item_id in by_id]
            missing = [item_id for item_id in item_ids if item_id not in by_id]
            if missing:
                raise AppError(f"Read-back failed: item not found after write: {', '.join(missing)}")

        relations = [
            row_to_dict(row)
            for row in conn.execute(
                """
                SELECT *
                FROM item_relations
                WHERE source_record_id = ?
                ORDER BY created_at, id
                """,
                (record_id,),
            )
        ]
        reviews = [
            row_to_dict(row)
            for row in conn.execute(
                """
                SELECT *
                FROM review_queue
                WHERE record_id = ?
                ORDER BY created_at, id
                """,
                (record_id,),
            )
        ]
        events = [
            row_to_dict(row)
            for row in conn.execute(
                """
                SELECT id, item_id, record_id, action, confidence, note, created_at
                FROM item_events
                WHERE record_id = ?
                ORDER BY created_at, id
                """,
                (record_id,),
            )
        ]
        recurrence_rules = [
            row_to_dict(row)
            for row in conn.execute(
                """
                SELECT *
                FROM recurrence_rules
                WHERE item_id IN (
                  SELECT id FROM items WHERE created_from_record_id = ?
                )
                ORDER BY created_at, id
                """,
                (record_id,),
            )
        ]

    return {
        "read_after_write": True,
        "record": row_to_dict(record_row),
        "items": item_rows,
        "relations": relations,
        "recurrence_rules": recurrence_rules,
        "reviews": reviews,
        "item_events": events,
    }


def apply_json(config: AppConfig, payload: dict[str, Any]) -> None:
    ensure_initialized(config.db_path)
    ts = now_iso()
    record = validate_record(payload, ts)
    operations = optional_list(payload, "operations")
    relations = optional_list(payload, "relations")
    review = payload.get("review")

    temp_to_item_id: dict[str, str] = {}
    normalized_items: dict[str, dict[str, Any]] = {}

    for index, operation in enumerate(operations):
        temp_id, item = validate_item(operation, index)
        temp_to_item_id[temp_id] = item["id"]
        normalized_items[temp_id] = item

    with connect(config.db_path, writable=True) as conn, transaction(conn):
        insert_record(conn, record)
        for temp_id, item in normalized_items.items():
            insert_item(conn, item, record["id"], ts)
            recurrence = item.get("recurrence")
            if recurrence:
                insert_recurrence_rule(conn, item["id"], recurrence, ts)
            item_event_after = {key: value for key, value in item.items() if key != "recurrence"}
            insert_item_event(
                conn,
                item_id=item["id"],
                record_id=record["id"],
                action="create",
                after_json=item_event_after,
                confidence=item.get("confidence"),
                note=None,
                ts=ts,
            )

        created_relations: list[dict[str, Any]] = []
        for index, relation in enumerate(relations):
            if not isinstance(relation, dict):
                raise AppError(f"`relations[{index}]` must be an object.")
            from_ref = relation.get("from_temp_id") or relation.get("from_item_id")
            to_ref = relation.get("to_temp_id") or relation.get("to_item_id")
            relation_type = relation.get("relation_type")
            from_item_id = temp_to_item_id.get(from_ref, from_ref)
            to_item_id = temp_to_item_id.get(to_ref, to_ref)
            if not from_item_id or not to_item_id or not relation_type:
                raise AppError(f"`relations[{index}]` requires from, to, and relation_type.")
            insert_relation(conn, from_item_id, to_item_id, relation_type, record["id"], ts)
            created_relations.append(
                {"from_item_id": from_item_id, "to_item_id": to_item_id, "relation_type": relation_type}
            )

        created_review = None
        if review:
            created_review = insert_review(conn, record["id"], review, temp_to_item_id, ts)

    item_ids = [item["id"] for item in normalized_items.values()]
    verification = fetch_apply_verification(config.db_path, record["id"], item_ids)

    print_json(
        {
            "status": "ok",
            "record": {"id": record["id"], "parse_status": record["parse_status"]},
            "created_items": verification["items"],
            "created_relations": created_relations,
            "created_recurrence_rules": verification["recurrence_rules"],
            "review": created_review,
            "verification": verification,
        }
    )


def parse_date_arg(value: str, arg_name: str) -> date:
    try:
        return datetime.fromisoformat(value).date()
    except ValueError as exc:
        raise AppError(f"{arg_name} must be YYYY-MM-DD.") from exc


def parse_iso_date(value: Any, path: str) -> date:
    if not isinstance(value, str) or not value.strip():
        raise AppError(f"`{path}` must be a date in YYYY-MM-DD format.")
    try:
        return date.fromisoformat(value.strip())
    except ValueError as exc:
        raise AppError(f"`{path}` must be a date in YYYY-MM-DD format.") from exc


def item_anchor_datetime(item: dict[str, Any]) -> datetime | None:
    value = item.get("due_at") if item["type"] == "task" else item.get("start_at")
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise AppError(f"Invalid item time: {value}") from exc


def item_anchor_time(item: dict[str, Any]) -> str | None:
    anchor = item_anchor_datetime(item)
    if anchor is None:
        return None
    return anchor.timetz().replace(tzinfo=None).isoformat(timespec="seconds")


def combine_date_with_item_time(item: dict[str, Any], occurrence_date: date) -> str | None:
    anchor = item_anchor_datetime(item)
    if anchor is None:
        return None
    combined = datetime.combine(occurrence_date, anchor.timetz().replace(tzinfo=LOCAL_TZ))
    return combined.replace(microsecond=0).isoformat()


def add_months(day: date, months: int) -> date:
    month_index = day.month - 1 + months
    year = day.year + month_index // 12
    month = month_index % 12 + 1
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)
    last_day = (next_month - timedelta(days=1)).day
    return date(year, month, min(day.day, last_day))


def recurrence_matches_date(rule: dict[str, Any], occurrence_date: date) -> bool:
    start = date.fromisoformat(rule["start_date"])
    if occurrence_date < start:
        return False
    active_until = rule.get("active_until")
    if active_until and occurrence_date > date.fromisoformat(active_until):
        return False

    interval = int(rule["interval"])
    frequency = rule["frequency"]
    if frequency == "daily":
        return (occurrence_date - start).days % interval == 0
    if frequency == "weekly":
        weeks = (occurrence_date - start).days // 7
        if weeks < 0 or weeks % interval != 0:
            return False
        weekdays = json.loads(rule["by_weekday"]) if rule.get("by_weekday") else [start.isoweekday()]
        return occurrence_date.isoweekday() in weekdays
    if frequency == "monthly":
        months = (occurrence_date.year - start.year) * 12 + occurrence_date.month - start.month
        if months < 0 or months % interval != 0:
            return False
        month_day = int(rule["by_month_day"] or start.day)
        return occurrence_date.day == month_day
    return False


def recurrence_date_matches_pattern(rule: dict[str, Any], occurrence_date: date) -> bool:
    rule_without_end = dict(rule)
    rule_without_end["active_until"] = None
    return recurrence_matches_date(rule_without_end, occurrence_date)


def expand_recurrence_dates(rule: dict[str, Any], start_day: date, end_day: date) -> list[date]:
    if end_day < start_day:
        return []
    rule_start = date.fromisoformat(rule["start_date"])
    active_until = date.fromisoformat(rule["active_until"]) if rule.get("active_until") else None
    current = max(start_day, rule_start)
    final = min(end_day, active_until) if active_until else end_day
    if final < current:
        return []

    dates: list[date] = []
    while current <= final:
        if recurrence_matches_date(rule, current):
            dates.append(current)
        current += timedelta(days=1)
    return dates


def recurrence_time_delta(item: dict[str, Any], from_date: date, to_date: date) -> timedelta:
    if item["type"] != "event" or not item.get("start_at") or not item.get("end_at"):
        return timedelta(0)
    try:
        start = datetime.fromisoformat(item["start_at"])
        end = datetime.fromisoformat(item["end_at"])
    except ValueError:
        return timedelta(0)
    return end - start


def build_recurrence_occurrence(
    item: dict[str, Any],
    rule: dict[str, Any],
    occurrence_date: date,
    status_row: dict[str, Any] | None,
    query_status: str,
) -> dict[str, Any] | None:
    occurrence_status = status_row.get("status") if status_row else None
    today = datetime.now(LOCAL_TZ).date()
    effective_status = occurrence_status or ("missed" if occurrence_date < today else "active")

    if query_status != "all":
        if query_status == "active" and (occurrence_status is not None or occurrence_date < today):
            return None
        if query_status in {"completed", "cancelled"} and occurrence_status != query_status:
            return None

    result = dict(item)
    result["status"] = effective_status
    result["recurrence"] = {
        "rule_id": rule["id"],
        "occurrence_date": occurrence_date.isoformat(),
    }
    result["completed_at"] = status_row.get("completed_at") if status_row and occurrence_status == "completed" else None
    if item["type"] == "task":
        result["due_at"] = combine_date_with_item_time(item, occurrence_date)
    else:
        result["start_at"] = combine_date_with_item_time(item, occurrence_date)
        if item.get("end_at") and result["start_at"]:
            start = datetime.fromisoformat(result["start_at"])
            result["end_at"] = (start + recurrence_time_delta(item, occurrence_date, occurrence_date)).isoformat()

    if status_row and status_row.get("override_json"):
        try:
            overrides = json.loads(status_row["override_json"])
        except json.JSONDecodeError:
            overrides = {}
        if isinstance(overrides, dict):
            result.update(overrides)
    return result


def fetch_recurrence_rule(conn: sqlite3.Connection, item_id: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM recurrence_rules WHERE item_id = ?", (item_id,)).fetchone()
    return row_to_dict(row) if row else None


def fetch_recurrence_statuses(
    conn: sqlite3.Connection,
    rule_ids: list[str],
    start_day: date,
    end_day: date,
) -> dict[tuple[str, str], dict[str, Any]]:
    if not rule_ids:
        return {}
    placeholders = ",".join("?" for _ in rule_ids)
    rows = conn.execute(
        f"""
        SELECT *
        FROM recurrence_status
        WHERE rule_id IN ({placeholders})
          AND occurrence_date >= ?
          AND occurrence_date <= ?
        """,
        (*rule_ids, start_day.isoformat(), end_day.isoformat()),
    ).fetchall()
    return {(row["rule_id"], row["occurrence_date"]): row_to_dict(row) for row in rows}


def upsert_recurrence_status(
    conn: sqlite3.Connection,
    rule: dict[str, Any],
    item_id: str,
    occurrence_date: date,
    status: str | None,
    ts: str,
    *,
    override_json: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if status is not None and status not in VALID_RECURRENCE_STATUS:
        raise AppError("Recurrence status must be completed or cancelled.")
    existing = conn.execute(
        "SELECT * FROM recurrence_status WHERE rule_id = ? AND occurrence_date = ?",
        (rule["id"], occurrence_date.isoformat()),
    ).fetchone()
    completed_at = ts if status == "completed" else None
    cancelled_at = ts if status == "cancelled" else None
    override_text = json.dumps(override_json, ensure_ascii=False) if override_json is not None else None
    if existing:
        next_status = status if status is not None else existing["status"]
        next_completed_at = completed_at if status == "completed" else (None if status == "cancelled" else existing["completed_at"])
        next_cancelled_at = cancelled_at if status == "cancelled" else (None if status == "completed" else existing["cancelled_at"])
        conn.execute(
            """
            UPDATE recurrence_status
            SET status = ?, override_json = COALESCE(?, override_json),
                completed_at = ?, cancelled_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (next_status, override_text, next_completed_at, next_cancelled_at, ts, existing["id"]),
        )
        row_id = existing["id"]
    else:
        row_id = make_id("RS")
        conn.execute(
            """
            INSERT INTO recurrence_status (
              id, rule_id, item_id, occurrence_date, status, override_json,
              completed_at, cancelled_at, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row_id,
                rule["id"],
                item_id,
                occurrence_date.isoformat(),
                status,
                override_text,
                completed_at,
                cancelled_at,
                ts,
                ts,
            ),
        )
    return row_to_dict(conn.execute("SELECT * FROM recurrence_status WHERE id = ?", (row_id,)).fetchone())


def fetch_recurring_items(conn: sqlite3.Connection, item_type: str | None = None) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    type_sql = "AND items.type = ?" if item_type else ""
    params: tuple[Any, ...] = (item_type,) if item_type else ()
    rows = conn.execute(
        f"""
        SELECT
          items.*,
          recurrence_rules.id AS rule_id,
          recurrence_rules.frequency AS rule_frequency,
          recurrence_rules.interval AS rule_interval,
          recurrence_rules.by_weekday AS rule_by_weekday,
          recurrence_rules.by_month_day AS rule_by_month_day,
          recurrence_rules.start_date AS rule_start_date,
          recurrence_rules.active_until AS rule_active_until,
          recurrence_rules.timezone AS rule_timezone,
          recurrence_rules.created_at AS rule_created_at,
          recurrence_rules.updated_at AS rule_updated_at
        FROM items
        JOIN recurrence_rules ON recurrence_rules.item_id = items.id
        WHERE 1 = 1
          {type_sql}
        ORDER BY items.created_at, items.id
        """,
        params,
    ).fetchall()

    result: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for row in rows:
        data = row_to_dict(row)
        item = {key: data[key] for key in ITEMS_BACKUP_TABLE_COLUMNS["items"]}
        rule = {
            "id": data["rule_id"],
            "item_id": data["id"],
            "frequency": data["rule_frequency"],
            "interval": data["rule_interval"],
            "by_weekday": data["rule_by_weekday"],
            "by_month_day": data["rule_by_month_day"],
            "start_date": data["rule_start_date"],
            "active_until": data["rule_active_until"],
            "timezone": data["rule_timezone"],
            "created_at": data["rule_created_at"],
            "updated_at": data["rule_updated_at"],
        }
        result.append((item, rule))
    return result


def query_recurrence_occurrences(
    conn: sqlite3.Connection,
    item_type: str,
    start_day: date,
    end_day: date,
    status: str,
) -> list[dict[str, Any]]:
    recurring = fetch_recurring_items(conn, item_type)
    rule_ids = [rule["id"] for _, rule in recurring]
    statuses = fetch_recurrence_statuses(conn, rule_ids, start_day, end_day)
    occurrences: list[dict[str, Any]] = []

    for item, rule in recurring:
        dates = expand_recurrence_dates(rule, start_day, end_day)
        for occurrence_date in dates:
            status_row = statuses.get((rule["id"], occurrence_date.isoformat()))
            if item["status"] != "active" and not status_row:
                continue
            occurrence = build_recurrence_occurrence(item, rule, occurrence_date, status_row, status)
            if occurrence:
                occurrences.append(occurrence)

    time_key = "due_at" if item_type == "task" else "start_at"
    return sorted(occurrences, key=lambda row: (row.get(time_key) or "", row.get("created_at") or ""))


def find_next_recurrence_occurrences(
    conn: sqlite3.Connection,
    item_type: str,
    after_day: date,
    *,
    limit_days: int = 366,
) -> list[dict[str, Any]]:
    end_day = after_day + timedelta(days=limit_days)
    occurrences: list[dict[str, Any]] = []
    for item, rule in fetch_recurring_items(conn, item_type):
        if item["status"] != "active":
            continue
        for occurrence_date in expand_recurrence_dates(rule, after_day, end_day):
            statuses = fetch_recurrence_statuses(conn, [rule["id"]], occurrence_date, occurrence_date)
            status_row = statuses.get((rule["id"], occurrence_date.isoformat()))
            occurrence = build_recurrence_occurrence(item, rule, occurrence_date, status_row, "active")
            if occurrence:
                occurrences.append(occurrence)
                break
    time_key = "due_at" if item_type == "task" else "start_at"
    return sorted(occurrences, key=lambda row: (row.get(time_key) or "", row.get("created_at") or ""))


def resolve_query_range(
    date_text: str | None,
    period: str | None,
    from_text: str | None,
    to_text: str | None,
) -> tuple[date, date, str]:
    if (from_text is None) != (to_text is None):
        raise AppError("Use --from and --to together.")

    range_modes = [date_text is not None, period is not None, from_text is not None]
    if sum(range_modes) > 1:
        raise AppError("Use only one of --date, --period, or --from/--to.")

    today = datetime.now(LOCAL_TZ).date()
    if date_text:
        day = parse_date_arg(date_text, "--date")
        return day, day, "date"
    if from_text and to_text:
        start_day = parse_date_arg(from_text, "--from")
        end_day = parse_date_arg(to_text, "--to")
        if end_day < start_day:
            raise AppError("--to must be on or after --from.")
        return start_day, end_day, "custom"

    period = period or "today"
    if period == "today":
        return today, today, "today"
    if period == "week":
        start_day = today - timedelta(days=today.weekday())
        return start_day, start_day + timedelta(days=6), "week"
    if period == "month":
        start_day = today.replace(day=1)
        next_month = start_day.replace(year=start_day.year + 1, month=1) if start_day.month == 12 else start_day.replace(month=start_day.month + 1)
        return start_day, next_month - timedelta(days=1), "month"
    raise AppError("Invalid --period. Expected one of: today, week, month.")


def item_status_clause(status: str) -> tuple[str, list[Any]]:
    if status == "all":
        return "", []
    return "AND status = ?", [status]


def review_status_clause(status: str) -> tuple[str, list[Any]]:
    if status == "all":
        return "", []
    review_status = QUERY_REVIEW_STATUS.get(status)
    if review_status is None:
        raise AppError(f"Invalid review status mapping for: {status}")
    return "AND review_queue.status = ?", [review_status]


def query_range(
    config: AppConfig,
    date_text: str | None,
    period: str | None,
    from_text: str | None,
    to_text: str | None,
    item_type: str | None,
    status: str | None,
) -> None:
    ensure_initialized(config.db_path)
    if item_type and item_type not in {"task", "event", "reviews"}:
        raise AppError("Invalid --type. Expected one of: task, event, reviews.")
    status = status or "active"
    if status not in QUERY_ITEM_STATUS:
        raise AppError("Invalid --status. Expected one of: active, completed, cancelled, all.")

    start_day, end_day, resolved_period = resolve_query_range(date_text, period, from_text, to_text)
    start = datetime.combine(start_day, datetime.min.time(), tzinfo=LOCAL_TZ).isoformat()
    end_exclusive = datetime.combine(end_day + timedelta(days=1), datetime.min.time(), tzinfo=LOCAL_TZ).isoformat()

    include_tasks = item_type in {None, "task"}
    include_events = item_type in {None, "event"}
    include_reviews = item_type in {None, "reviews"}
    explicit_range = any(value is not None for value in (date_text, period, from_text, to_text))
    filter_reviews_by_range = item_type is None or explicit_range

    payload: dict[str, Any] = {
        "range": {
            "from": start_day.isoformat(),
            "to": end_day.isoformat(),
            "period": resolved_period,
        },
        "filters": {
            "type": item_type,
            "status": status,
        },
    }

    item_status_sql, item_status_params = item_status_clause(status)
    review_status_sql, review_status_params = review_status_clause(status)

    with connect(config.db_path) as conn:
        if include_events:
            events_in_range = [
                row_to_dict(row)
                for row in conn.execute(
                    f"""
                    SELECT * FROM items
                    WHERE type = 'event'
                      {item_status_sql}
                      AND NOT EXISTS (SELECT 1 FROM recurrence_rules WHERE recurrence_rules.item_id = items.id)
                      AND start_at IS NOT NULL
                      AND start_at >= ?
                      AND start_at < ?
                    ORDER BY start_at, created_at
                    """,
                    (*item_status_params, start, end_exclusive),
                )
            ]
            next_upcoming_event = None
            if status in {"active", "all"}:
                next_upcoming_event = conn.execute(
                    """
                    SELECT * FROM items
                    WHERE type = 'event'
                      AND status = 'active'
                      AND NOT EXISTS (SELECT 1 FROM recurrence_rules WHERE recurrence_rules.item_id = items.id)
                      AND start_at IS NOT NULL
                      AND start_at >= ?
                    ORDER BY start_at, created_at
                    LIMIT 1
                    """,
                    (end_exclusive,),
                ).fetchone()
            recurring_events = query_recurrence_occurrences(conn, "event", start_day, end_day, status)
            events_in_range.extend(recurring_events)
            events_in_range.sort(key=lambda row: (row.get("start_at") or "", row.get("created_at") or ""))

            next_upcoming = row_to_dict(next_upcoming_event) if next_upcoming_event else None
            if status in {"active", "all"}:
                next_recurring_events = find_next_recurrence_occurrences(conn, "event", end_day + timedelta(days=1))
                candidates = [candidate for candidate in [next_upcoming, *next_recurring_events] if candidate]
                if candidates:
                    next_upcoming = sorted(candidates, key=lambda row: (row.get("start_at") or "", row.get("created_at") or ""))[0]

            payload["events"] = {
                "in_range": events_in_range,
                "next_upcoming": next_upcoming,
            }

        if include_tasks:
            tasks_due_in_range = [
                row_to_dict(row)
                for row in conn.execute(
                    f"""
                    SELECT * FROM items
                    WHERE type = 'task'
                      {item_status_sql}
                      AND NOT EXISTS (SELECT 1 FROM recurrence_rules WHERE recurrence_rules.item_id = items.id)
                      AND due_at IS NOT NULL
                      AND due_at >= ?
                      AND due_at < ?
                    ORDER BY due_at, created_at
                    """,
                    (*item_status_params, start, end_exclusive),
                )
            ]
            overdue_tasks = []
            upcoming_tasks = []
            if status in {"active", "all"}:
                overdue_tasks = [
                    row_to_dict(row)
                    for row in conn.execute(
                        """
                        SELECT * FROM items
                        WHERE type = 'task'
                          AND status = 'active'
                          AND NOT EXISTS (SELECT 1 FROM recurrence_rules WHERE recurrence_rules.item_id = items.id)
                          AND due_at IS NOT NULL
                          AND due_at < ?
                        ORDER BY due_at, created_at
                        """,
                        (start,),
                    )
                ]
                upcoming_tasks = [
                    row_to_dict(row)
                    for row in conn.execute(
                        """
                        SELECT * FROM items
                        WHERE type = 'task'
                          AND status = 'active'
                          AND NOT EXISTS (SELECT 1 FROM recurrence_rules WHERE recurrence_rules.item_id = items.id)
                          AND due_at IS NOT NULL
                          AND due_at >= ?
                        ORDER BY due_at, created_at
                        """,
                        (end_exclusive,),
                    )
                ]
            tasks_without_due_at = [
                row_to_dict(row)
                for row in conn.execute(
                    f"""
                    SELECT * FROM items
                    WHERE type = 'task'
                      {item_status_sql}
                      AND NOT EXISTS (SELECT 1 FROM recurrence_rules WHERE recurrence_rules.item_id = items.id)
                      AND due_at IS NULL
                    ORDER BY created_at
                    """,
                    item_status_params,
                )
            ]
            recurring_tasks_due_in_range = query_recurrence_occurrences(conn, "task", start_day, end_day, status)
            tasks_due_in_range.extend(recurring_tasks_due_in_range)
            tasks_due_in_range.sort(key=lambda row: (row.get("due_at") or "", row.get("created_at") or ""))
            if status in {"active", "all"}:
                upcoming_tasks.extend(find_next_recurrence_occurrences(conn, "task", end_day + timedelta(days=1)))
                upcoming_tasks.sort(key=lambda row: (row.get("due_at") or "", row.get("created_at") or ""))

            payload["tasks"] = {
                "overdue_before_range": overdue_tasks,
                "due_in_range": tasks_due_in_range,
                "upcoming_after_range": upcoming_tasks,
                "without_due_at": tasks_without_due_at,
            }

        if include_reviews:
            review_range_sql = ""
            review_params = list(review_status_params)
            if filter_reviews_by_range:
                review_range_sql = "AND review_queue.created_at >= ? AND review_queue.created_at < ?"
                review_params.extend([start, end_exclusive])
            reviews = [
                row_to_dict(row)
                for row in conn.execute(
                    f"""
                    SELECT review_queue.*, records.canonical_text
                    FROM review_queue
                    JOIN records ON records.id = review_queue.record_id
                    WHERE 1 = 1
                      {review_status_sql}
                      {review_range_sql}
                    ORDER BY review_queue.created_at
                    """,
                    review_params,
                )
            ]
            payload["reviews"] = reviews

    print_json(payload)


def fetch_review(conn: sqlite3.Connection, review_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT review_queue.*, records.canonical_text
        FROM review_queue
        JOIN records ON records.id = review_queue.record_id
        WHERE review_queue.id = ?
        """,
        (review_id,),
    ).fetchone()
    return row_to_dict(row) if row else None


def update_review(config: AppConfig, review_id: str, status: str, item_id: str | None = None) -> None:
    ensure_initialized(config.db_path)
    review_id = review_id.strip()
    if not review_id:
        raise AppError("`--review-id` is required.")
    if status not in VALID_REVIEW_STATUS:
        raise AppError("`--status` must be open, resolved, or dismissed.")

    item_id = item_id.strip() if item_id is not None else None
    if item_id == "":
        raise AppError("`--item-id` cannot be empty.")

    ts = now_iso()
    resolved_at = None if status == "open" else ts
    with connect(config.db_path, writable=True) as conn, transaction(conn):
        existing = fetch_review(conn, review_id)
        if existing is None:
            raise AppError(f"Review not found: {review_id}")
        if item_id is not None:
            item_row = conn.execute("SELECT id FROM items WHERE id = ?", (item_id,)).fetchone()
            if item_row is None:
                raise AppError(f"Item not found: {item_id}")

        set_parts = ["status = ?", "resolved_at = ?"]
        values: list[Any] = [status, resolved_at]
        if item_id is not None:
            set_parts.append("item_id = ?")
            values.append(item_id)
        values.append(review_id)
        conn.execute(
            f"""
            UPDATE review_queue
            SET {", ".join(set_parts)}
            WHERE id = ?
            """,
            values,
        )
        updated = fetch_review(conn, review_id)

    print_json(
        {
            "status": "ok",
            "review": updated,
            "verification": {
                "read_after_write": True,
                "review": updated,
            },
        }
    )


UPDATE_ITEM_FIELDS = {
    "type",
    "title",
    "content",
    "status",
    "confidence",
    "due_at",
    "start_at",
    "end_at",
    "all_day",
    "project",
    "people",
    "location",
}
CLEARABLE_UPDATE_FIELDS = {
    "content",
    "confidence",
    "due_at",
    "start_at",
    "end_at",
    "project",
    "people",
    "location",
}

RECURRENCE_OVERRIDE_FIELDS = {
    "title",
    "content",
    "confidence",
    "due_at",
    "start_at",
    "end_at",
    "all_day",
    "project",
    "people",
    "location",
}


def normalize_update_fields(updates: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for field, value in updates.items():
        if field not in UPDATE_ITEM_FIELDS:
            raise AppError(f"Unsupported update field: {field}")
        if field in {"type", "status", "all_day"} and value is None:
            raise AppError(f"`{field}` cannot be cleared.")
        if field == "type" and value not in VALID_ITEM_TYPES:
            raise AppError("`type` must be task or event.")
        if field == "status" and value not in VALID_ITEM_STATUS:
            raise AppError("`status` is invalid.")
        if field == "title":
            if value is None:
                raise AppError("`title` cannot be cleared.")
            if not isinstance(value, str) or not value.strip():
                raise AppError("`title` cannot be empty.")
            value = value.strip()
        if field == "all_day":
            value = int(value)
            if value not in {0, 1}:
                raise AppError("`all_day` must be 0 or 1.")
        if field == "confidence":
            value = validate_confidence(value, "confidence")
        if field == "people":
            value = json_or_none(value, "people")
        normalized[field] = value
    return normalized


def update_item_fields(
    config: AppConfig,
    item_id: str,
    updates: dict[str, Any],
    *,
    action: str = "update",
    note: str | None = None,
) -> dict[str, Any]:
    ensure_initialized(config.db_path)
    normalized = normalize_update_fields(updates)
    if not normalized:
        raise AppError("No update fields provided.")

    ts = now_iso()
    with connect(config.db_path, writable=True) as conn, transaction(conn):
        row = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
        if row is None:
            raise AppError(f"Item not found: {item_id}")
        item = row_to_dict(row)
        before = dict(item)

        effective = {**item, **normalized}
        if effective["type"] == "event" and not effective.get("start_at") and not int(effective.get("all_day") or 0):
            raise AppError("Event items require start_at unless all_day is 1.")
        if effective["type"] == "task" and not effective.get("due_at") and effective.get("start_at"):
            raise AppError("Task items cannot use start_at instead of due_at.")

        completed_at = item.get("completed_at")
        if normalized.get("status") == "completed" and not completed_at:
            completed_at = ts
        elif normalized.get("status") in {"active", "cancelled", "needs_review"}:
            completed_at = None

        set_parts = [f"{field} = ?" for field in normalized]
        values = list(normalized.values())
        set_parts.extend(["completed_at = ?", "updated_at = ?"])
        values.extend([completed_at, ts, item_id])
        conn.execute(
            f"""
            UPDATE items
            SET {", ".join(set_parts)}
            WHERE id = ?
            """,
            values,
        )
        updated = row_to_dict(conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone())
        insert_item_event(
            conn,
            item_id=item_id,
            record_id=item["created_from_record_id"],
            action=action,
            before_json=before,
            after_json=updated,
            confidence=1.0,
            note=note,
            ts=ts,
        )
    return updated


def close_ended_recurrences(conn: sqlite3.Connection, ts: str) -> list[dict[str, Any]]:
    today = datetime.now(LOCAL_TZ).date().isoformat()
    rows = conn.execute(
        """
        SELECT items.*
        FROM items
        JOIN recurrence_rules ON recurrence_rules.item_id = items.id
        WHERE items.status = 'active'
          AND recurrence_rules.active_until IS NOT NULL
          AND recurrence_rules.active_until < ?
        ORDER BY items.created_at, items.id
        """,
        (today,),
    ).fetchall()
    closed: list[dict[str, Any]] = []
    for row in rows:
        item = row_to_dict(row)
        before = dict(item)
        conn.execute(
            """
            UPDATE items
            SET status = 'completed', completed_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (ts, ts, item["id"]),
        )
        updated = row_to_dict(conn.execute("SELECT * FROM items WHERE id = ?", (item["id"],)).fetchone())
        insert_item_event(
            conn,
            item_id=item["id"],
            record_id=item["created_from_record_id"],
            action="complete",
            before_json=before,
            after_json=updated,
            confidence=1.0,
            note="recurrence plan ended",
            ts=ts,
        )
        closed.append(updated)
    return closed


def choose_default_occurrence_date(conn: sqlite3.Connection, item: dict[str, Any], rule: dict[str, Any]) -> tuple[date | None, bool]:
    today = datetime.now(LOCAL_TZ).date()
    if recurrence_matches_date(rule, today):
        status_row = conn.execute(
            "SELECT status FROM recurrence_status WHERE rule_id = ? AND occurrence_date = ?",
            (rule["id"], today.isoformat()),
        ).fetchone()
        if status_row is None:
            return today, True

    start = date.fromisoformat(rule["start_date"])
    current = today - timedelta(days=1)
    floor = max(start, today - timedelta(days=366))
    while current >= floor:
        if recurrence_matches_date(rule, current):
            status_row = conn.execute(
                "SELECT status FROM recurrence_status WHERE rule_id = ? AND occurrence_date = ?",
                (rule["id"], current.isoformat()),
            ).fetchone()
            if status_row is None:
                return current, True
        current -= timedelta(days=1)

    current = today + timedelta(days=1)
    ceiling = today + timedelta(days=366)
    while current <= ceiling:
        if recurrence_matches_date(rule, current):
            status_row = conn.execute(
                "SELECT status FROM recurrence_status WHERE rule_id = ? AND occurrence_date = ?",
                (rule["id"], current.isoformat()),
            ).fetchone()
            if status_row is None:
                return current, True
        current += timedelta(days=1)
    return None, False


def complete_item(config: AppConfig, item_id: str, note: str | None, occurrence_date_text: str | None = None) -> None:
    ensure_initialized(config.db_path)
    ts = now_iso()
    with connect(config.db_path, writable=True) as conn, transaction(conn):
        closed_recurrences = close_ended_recurrences(conn, ts)
        row = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
        if row is None:
            raise AppError(f"Item not found: {item_id}")
        item = row_to_dict(row)
        rule = fetch_recurrence_rule(conn, item_id)
        if rule:
            if item["status"] == "cancelled":
                raise AppError("Cancelled recurring items cannot be completed.")
            if item["status"] == "completed":
                print_json({"status": "already_completed", "item": item, "closed_recurrences": closed_recurrences})
                return
            if occurrence_date_text:
                occurrence_date = parse_iso_date(occurrence_date_text, "--occurrence-date")
                auto_selected = False
            else:
                occurrence_date, auto_selected = choose_default_occurrence_date(conn, item, rule)
                if occurrence_date is None:
                    print_json(
                        {
                            "status": "requires_occurrence_date",
                            "message": "No default recurring occurrence was found. Specify --occurrence-date.",
                            "requires": ["--occurrence-date"],
                            "closed_recurrences": closed_recurrences,
                        }
                    )
                    return
            if not recurrence_date_matches_pattern(rule, occurrence_date):
                raise AppError("The requested occurrence date does not match the recurrence rule.")
            status_row = upsert_recurrence_status(conn, rule, item_id, occurrence_date, "completed", ts)
            print_json(
                {
                    "status": "completed",
                    "item": item,
                    "recurrence": {
                        "rule_id": rule["id"],
                        "occurrence_date": occurrence_date.isoformat(),
                        "auto_selected": auto_selected,
                    },
                    "recurrence_status": status_row,
                    "closed_recurrences": closed_recurrences,
                }
            )
            return

    if item["status"] == "completed":
        print_json({"status": "already_completed", "item": item})
        return
    if item["status"] == "cancelled":
        raise AppError("Cancelled items cannot be completed.")
    updated = update_item_fields(config, item_id, {"status": "completed"}, action="complete", note=note)
    print_json({"status": "completed", "item": updated})


def requires_scope_payload(action: str) -> dict[str, Any]:
    return {
        "status": "requires_scope",
        "message": f"This is a recurring item. Specify whether to {action} one occurrence or the whole series.",
        "allowed_scopes": ["occurrence", "series"],
        "requires": ["--scope", "--occurrence-date when --scope occurrence"],
    }


def cancel_item(
    config: AppConfig,
    item_id: str,
    note: str | None,
    scope: str | None = None,
    occurrence_date_text: str | None = None,
) -> None:
    ensure_initialized(config.db_path)
    with connect(config.db_path) as conn:
        row = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
        rule = fetch_recurrence_rule(conn, item_id) if row else None
    if row is None:
        raise AppError(f"Item not found: {item_id}")
    item = row_to_dict(row)
    if rule:
        if scope is None:
            print_json(requires_scope_payload("cancel"))
            return
        if scope == "occurrence":
            if not occurrence_date_text:
                raise AppError("--occurrence-date is required when --scope occurrence.")
            occurrence_date = parse_iso_date(occurrence_date_text, "--occurrence-date")
            if not recurrence_date_matches_pattern(rule, occurrence_date):
                raise AppError("The requested occurrence date does not match the recurrence rule.")
            ts = now_iso()
            with connect(config.db_path, writable=True) as conn, transaction(conn):
                status_row = upsert_recurrence_status(conn, rule, item_id, occurrence_date, "cancelled", ts)
            print_json(
                {
                    "status": "cancelled",
                    "item": item,
                    "recurrence": {"rule_id": rule["id"], "occurrence_date": occurrence_date.isoformat()},
                    "recurrence_status": status_row,
                }
            )
            return
        if scope != "series":
            raise AppError("--scope must be occurrence or series.")
    if item["status"] == "cancelled":
        print_json({"status": "already_cancelled", "item": item})
        return
    updated = update_item_fields(config, item_id, {"status": "cancelled"}, action="cancel", note=note)
    print_json({"status": "cancelled", "item": updated})


def parse_people_arg(value: str | None) -> Any:
    if value is None:
        return None
    text = value.strip()
    if text.startswith("[") or text.startswith("{"):
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            if text.startswith("[") and text.endswith("]"):
                values = [part.strip() for part in text[1:-1].split(",")]
                if values and all(values):
                    return values
            raise AppError(f"Invalid people JSON: {exc}") from exc
    return value


def update_item(config: AppConfig, args: argparse.Namespace) -> None:
    clear_fields = args.clear or []
    invalid_clear_fields = sorted(set(clear_fields) - CLEARABLE_UPDATE_FIELDS)
    if invalid_clear_fields:
        raise AppError(f"Unsupported clear field(s): {', '.join(invalid_clear_fields)}")

    updates: dict[str, Any] = {field: None for field in clear_fields}
    cli_fields = {
        "type": args.type,
        "title": args.title,
        "content": args.content,
        "status": args.status,
        "confidence": args.confidence,
        "due_at": args.due_at,
        "start_at": args.start_at,
        "end_at": args.end_at,
        "all_day": args.all_day,
        "project": args.project,
        "people": parse_people_arg(args.people) if args.people is not None else None,
        "location": args.location,
    }
    for field, value in cli_fields.items():
        if value is not None:
            updates[field] = value
    with connect(config.db_path) as conn:
        rule = fetch_recurrence_rule(conn, args.item_id)
    if rule:
        if args.scope is None:
            print_json(requires_scope_payload("update"))
            return
        if args.scope == "occurrence":
            if not args.occurrence_date:
                raise AppError("--occurrence-date is required when --scope occurrence.")
            occurrence_date = parse_iso_date(args.occurrence_date, "--occurrence-date")
            if not recurrence_date_matches_pattern(rule, occurrence_date):
                raise AppError("The requested occurrence date does not match the recurrence rule.")
            override_updates = {field: value for field, value in updates.items() if field in RECURRENCE_OVERRIDE_FIELDS}
            unsupported = sorted(set(updates) - RECURRENCE_OVERRIDE_FIELDS)
            if unsupported:
                raise AppError(f"Cannot update occurrence field(s): {', '.join(unsupported)}")
            if not override_updates:
                raise AppError("No occurrence update fields provided.")
            ts = now_iso()
            with connect(config.db_path, writable=True) as conn, transaction(conn):
                status_row = upsert_recurrence_status(
                    conn,
                    rule,
                    args.item_id,
                    occurrence_date,
                    None,
                    ts,
                    override_json=override_updates,
                )
            print_json(
                {
                    "status": "updated",
                    "recurrence": {"rule_id": rule["id"], "occurrence_date": occurrence_date.isoformat()},
                    "recurrence_status": status_row,
                }
            )
            return
        if args.scope != "series":
            raise AppError("--scope must be occurrence or series.")
    updated = update_item_fields(config, args.item_id, updates, note=args.note)
    print_json({"status": "updated", "item": updated})


def backup_checksum(data: dict[str, Any]) -> str:
    body = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def fetch_items_backup_data(db_path: Path) -> dict[str, Any]:
    ensure_initialized(db_path)
    with connect(db_path) as conn:
        tables: dict[str, list[dict[str, Any]]] = {}
        for table, columns in ITEMS_BACKUP_TABLE_COLUMNS.items():
            column_sql = ", ".join(columns)
            rows = conn.execute(
                f"SELECT {column_sql} FROM {table} ORDER BY {ITEMS_BACKUP_TABLE_ORDER[table]}"
            ).fetchall()
            tables[table] = [row_to_dict(row) for row in rows]

    return {
        "format": ITEMS_BACKUP_FORMAT,
        "version": ITEMS_BACKUP_VERSION,
        "tables": tables,
    }


def build_items_backup_payload(db_path: Path) -> dict[str, Any]:
    data = fetch_items_backup_data(db_path)
    return {
        "metadata": {
            "format": ITEMS_BACKUP_FORMAT,
            "version": ITEMS_BACKUP_VERSION,
            "created_at": now_iso(),
            "timezone": "Asia/Shanghai",
        },
        "data": data,
        "checksum": backup_checksum(data),
    }


def summarize_backup_payload(payload: dict[str, Any]) -> dict[str, Any]:
    tables = payload["data"]["tables"]
    item_counts: dict[str, int] = {}
    status_counts: dict[str, int] = {}
    for item in tables["items"]:
        item_counts[item["type"]] = item_counts.get(item["type"], 0) + 1
        status_counts[item["status"]] = status_counts.get(item["status"], 0) + 1
    review_counts: dict[str, int] = {}
    for review in tables["review_queue"]:
        review_counts[review["status"]] = review_counts.get(review["status"], 0) + 1
    recurrence_status_counts: dict[str, int] = {}
    for occurrence in tables.get("recurrence_status", []):
        occurrence_status = occurrence.get("status") or "override"
        recurrence_status_counts[occurrence_status] = recurrence_status_counts.get(occurrence_status, 0) + 1
    return {
        "records": len(tables["records"]),
        "items": len(tables["items"]),
        "tasks": item_counts.get("task", 0),
        "events": item_counts.get("event", 0),
        "relations": len(tables["item_relations"]),
        "recurrence_rules": len(tables.get("recurrence_rules", [])),
        "recurrence_status": len(tables.get("recurrence_status", [])),
        "item_events": len(tables["item_events"]),
        "reviews": len(tables["review_queue"]),
        "item_status_counts": status_counts,
        "recurrence_status_counts": recurrence_status_counts,
        "review_status_counts": review_counts,
    }


def item_time_label(item: dict[str, Any]) -> str:
    if item["type"] == "task":
        return item.get("due_at") or "无明确截止日期"
    if item.get("all_day"):
        return item.get("start_at") or "全天"
    return item.get("start_at") or "无开始时间"


def format_items_backup_text(payload: dict[str, Any]) -> str:
    tables = payload["data"]["tables"]
    summary = summarize_backup_payload(payload)
    lines = [
        "# DailyAssistant items-backup.txt",
        "",
        "本文件是事项备份文本副本，供备份校验和数据库恢复失败时重建使用。",
        "请不要手工修改结构化 JSON 区块。",
        "",
        "## 概览",
        f"- 生成时间：{payload['metadata']['created_at']}",
        f"- 记录数：{summary['records']}",
        f"- 事项数：{summary['items']}（任务 {summary['tasks']}，日程 {summary['events']}）",
        f"- 关系数：{summary['relations']}",
        f"- 事项事件数：{summary['item_events']}",
        f"- 待确认数：{summary['reviews']}",
        f"- 校验和：{payload['checksum']}",
        "",
        "## 事项",
    ]

    for item in tables["items"]:
        lines.append(
            f"- [{item['type']}/{item['status']}] {item['title']} | 时间：{item_time_label(item)} | ID：{item['id']}"
        )
    if not tables["items"]:
        lines.append("- 无")

    lines.extend(["", "## 待确认"])
    for review in tables["review_queue"]:
        question = review.get("question") or "(无问题文本)"
        lines.append(f"- [{review['status']}] {question} | ID：{review['id']}")
    if not tables["review_queue"]:
        lines.append("- 无")

    encoded_payload = base64.b64encode(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).decode("ascii")
    lines.extend(
        [
            "",
            ITEMS_BACKUP_BEGIN,
            encoded_payload,
            ITEMS_BACKUP_END,
            "",
        ]
    )
    return "\n".join(lines)


def export_items_backup(config: AppConfig, output_path: str) -> None:
    out_path = Path(output_path).resolve()
    if not path_is_under_app(out_path):
        raise AppError(f"Output path must stay under this project: {APP_DIR}")
    payload = build_items_backup_payload(config.db_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(format_items_backup_text(payload), encoding="utf-8", newline="\n")
    print_json(
        {
            "status": "ok",
            "path": str(out_path),
            "checksum": payload["checksum"],
            "summary": summarize_backup_payload(payload),
        }
    )


def read_items_backup_payload(path_text: str) -> dict[str, Any]:
    path = Path(path_text).resolve()
    if not path_is_under_app(path):
        raise AppError(f"Items backup file must stay under this project: {APP_DIR}")
    if not path.exists():
        raise AppError(f"Items backup file not found: {path}")
    text = path.read_text(encoding="utf-8")
    begin = text.find(ITEMS_BACKUP_BEGIN)
    end = text.find(ITEMS_BACKUP_END)
    if begin == -1 or end == -1 or end <= begin:
        raise AppError("Items backup file is missing the structured JSON block.")
    encoded = text[begin + len(ITEMS_BACKUP_BEGIN) : end].strip()
    try:
        payload = json.loads(base64.b64decode(encoded, validate=True).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AppError(f"Invalid items backup JSON block: {exc}") from exc
    validate_items_backup_payload(payload)
    return payload


def validate_items_backup_payload(payload: dict[str, Any]) -> None:
    if not isinstance(payload, dict):
        raise AppError("Items backup payload must be an object.")
    metadata = payload.get("metadata")
    data = payload.get("data")
    checksum = payload.get("checksum")
    if not isinstance(metadata, dict) or not isinstance(data, dict) or not isinstance(checksum, str):
        raise AppError("Items backup payload must contain metadata, data, and checksum.")
    if metadata.get("format") != ITEMS_BACKUP_FORMAT and data.get("format") != ITEMS_BACKUP_FORMAT:
        raise AppError("Items backup format is not supported.")
    if data.get("version") != ITEMS_BACKUP_VERSION:
        raise AppError(f"Items backup version is not supported: {data.get('version')}")
    tables = data.get("tables")
    if not isinstance(tables, dict):
        raise AppError("Items backup data.tables must be an object.")
    for table, columns in ITEMS_BACKUP_TABLE_COLUMNS.items():
        rows = tables.get(table)
        if not isinstance(rows, list):
            raise AppError(f"Items backup table is missing or invalid: {table}")
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                raise AppError(f"Items backup row must be an object: {table}[{index}]")
            missing = [column for column in columns if column not in row]
            if missing:
                raise AppError(f"Items backup row {table}[{index}] is missing columns: {', '.join(missing)}")
    actual_checksum = backup_checksum(data)
    if actual_checksum != checksum:
        raise AppError(f"Items backup checksum mismatch: expected {checksum}, got {actual_checksum}")


def compare_backup_data(expected: dict[str, Any], actual: dict[str, Any]) -> dict[str, Any]:
    differences: list[dict[str, Any]] = []
    expected_tables = expected["tables"]
    actual_tables = actual["tables"]
    for table in ITEMS_BACKUP_TABLE_COLUMNS:
        expected_rows = expected_tables[table]
        actual_rows = actual_tables[table]
        if expected_rows != actual_rows:
            differences.append(
                {
                    "table": table,
                    "expected_count": len(expected_rows),
                    "actual_count": len(actual_rows),
                }
            )
    return {
        "ok": not differences,
        "expected_checksum": backup_checksum(expected),
        "actual_checksum": backup_checksum(actual),
        "differences": differences,
    }


def verify_items_backup(config: AppConfig, input_path: str) -> None:
    payload = read_items_backup_payload(input_path)
    actual = fetch_items_backup_data(config.db_path)
    comparison = compare_backup_data(payload["data"], actual)
    print_json(
        {
            "status": "ok" if comparison["ok"] else "mismatch",
            "summary": summarize_backup_payload(payload),
            "comparison": comparison,
        }
    )


def write_items_backup_data_to_db(db_path: Path, data: dict[str, Any]) -> None:
    tables = data["tables"]
    initialize_database(db_path)
    with connect(db_path, writable=True) as conn, transaction(conn):
        for table in ITEMS_BACKUP_DELETE_ORDER:
            conn.execute(f"DELETE FROM {table}")
        for table in ITEMS_BACKUP_IMPORT_ORDER:
            columns = ITEMS_BACKUP_TABLE_COLUMNS[table]
            placeholders = ", ".join("?" for _ in columns)
            column_sql = ", ".join(columns)
            sql = f"INSERT INTO {table} ({column_sql}) VALUES ({placeholders})"
            for row in tables[table]:
                conn.execute(sql, [row[column] for column in columns])


def restore_items_from_backup(config: AppConfig, input_path: str) -> None:
    payload = read_items_backup_payload(input_path)
    data = payload["data"]
    config.db_path.parent.mkdir(parents=True, exist_ok=True)
    temp_db = config.db_path.parent / f".restore-items-{datetime.now(LOCAL_TZ):%Y%m%d-%H%M%S}-{uuid4().hex[:8]}.sqlite"
    try:
        write_items_backup_data_to_db(temp_db, data)
        temp_actual = fetch_items_backup_data(temp_db)
        temp_comparison = compare_backup_data(data, temp_actual)
        if not temp_comparison["ok"]:
            raise AppError(f"Restore staging verification failed: {temp_comparison['differences']}")
        ensure_database_writable(config.db_path)
        os.replace(temp_db, config.db_path)
        repair_workspace_database_permissions(config.db_path)
    finally:
        try:
            if temp_db.exists():
                temp_db.unlink()
        except OSError:
            pass

    actual = fetch_items_backup_data(config.db_path)
    comparison = compare_backup_data(data, actual)
    if not comparison["ok"]:
        raise AppError(f"Restore finished but verification failed: {comparison['differences']}")
    print_json(
        {
            "status": "restored",
            "source": str(Path(input_path).resolve()),
            "summary": summarize_backup_payload(payload),
            "comparison": comparison,
        }
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="DailyAssistant local SQLite assistant")
    parser.add_argument("--version", action="version", version=f"DailyAssistant {APP_VERSION}")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="Path to SQLite database.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("doctor", help="Check local runtime environment without requiring a database.")
    subparsers.add_parser("init", help="Create or update the local SQLite database.")

    apply = subparsers.add_parser("apply-json", help="Apply a Codex-produced JSON parse result.")
    apply.add_argument("--json", help="JSON string. If omitted, stdin is used.")
    apply.add_argument("--file", help="Path to a UTF-8 JSON file.")
    apply.add_argument("--base64", help="UTF-8 JSON encoded as base64. Useful for Chinese text on Windows.")

    query = subparsers.add_parser("query", help="Query tasks, events, or reviews by date, period, or date range.")
    query.add_argument("--date", help="Single date in YYYY-MM-DD.")
    query.add_argument("--period", choices=["today", "week", "month"], help="Date period. Defaults to today.")
    query.add_argument("--from", dest="from_date", help="Range start date in YYYY-MM-DD.")
    query.add_argument("--to", dest="to_date", help="Range end date in YYYY-MM-DD, inclusive.")
    query.add_argument("--type", choices=["task", "event", "reviews"], help="Optional result filter.")
    query.add_argument("--status", choices=["active", "completed", "cancelled", "all"], help="Status filter. Defaults to active.")

    review = subparsers.add_parser("review", help="Update a review queue entry by id.")
    review.add_argument("--review-id", required=True)
    review.add_argument("--status", required=True, choices=sorted(VALID_REVIEW_STATUS))
    review.add_argument("--item-id", help="Optional item to associate with the review.")

    update = subparsers.add_parser("update", help="Update item fields by id.")
    update.add_argument("--item-id", required=True)
    update.add_argument("--type", choices=sorted(VALID_ITEM_TYPES))
    update.add_argument("--title")
    update.add_argument("--content")
    update.add_argument("--status", choices=sorted(VALID_ITEM_STATUS))
    update.add_argument("--confidence", type=float)
    update.add_argument("--due-at", dest="due_at")
    update.add_argument("--start-at", dest="start_at")
    update.add_argument("--end-at", dest="end_at")
    update.add_argument("--all-day", dest="all_day", type=int, choices=[0, 1])
    update.add_argument("--project")
    update.add_argument("--people", help="String or JSON array/object.")
    update.add_argument("--location")
    update.add_argument("--clear", action="append", choices=sorted(CLEARABLE_UPDATE_FIELDS), help="Clear a nullable field. Repeatable.")
    update.add_argument("--note")
    update.add_argument("--scope", choices=["occurrence", "series"], help="For recurring items: update one occurrence or the whole series.")
    update.add_argument("--occurrence-date", help="Recurring occurrence date in YYYY-MM-DD.")

    complete = subparsers.add_parser("complete", help="Mark a task or event item completed by id.")
    complete.add_argument("--item-id", required=True)
    complete.add_argument("--note")
    complete.add_argument("--occurrence-date", help="Recurring occurrence date in YYYY-MM-DD. Defaults to the nearest open occurrence.")

    cancel = subparsers.add_parser("cancel", help="Soft-delete an item by marking it cancelled.")
    cancel.add_argument("--item-id", required=True)
    cancel.add_argument("--note")
    cancel.add_argument("--scope", choices=["occurrence", "series"], help="For recurring items: cancel one occurrence or the whole series.")
    cancel.add_argument("--occurrence-date", help="Recurring occurrence date in YYYY-MM-DD.")

    export_backup = subparsers.add_parser("export-items-backup", help="Export all items to items-backup.txt.")
    export_backup.add_argument("--output", default=str(APP_DIR / "backup" / "items-backup.txt"))

    verify_backup = subparsers.add_parser("verify-items-backup", help="Compare the database with an items-backup.txt file.")
    verify_backup.add_argument("--file", required=True)

    restore_backup = subparsers.add_parser("restore-items-backup", help="Rebuild database contents from an items-backup.txt file.")
    restore_backup.add_argument("--file", required=True)

    return parser


def main(argv: list[str] | None = None) -> int:
    configure_text_io()
    parser = build_parser()
    args = parser.parse_args(argv)
    config = AppConfig(db_path=Path(args.db).resolve())

    try:
        if args.command == "doctor":
            doctor(config)
        elif args.command == "init":
            init_db(config)
        elif args.command == "apply-json":
            apply_json(config, load_json_arg(args.json, args.file, args.base64))
        elif args.command == "query":
            query_range(config, args.date, args.period, args.from_date, args.to_date, args.type, args.status)
        elif args.command == "review":
            update_review(config, args.review_id, args.status, args.item_id)
        elif args.command == "update":
            update_item(config, args)
        elif args.command == "complete":
            complete_item(config, args.item_id, args.note, args.occurrence_date)
        elif args.command == "cancel":
            cancel_item(config, args.item_id, args.note, args.scope, args.occurrence_date)
        elif args.command == "export-items-backup":
            export_items_backup(config, args.output)
        elif args.command == "verify-items-backup":
            verify_items_backup(config, args.file)
        elif args.command == "restore-items-backup":
            restore_items_from_backup(config, args.file)
        else:
            parser.error(f"Unknown command: {args.command}")
    except NeedsInitError:
        print_json(needs_init_payload(config.db_path))
        return 2
    except AppError as exc:
        print_json({"status": "error", "message": str(exc)})
        return 2
    except sqlite3.Error as exc:
        message = str(exc)
        if "readonly" in message.lower() or "read-only" in message.lower():
            message = (
                f"SQLite write failed because the database is read-only: {config.db_path}. "
                "Do not rerun outside the sandbox. Fix this workspace-local database path or file permissions, "
                "then retry the same command."
            )
        else:
            message = f"SQLite error: {message}"
        print_json({"status": "error", "message": message})
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
