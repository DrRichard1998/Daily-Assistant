#!/usr/bin/env python
"""Local SQLite-backed assistant CLI.

Codex parses natural language into the JSON contract documented in AGENTS.md;
this CLI validates, writes, and reads back the committed rows.
"""

from __future__ import annotations

import argparse
import base64
import csv
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

VALID_ITEM_TYPES = {"task", "event"}
VALID_ITEM_STATUS = {"active", "completed", "cancelled", "needs_review"}
QUERY_ITEM_STATUS = {"active", "completed", "cancelled", "all"}
VALID_PARSE_STATUS = {"parsed", "needs_review", "ignored", "failed"}
VALID_RELATIONS = {"prepares_for", "related_to", "duplicate_of"}
VALID_REVIEW_STATUS = {"open", "resolved", "dismissed"}
QUERY_REVIEW_STATUS = {"active": "open", "completed": "resolved", "cancelled": "dismissed"}


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
        "next_extension": "extensions/init.md",
        "next_action": "Read extensions/init.md and ask the user whether to start using this project.",
    }


def init_db(config: AppConfig) -> None:
    if not SCHEMA_PATH.exists():
        raise AppError(f"Schema not found: {SCHEMA_PATH}")
    repair_workspace_database_permissions(config.db_path)
    with connect(config.db_path, writable=True) as conn:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    permissions_repaired = repair_workspace_database_permissions(config.db_path)
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
            **item,
            "created_from_record_id": record_id,
            "created_at": ts,
            "updated_at": ts,
            "completed_at": ts if item["status"] == "completed" else None,
        },
    )


def insert_item_event(
    conn: sqlite3.Connection,
    item_id: str,
    record_id: str,
    action: str,
    after_json: dict[str, Any] | None,
    confidence: float | None,
    note: str | None,
    ts: str,
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
            None,
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

    return {
        "read_after_write": True,
        "record": row_to_dict(record_row),
        "items": item_rows,
        "relations": relations,
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
            insert_item_event(
                conn,
                item_id=item["id"],
                record_id=record["id"],
                action="create",
                after_json=item,
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
            "review": created_review,
            "verification": verification,
        }
    )


def parse_date_arg(value: str, arg_name: str) -> date:
    try:
        return datetime.fromisoformat(value).date()
    except ValueError as exc:
        raise AppError(f"{arg_name} must be YYYY-MM-DD.") from exc


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
                      AND start_at IS NOT NULL
                      AND start_at >= ?
                    ORDER BY start_at, created_at
                    LIMIT 1
                    """,
                    (end_exclusive,),
                ).fetchone()
            payload["events"] = {
                "in_range": events_in_range,
                "next_upcoming": row_to_dict(next_upcoming_event) if next_upcoming_event else None,
            }

        if include_tasks:
            tasks_due_in_range = [
                row_to_dict(row)
                for row in conn.execute(
                    f"""
                    SELECT * FROM items
                    WHERE type = 'task'
                      {item_status_sql}
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
                      AND due_at IS NULL
                    ORDER BY created_at
                    """,
                    item_status_params,
                )
            ]
            payload["tasks"] = {
                "overdue_before_range": overdue_tasks,
                "due_in_range": tasks_due_in_range,
                "upcoming_after_range": upcoming_tasks,
                "without_due_at": tasks_without_due_at,
            }

        if include_reviews:
            reviews = [
                row_to_dict(row)
                for row in conn.execute(
                    f"""
                    SELECT review_queue.*, records.canonical_text
                    FROM review_queue
                    JOIN records ON records.id = review_queue.record_id
                    WHERE 1 = 1
                      {review_status_sql}
                    ORDER BY review_queue.created_at
                    """,
                    review_status_params,
                )
            ]
            payload["reviews"] = reviews

    print_json(payload)


def complete_item(config: AppConfig, item_id: str, note: str | None) -> None:
    ensure_initialized(config.db_path)
    ts = now_iso()
    with connect(config.db_path, writable=True) as conn, transaction(conn):
        row = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
        if row is None:
            raise AppError(f"Item not found: {item_id}")
        item = row_to_dict(row)
        if item["type"] != "task":
            raise AppError("Only task items can be completed.")
        if item["status"] == "completed":
            print_json({"status": "already_completed", "item": item})
            return
        if item["status"] == "cancelled":
            raise AppError("Cancelled items cannot be completed.")
        before = dict(item)
        conn.execute(
            """
            UPDATE items
            SET status = 'completed', completed_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (ts, ts, item_id),
        )
        updated = row_to_dict(conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone())
        conn.execute(
            """
            INSERT INTO item_events (
              id, item_id, record_id, action, before_json, after_json,
              confidence, note, created_at
            )
            VALUES (?, ?, ?, 'complete', ?, ?, ?, ?, ?)
            """,
            (
                make_id("E"),
                item_id,
                item["created_from_record_id"],
                json.dumps(before, ensure_ascii=False),
                json.dumps(updated, ensure_ascii=False),
                1.0,
                note,
                ts,
            ),
        )
    print_json({"status": "completed", "item": updated})


def cancel_item(config: AppConfig, item_id: str, note: str | None) -> None:
    ensure_initialized(config.db_path)
    ts = now_iso()
    with connect(config.db_path, writable=True) as conn, transaction(conn):
        row = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
        if row is None:
            raise AppError(f"Item not found: {item_id}")
        item = row_to_dict(row)
        if item["status"] == "cancelled":
            print_json({"status": "already_cancelled", "item": item})
            return
        before = dict(item)
        conn.execute(
            """
            UPDATE items
            SET status = 'cancelled', completed_at = NULL, updated_at = ?
            WHERE id = ?
            """,
            (ts, item_id),
        )
        updated = row_to_dict(conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone())
        conn.execute(
            """
            INSERT INTO item_events (
              id, item_id, record_id, action, before_json, after_json,
              confidence, note, created_at
            )
            VALUES (?, ?, ?, 'cancel', ?, ?, ?, ?, ?)
            """,
            (
                make_id("E"),
                item_id,
                item["created_from_record_id"],
                json.dumps(before, ensure_ascii=False),
                json.dumps(updated, ensure_ascii=False),
                1.0,
                note,
                ts,
            ),
        )
    print_json({"status": "cancelled", "item": updated})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="DairyAssistant local SQLite assistant")
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

    complete = subparsers.add_parser("complete", help="Mark a task item completed by id.")
    complete.add_argument("--item-id", required=True)
    complete.add_argument("--note")

    cancel = subparsers.add_parser("cancel", help="Soft-delete an item by marking it cancelled.")
    cancel.add_argument("--item-id", required=True)
    cancel.add_argument("--note")

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
        elif args.command == "complete":
            complete_item(config, args.item_id, args.note)
        elif args.command == "cancel":
            cancel_item(config, args.item_id, args.note)
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
