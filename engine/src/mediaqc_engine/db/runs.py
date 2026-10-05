"""Canonical run/execution persistence and guarded transitions."""

import json
import sqlite3
from typing import Any
from uuid import uuid4

from mediaqc_engine import __version__
from mediaqc_engine.app.errors import AppError
from mediaqc_engine.db import audio_assignments
from mediaqc_engine.db.project import now
from mediaqc_engine.qc.audio_applicability import Snapshot

TERMINAL = {"COMPLETED", "CANCELLED", "FAILED"}
ACTIVE = {
    "QUEUED",
    "INSPECTING",
    "ANALYZING",
    "GENERATING_EVIDENCE",
    "GENERATING_REPORT",
}
TRANSITIONS = {
    "QUEUED": {"INSPECTING", "CANCELLED", "FAILED"},
    "INSPECTING": {"ANALYZING", "CANCELLED", "FAILED"},
    "ANALYZING": {"GENERATING_EVIDENCE", "COMPLETED", "CANCELLED", "FAILED"},
    "GENERATING_EVIDENCE": {"COMPLETED", "CANCELLED", "FAILED"},
}


def encode(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(",", ":"))


def fetch(db: sqlite3.Connection, identifier: str) -> dict[str, object]:
    row = db.execute("SELECT * FROM analysis_runs WHERE id=?", (identifier,)).fetchone()
    if row is None:
        raise AppError("RUN_NOT_FOUND", "Run does not exist in the open project")
    return dict(row)


def create(
    db: sqlite3.Connection,
    project_id: str,
    asset_id: str,
    profile: dict[str, object],
    fingerprint: object,
    ai_mode: str = "OFF",
    batch_item_id: str | None = None,
    assignment: tuple[Snapshot, dict[str, Any]] | None = None,
) -> str:
    identifier = str(uuid4())
    with db:
        # A transaction also protects against two application instances starting a run.
        db.execute("BEGIN IMMEDIATE")
        if db.execute(
            "SELECT id FROM analysis_runs WHERE status NOT IN "
            "('COMPLETED','CANCELLED','FAILED') LIMIT 1"
        ).fetchone():
            raise AppError(
                "RUN_START_FAILED", "A run is already active in this project"
            )
        db.execute(
            "INSERT INTO analysis_runs (id,project_id,media_asset_id,"
            "qc_profile_snapshot_json,status,engine_version,protocol_version,"
            "media_fingerprint_sha256,ai_mode,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                identifier,
                project_id,
                asset_id,
                encode(profile),
                "QUEUED",
                __version__,
                "1.0",
                fingerprint,
                ai_mode,
                now(),
            ),
        )
        if assignment is not None:
            audio_assignments.save(db, identifier, *assignment)
        if batch_item_id is not None:
            item = db.execute(
                "SELECT i.batch_id FROM batch_items i JOIN batches b ON "
                "b.id=i.batch_id "
                "WHERE i.id=? AND i.status='INSPECTING' AND b.project_id=? "
                "AND b.status IN ('RUNNING','PAUSING') AND "
                "b.qc_profile_snapshot_json=? "
                "AND b.ai_mode=? AND i.analysis_run_id IS NULL",
                (batch_item_id, project_id, encode(profile), ai_mode),
            ).fetchone()
            if item is None:
                raise AppError("BATCH_CONFLICT", "Batch item cannot start this run")
            db.execute(
                "UPDATE batch_items SET "
                "status='RUNNING',analysis_run_id=?,media_asset_id=?,updated_at=?"
                " WHERE id=?",
                (identifier, asset_id, now(), batch_item_id),
            )
            from mediaqc_engine.db.batches import touch

            touch(db, item[0])
    return identifier


def transition(
    db: sqlite3.Connection,
    identifier: str,
    status: str,
    code: str | None = None,
    message: str | None = None,
) -> None:
    from mediaqc_engine.db.findings import overall

    with db:
        db.execute("BEGIN IMMEDIATE")
        previous = str(fetch(db, identifier)["status"])
        if previous in TERMINAL:
            raise AppError("RUN_ALREADY_TERMINAL", "Run has already finished")
        if status not in TRANSITIONS.get(previous, set()):
            raise AppError("INVALID_REQUEST", "Invalid run state transition")
        db.execute(
            "UPDATE analysis_runs SET status=?, error_code=?, error_message=?, "
            "started_at=COALESCE(started_at,?), completed_at=?, "
            "overall_result=? WHERE id=?",
            (
                status,
                code,
                message,
                now(),
                now() if status in TERMINAL else None,
                overall(db, identifier) if status == "COMPLETED" else None,
                identifier,
            ),
        )


def recover(db: sqlite3.Connection) -> None:
    with db:
        stamp = now()
        db.execute(
            "UPDATE detector_executions SET status='FAILED', completed_at=?, "
            "error_code='ENGINE_INTERRUPTED', error_message='Engine stopped "
            "unexpectedly' "
            "WHERE status IN ('PENDING','RUNNING') AND analysis_run_id IN "
            "(SELECT id FROM analysis_runs WHERE status NOT IN "
            "('COMPLETED','CANCELLED','FAILED'))",
            (stamp,),
        )
        db.execute(
            "UPDATE analysis_runs SET status='FAILED', completed_at=?, "
            "error_code='ENGINE_INTERRUPTED', error_message='Engine stopped "
            "unexpectedly; retry the run', "
            "overall_result=NULL WHERE status NOT IN "
            "('COMPLETED','CANCELLED','FAILED')",
            (stamp,),
        )


def summary(db: sqlite3.Connection, identifier: str) -> dict[str, object]:
    from mediaqc_engine.db.findings import counts, list_findings
    from mediaqc_engine.media.loudness_scope import notes

    run = fetch(db, identifier)
    executions = [
        dict(row)
        for row in db.execute(
            "SELECT * FROM detector_executions WHERE analysis_run_id=? ORDER BY rowid",
            (identifier,),
        )
    ]
    for execution in executions:
        rows = db.execute(
            "SELECT severity,COUNT(*) FROM findings WHERE detector_execution_id=? "
            "AND disposition NOT IN ('IGNORED','FALSE_POSITIVE') GROUP BY severity",
            (execution["id"],),
        ).fetchall()
        execution["finding_count"] = sum(row[1] for row in rows)
        severities = {row[0] for row in rows}
        execution["worst_severity"] = next(
            (value for value in ("FAIL", "WARN", "INFO") if value in severities), None
        )
    return {
        **run,
        "audio_assignment": audio_assignments.document(db, identifier),
        "audio_applicability_policy": "explicit_audio_v1"
        if audio_assignments.document(db, identifier)
        else None,
        "media": dict(
            db.execute(
                "SELECT file_name,duration_seconds,absolute_path "
                "FROM media_assets WHERE id=?",
                (run["media_asset_id"],),
            ).fetchone()
        ),
        "analysis_run_id": identifier,
        "interpretation_notes": notes(db, identifier),
        "detector_states": executions,
        "summary": {
            "dispositions": {
                row[0]: row[1]
                for row in db.execute(
                    "SELECT disposition,COUNT(*) FROM findings "
                    "WHERE analysis_run_id=? GROUP BY disposition",
                    (identifier,),
                )
            },
            "counts": counts(db, identifier),
            "qc_available": any(item["status"] == "COMPLETED" for item in executions),
        },
        **list_findings(db, {"analysis_run_id": identifier}),
    }
