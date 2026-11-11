"""Canonical findings/evidence persistence; no schema changes or media writes."""

import json
import sqlite3
from pathlib import Path
from typing import cast
from uuid import uuid4

from mediaqc_engine.app.errors import AppError
from mediaqc_engine.db.project import now
from mediaqc_engine.db.runs import encode


def save(
    db: sqlite3.Connection,
    project_directory: Path,
    run_id: str,
    execution_id: str,
    draft: dict[str, object],
) -> dict[str, object]:
    if (
        draft["severity"] not in {"INFO", "WARN", "FAIL"}
        or draft["disposition"] != "OPEN"
    ):
        raise AppError("ENGINE_INTERNAL_ERROR", "Invalid detector finding")
    encode(draft)
    start, end = draft["start_time_seconds"], draft["end_time_seconds"]
    if start is not None and (
        float(str(start)) < 0 or end is None or float(str(end)) < float(str(start))
    ):
        raise AppError("ENGINE_INTERNAL_ERROR", "Invalid finding interval")
    metadata = cast(dict[str, object], draft["metadata"])
    evidence: dict[str, object] | None = None
    relative = (
        Path("evidence")
        / str(draft["detector_id"]).split(".")[0]
        / run_id
        / f"{draft['id']}.json"
    )
    try:
        output = project_directory / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            encode(
                {
                    key: draft[key]
                    for key in (
                        "detector_id",
                        "detector_version",
                        "measurements",
                        "threshold",
                        "metadata",
                        "start_time_seconds",
                        "end_time_seconds",
                    )
                }
            ),
            encoding="utf-8",
        )
        evidence = {
            "id": str(uuid4()),
            "evidence_type": "METRICS_JSON",
            "relative_path": relative.as_posix(),
            "mime_type": "application/json",
        }
    except OSError:
        metadata["evidence_error"] = {
            "code": "EVIDENCE_WRITE_FAILED",
            "message": "Cannot write evidence; check permissions and free space",
        }
    fields = (
        "id",
        "detector_id",
        "detector_version",
        "stream_id",
        "severity",
        "confidence",
        "start_time_seconds",
        "end_time_seconds",
        "duration_seconds",
        "title",
        "description",
        "disposition",
    )
    db.execute(
        f"INSERT INTO findings ({','.join(fields)},analysis_run_id,"
        "detector_execution_id,measurements_json,threshold_json,metadata_json,"
        "created_at,updated_at) VALUES ("
        f"{','.join('?' for _ in range(len(fields) + 7))})",
        (
            *[draft[key] for key in fields],
            run_id,
            execution_id,
            encode(draft["measurements"]),
            encode(draft["threshold"]),
            encode(metadata),
            now(),
            now(),
        ),
    )
    if evidence is not None:
        db.execute(
            "INSERT INTO evidence (id,finding_id,evidence_type,relative_path,"
            "mime_type,start_time_seconds,end_time_seconds,metadata_json,"
            "created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (
                evidence["id"],
                draft["id"],
                evidence["evidence_type"],
                evidence["relative_path"],
                evidence["mime_type"],
                start,
                end,
                "{}",
                now(),
            ),
        )
    draft["evidence"] = [evidence] if evidence else []
    return draft


def counts(db: sqlite3.Connection, run_id: str) -> dict[str, int]:
    result = {"INFO": 0, "WARN": 0, "FAIL": 0}
    for row in db.execute(
        "SELECT severity,COUNT(*) AS count FROM findings WHERE analysis_run_id=? "
        "AND disposition NOT IN ('IGNORED','FALSE_POSITIVE','WAIVED') "
        "GROUP BY severity",
        (run_id,),
    ):
        result[row["severity"]] = row["count"]
    return result


def overall(db: sqlite3.Connection, run_id: str) -> str:
    values = counts(db, run_id)
    return "FAIL" if values["FAIL"] else "WARN" if values["WARN"] else "PASS"


def public(db: sqlite3.Connection, row: sqlite3.Row) -> dict[str, object]:
    from mediaqc_engine.explanations import explain

    value = dict(row)
    for key in ("measurements", "threshold", "metadata"):
        value[key] = json.loads(value.pop(key + "_json") or "{}")
    value["explanation"] = explain(value)
    value["evidence"] = [
        dict(item)
        for item in db.execute(
            "SELECT * FROM evidence WHERE finding_id=?", (value["id"],)
        )
    ]
    value["feedback"] = [
        dict(item)
        for item in db.execute(
            "SELECT previous_disposition,new_disposition,note,created_at "
            "FROM operator_feedback WHERE finding_id=? ORDER BY rowid",
            (value["id"],),
        )
    ]
    review = db.execute(
        "SELECT * FROM ai_reviews WHERE finding_id=?", (value["id"],)
    ).fetchone()
    if review is not None:
        saved = dict(review)
        saved["output"] = json.loads(saved.pop("output_json") or "null")
        value["ai_review"] = saved
    return value


def list_findings(
    db: sqlite3.Connection, params: dict[str, object]
) -> dict[str, object]:
    allowed = {
        "analysis_run_id",
        "severity",
        "detector_id",
        "disposition",
        "start_time_seconds",
        "end_time_seconds",
        "limit",
        "offset",
    }
    if "analysis_run_id" not in params or not params.keys() <= allowed:
        raise AppError("INVALID_REQUEST", "Specify run and supported finding filters")
    clauses, values = [], []
    for key in ("analysis_run_id", "severity", "detector_id", "disposition"):
        if key in params:
            if not isinstance(params[key], str):
                raise AppError("INVALID_REQUEST", "Finding filter must be text")
            clauses.append(key + "=?")
            values.append(params[key])
    for key, column, operator in (
        ("start_time_seconds", "end_time_seconds", ">="),
        ("end_time_seconds", "start_time_seconds", "<="),
    ):
        if key in params:
            if type(params[key]) not in (int, float):
                raise AppError("INVALID_REQUEST", "Finding time filter must be numeric")
            clauses.append(f"{column}{operator}?")
            values.append(params[key])
    limit, offset = params.get("limit", 100), params.get("offset", 0)
    if (
        type(limit) is not int
        or type(offset) is not int
        or not 1 <= limit <= 100
        or offset < 0
    ):
        raise AppError(
            "INVALID_REQUEST",
            "Finding page limit must be 1-100 and offset non-negative",
        )
    where = " AND ".join(clauses)
    total = db.execute(
        f"SELECT COUNT(*) FROM findings WHERE {where}", values
    ).fetchone()[0]
    rows = db.execute(
        f"SELECT * FROM findings WHERE {where} "
        "ORDER BY start_time_seconds,id LIMIT ? OFFSET ?",
        (*values, limit, offset),
    )
    return {"findings": [public(db, row) for row in rows], "total": total}


def get(db: sqlite3.Connection, identifier: object) -> dict[str, object]:
    if not isinstance(identifier, str):
        raise AppError("INVALID_REQUEST", "Finding ID must be text")
    row = db.execute("SELECT * FROM findings WHERE id=?", (identifier,)).fetchone()
    if row is None:
        raise AppError("INVALID_REQUEST", "Finding does not exist in this project")
    return public(db, row)


def set_disposition(
    db: sqlite3.Connection, params: dict[str, object]
) -> dict[str, object]:
    if not {"finding_id", "disposition"} <= params.keys() or not params.keys() <= {
        "finding_id",
        "disposition",
        "note",
    }:
        raise AppError(
            "INVALID_REQUEST", "Specify finding_id, disposition and optional note"
        )
    disposition, note = params["disposition"], params.get("note")
    if (
        not isinstance(disposition, str)
        or disposition
        not in {"OPEN", "CONFIRMED", "FALSE_POSITIVE", "IGNORED", "WAIVED"}
        or (note is not None and (not isinstance(note, str) or len(note) > 4000))
    ):
        raise AppError(
            "INVALID_REQUEST", "Invalid disposition or note (maximum 4000 characters)"
        )
    with db:
        db.execute("BEGIN IMMEDIATE")
        finding = get(db, params["finding_id"])
        db.execute(
            "INSERT INTO operator_feedback VALUES (?,?,?,?,?,?)",
            (
                str(uuid4()),
                finding["id"],
                finding["disposition"],
                disposition,
                note,
                now(),
            ),
        )
        db.execute(
            "UPDATE findings SET disposition=?,updated_at=? WHERE id=?",
            (disposition, now(), finding["id"]),
        )
        run_id = str(finding["analysis_run_id"])
        db.execute(
            "UPDATE analysis_runs SET overall_result=? "
            "WHERE id=? AND status='COMPLETED'",
            (overall(db, run_id), run_id),
        )
        db.execute(
            "UPDATE batches SET revision=revision+1,updated_at=? WHERE id IN "
            "(SELECT batch_id FROM batch_items WHERE analysis_run_id=?)",
            (now(), run_id),
        )
    return get(db, finding["id"])
