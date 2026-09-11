"""Canonical run/execution persistence and guarded transitions."""

import json
import sqlite3
from uuid import uuid4

from mediaqc_engine import __version__
from mediaqc_engine.app.errors import AppError
from mediaqc_engine.db.project import now

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
    "ANALYZING": {"COMPLETED", "CANCELLED", "FAILED"},
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
                "OFF",
                now(),
            ),
        )
    return identifier


def transition(
    db: sqlite3.Connection,
    identifier: str,
    status: str,
    code: str | None = None,
    message: str | None = None,
) -> None:
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
                "PASS" if status == "COMPLETED" else None,
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
    run = fetch(db, identifier)
    executions = [
        dict(row)
        for row in db.execute(
            "SELECT * FROM detector_executions WHERE analysis_run_id=? ORDER BY rowid",
            (identifier,),
        )
    ]
    return {
        **run,
        "analysis_run_id": identifier,
        "detector_states": executions,
        "summary": {"counts": {"INFO": 0, "WARN": 0, "FAIL": 0}, "qc_available": False},
    }
