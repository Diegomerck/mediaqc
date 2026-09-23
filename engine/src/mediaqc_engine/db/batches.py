"""Persistent queue and bounded read models. Runs remain the QC authority."""

import json
import os
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from mediaqc_engine.app.errors import AppError
from mediaqc_engine.db.project import now

QUIESCENT = {"READY", "PAUSED", "COMPLETED", "STOPPED", "FAILED", "INTERRUPTED"}
REPORTABLE = QUIESCENT - {"READY"}
TERMINAL_ITEMS = {"COMPLETED", "ERROR", "CANCELLED", "EXCLUDED"}


def fetch(db: sqlite3.Connection, identifier: object) -> sqlite3.Row:
    if not isinstance(identifier, str):
        raise AppError("INVALID_REQUEST", "Specify batch_id")
    row = db.execute("SELECT * FROM batches WHERE id=?", (identifier,)).fetchone()
    if row is None:
        raise AppError("BATCH_NOT_FOUND", "Batch not found in this project")
    assert isinstance(row, sqlite3.Row)
    return row


def page(params: dict[str, object]) -> tuple[int, int]:
    limit, offset = params.get("limit", 50), params.get("offset", 0)
    if (
        type(limit) is not int
        or type(offset) is not int
        or not 1 <= limit <= 50
        or offset < 0
    ):
        raise AppError("INVALID_REQUEST", "Page limit must be 1-50; offset nonnegative")
    return limit, offset


def touch(db: sqlite3.Connection, identifier: str) -> None:
    db.execute(
        "UPDATE batches SET revision=revision+1,updated_at=? WHERE id=?",
        (now(), identifier),
    )


def state(
    db: sqlite3.Connection,
    identifier: str,
    status: str,
    code: str | None = None,
    message: str | None = None,
) -> None:
    with db:
        db.execute(
            "UPDATE batches SET "
            "status=?,error_code=?,error_message=?,completed_at=? WHERE "
            "id=?",
            (
                status,
                code,
                message,
                now() if status in {"COMPLETED", "STOPPED", "FAILED"} else None,
                identifier,
            ),
        )
        touch(db, identifier)


def create(
    db: sqlite3.Connection,
    project_id: str,
    name: str,
    kind: str,
    source: str | None,
    recursive: bool = False,
    original: sqlite3.Row | None = None,
) -> str:
    identifier, stamp = str(uuid4()), now()
    with db:
        db.execute(
            "INSERT INTO batches (id,project_id,name,source_kind,source_path,recursive,"
            "status,created_at,updated_at,original_batch_id,profile_key,profile_version,"
            "qc_profile_snapshot_json,ai_mode) VALUES "
            "(?,?,?,?,?,?,'IMPORTING',?,?,?,?,?,?,?)",
            (
                identifier,
                project_id,
                name,
                kind,
                source,
                int(recursive),
                stamp,
                stamp,
                original["id"] if original else None,
                original["profile_key"] if original else None,
                original["profile_version"] if original else None,
                original["qc_profile_snapshot_json"] if original else None,
                original["ai_mode"] if original else "OFF",
            ),
        )
    return identifier


def add_item(
    db: sqlite3.Connection,
    batch_id: str,
    path: Path,
    relative: str,
    reason: str | None = None,
    code: str | None = None,
    message: str | None = None,
    original_item: str | None = None,
) -> None:
    # normpath/normcase do not dereference links or fingerprint content.
    key = os.path.normcase(os.path.abspath(path))
    size, modified = None, None
    if reason is None:
        try:
            info = path.stat()
            size = info.st_size
            modified = datetime.fromtimestamp(info.st_mtime, UTC).isoformat()
        except OSError:
            pass  # Retain unreadable candidates for an actionable processing ERROR.
    stamp = now()
    with db:
        db.execute(
            "INSERT INTO batch_items (id,batch_id,absolute_path,normalized_path_key,"
            "relative_path,status,import_size_bytes,import_modified_at,exclusion_reason,"
            "error_code,error_message,created_at,updated_at,original_item_id) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON "
            "CONFLICT(batch_id,normalized_path_key) "
            "DO UPDATE SET "
            "duplicate_count=duplicate_count+1,updated_at=excluded.updated_at",
            (
                str(uuid4()),
                batch_id,
                str(path),
                key,
                relative,
                "EXCLUDED" if reason else "PENDING",
                size,
                modified,
                reason,
                code,
                message,
                stamp,
                stamp,
                original_item,
            ),
        )
        touch(db, batch_id)


def finish_import(db: sqlite3.Connection, identifier: str) -> None:
    with db:
        # SQLite sorts on disk as necessary; no Python list of the folder contents.
        db.execute(
            "WITH ordered AS (SELECT id,ROW_NUMBER() OVER (ORDER BY "
            "normalized_path_key,id) AS n "
            "FROM batch_items WHERE batch_id=? AND status!='EXCLUDED') "
            "UPDATE batch_items SET queue_position=(SELECT n FROM ordered "
            "WHERE ordered.id=batch_items.id) "
            "WHERE batch_id=? AND status!='EXCLUDED'",
            (identifier, identifier),
        )
        db.execute(
            "UPDATE batches SET status='READY',discovery_completed_at=? WHERE id=?",
            (now(), identifier),
        )
        touch(db, identifier)


def update_item(
    db: sqlite3.Connection,
    item_id: str,
    status: str,
    code: str | None = None,
    message: str | None = None,
) -> None:
    with db:
        item = db.execute(
            "SELECT batch_id FROM batch_items WHERE id=?", (item_id,)
        ).fetchone()
        db.execute(
            "UPDATE batch_items SET status=?,error_code=?,error_message=?,updated_at=?,"
            "started_at=COALESCE(started_at,?),completed_at=? WHERE id=?",
            (
                status,
                code,
                message,
                now(),
                now(),
                now() if status in TERMINAL_ITEMS else None,
                item_id,
            ),
        )
        touch(db, item[0])


def cancel_pending(db: sqlite3.Connection, identifier: str) -> None:
    with db:
        db.execute(
            "UPDATE batch_items SET status='CANCELLED',completed_at=?,updated_at=? "
            "WHERE batch_id=? AND status='PENDING'",
            (now(), now(), identifier),
        )
        touch(db, identifier)


def reconcile(
    db: sqlite3.Connection, interrupted: Callable[[str], None] | None = None
) -> None:
    """Run recovery has already completed. Never automatically start a worker."""
    identifiers = db.execute(
        "SELECT id,status,discovery_completed_at FROM batches "
        "WHERE status IN ('IMPORTING','RUNNING','PAUSING','STOPPING')"
    )
    for batch in identifiers:
        with db:
            for item in db.execute(
                "SELECT i.id,r.status,r.error_code,r.error_message FROM batch_items i "
                "LEFT JOIN analysis_runs r ON r.id=i.analysis_run_id "
                "WHERE i.batch_id=? AND i.status IN ('INSPECTING','RUNNING')",
                (batch["id"],),
            ):
                status = {"COMPLETED": "COMPLETED", "CANCELLED": "CANCELLED"}.get(
                    item["status"], "ERROR"
                )
                db.execute(
                    "UPDATE batch_items SET "
                    "status=?,completed_at=?,updated_at=?,error_code=?,"
                    "error_message=? WHERE id=?",
                    (
                        status,
                        now(),
                        now(),
                        (item["error_code"] or "ENGINE_INTERRUPTED")
                        if status == "ERROR"
                        else None,
                        (
                            item["error_message"]
                            or "Inspection interrupted; retry in a new batch"
                        )
                        if status == "ERROR"
                        else None,
                        item["id"],
                    ),
                )
            pending = db.execute(
                "SELECT 1 FROM batch_items WHERE batch_id=? AND "
                "status='PENDING' LIMIT 1",
                (batch["id"],),
            ).fetchone()
            if batch["status"] == "STOPPING":
                db.execute(
                    "UPDATE batch_items SET status='CANCELLED',completed_at=?,"
                    "updated_at=? WHERE batch_id=? AND status='PENDING'",
                    (now(), now(), batch["id"]),
                )
                target = "STOPPED"
            elif not batch["discovery_completed_at"] or pending:
                target = "INTERRUPTED"
            else:
                target = "COMPLETED"
            db.execute(
                "UPDATE batches SET status=?,error_code=?,error_message=?,"
                "completed_at=? WHERE id=?",
                (
                    target,
                    "ENGINE_INTERRUPTED" if target == "INTERRUPTED" else None,
                    "Processing stopped unexpectedly"
                    if target == "INTERRUPTED"
                    else None,
                    None if target == "INTERRUPTED" else now(),
                    batch["id"],
                ),
            )
            touch(db, batch["id"])
        if target == "INTERRUPTED" and interrupted:
            interrupted(batch["id"])


def counts(db: sqlite3.Connection, identifier: str) -> dict[str, int]:
    result = dict.fromkeys(
        (
            "total",
            "processed",
            "pass",
            "warn",
            "fail",
            "error",
            "cancelled",
            "processing",
            "pending",
        ),
        0,
    )
    for row in db.execute(
        "SELECT i.status,r.overall_result,COUNT(*) AS n FROM batch_items i "
        "LEFT JOIN analysis_runs r ON r.id=i.analysis_run_id WHERE i.batch_id=? "
        "AND i.status!='EXCLUDED' GROUP BY i.status,r.overall_result",
        (identifier,),
    ):
        status, verdict, n = row
        key = (
            verdict.lower()
            if status == "COMPLETED" and verdict
            else {
                "INSPECTING": "processing",
                "RUNNING": "processing",
                "ERROR": "error",
                "CANCELLED": "cancelled",
                "PENDING": "pending",
            }.get(status)
        )
        if key is None:
            raise AppError("PROJECT_INVALID", "Completed batch item has no QC verdict")
        result[key] += n
        result["total"] += n
        if status in {"COMPLETED", "ERROR"}:
            result["processed"] += n
    return result


def summary(db: sqlite3.Connection, identifier: str) -> dict[str, object]:
    row = dict(fetch(db, identifier))
    profile = json.loads(row.pop("qc_profile_snapshot_json") or "null")
    result_counts = counts(db, identifier)
    imported = db.execute(
        "SELECT "
        "SUM(status='EXCLUDED'),SUM(duplicate_count),SUM(exclusion_reason='DIRECTORY_ERROR')"
        " "
        "FROM batch_items WHERE batch_id=?",
        (identifier,),
    ).fetchone()
    current = db.execute(
        "SELECT id AS "
        "item_id,analysis_run_id,relative_path,absolute_path,status AS "
        "stage "
        "FROM batch_items WHERE batch_id=? AND status IN "
        "('INSPECTING','RUNNING') LIMIT 1",
        (identifier,),
    ).fetchone()
    active = dict(current) if current else None
    if active:
        active.update(
            file_name=Path(active.pop("absolute_path")).name,
            file_progress=None,
            media_time_seconds=None,
            media_duration_seconds=None,
        )
    return {
        **row,
        "batch_id": identifier,
        "profile": {key: profile[key] for key in ("profile_key", "name", "version")}
        if profile
        else None,
        "counts": result_counts,
        "import_summary": {
            "excluded": imported[0] or 0,
            "duplicate_encounters": imported[1] or 0,
            "directory_errors": imported[2] or 0,
            "complete": bool(row["discovery_completed_at"]),
            "partial": bool(imported[2]),
        },
        "current": active,
        "overall_progress": result_counts["processed"] / max(1, result_counts["total"]),
        "progress_estimated": True,
        "can_continue_pending": row["status"] == "INTERRUPTED"
        and bool(row["discovery_completed_at"])
        and bool(profile)
        and result_counts["pending"] > 0,
    }


def items(db: sqlite3.Connection, params: dict[str, object]) -> dict[str, object]:
    batch = fetch(db, params.get("batch_id"))
    limit, offset = page(params)
    choice = params.get("filter", "ALL")
    filters = {
        "ALL": "i.status!='EXCLUDED'",
        "NEEDS_ATTENTION": (
            "(i.status='ERROR' OR (i.status='COMPLETED' "
            "AND r.overall_result IN ('WARN','FAIL')))"
        ),
        "PROCESSING": "i.status IN ('INSPECTING','RUNNING')",
        "IMPORT_RESULTS": "(i.status='EXCLUDED' OR i.duplicate_count>0)",
        **{key: f"i.status='{key}'" for key in ("ERROR", "CANCELLED", "PENDING")},
        **{
            key: f"i.status='COMPLETED' AND r.overall_result='{key}'"
            for key in ("PASS", "WARN", "FAIL")
        },
    }
    if not isinstance(choice, str) or choice not in filters:
        raise AppError("INVALID_REQUEST", "Unknown batch filter")
    query = (
        " FROM batch_items i LEFT JOIN analysis_runs r ON "
        "r.id=i.analysis_run_id WHERE i.batch_id=? AND " + filters[choice]
    )
    total = db.execute("SELECT COUNT(*)" + query, (batch["id"],)).fetchone()[0]
    order = (
        "i.normalized_path_key,i.id"
        if choice == "IMPORT_RESULTS" or not batch["discovery_completed_at"]
        else "i.queue_position,i.id"
    )
    rows = db.execute(
        "SELECT i.id AS "
        "item_id,i.queue_position,i.relative_path,i.absolute_path,i.status,"
        "i.analysis_run_id,r.overall_result,i.error_code,i.error_message,i.exclusion_reason,i.duplicate_count"
        + query
        + f" ORDER BY {order} LIMIT ? OFFSET ?",
        (batch["id"], limit, offset),
    )
    values = []
    for row in rows:
        value = dict(row)
        value["file_name"] = Path(value["absolute_path"]).name
        value["issue_counts"] = None
        if value["status"] == "COMPLETED":
            from mediaqc_engine.db.findings import counts as issue_counts

            value["issue_counts"] = issue_counts(db, value["analysis_run_id"])
        values.append(value)
    return {
        "batch_id": batch["id"],
        "revision": batch["revision"],
        "items": values,
        "total": total,
        "limit": limit,
        "offset": offset,
    }
