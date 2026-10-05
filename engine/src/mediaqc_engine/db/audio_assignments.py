"""Immutable relational assignment snapshots, created in the run transaction."""

import json
import sqlite3
from typing import Any

from mediaqc_engine.qc.audio_applicability import Snapshot


def save(
    db: sqlite3.Connection, run_id: str, snapshot: Snapshot, document: dict[str, Any]
) -> None:
    db.execute(
        "INSERT INTO audio_assignments VALUES (?,?,?,?,?,?)",
        (
            run_id,
            snapshot.identity,
            snapshot.source_sha256,
            snapshot.provenance,
            "explicit_audio_v1",
            json.dumps(document, allow_nan=False),
        ),
    )
    db.executemany(
        "INSERT INTO audio_assignment_channels VALUES (?,?,?,?,?)",
        [(run_id, *c.member, c.role, c.expectation) for c in snapshot.channels],
    )
    for program in snapshot.programs:
        db.execute(
            "INSERT INTO audio_assignment_programs VALUES (?,?,?)",
            (run_id, program.program_id, program.layout),
        )
        db.executemany(
            "INSERT INTO audio_assignment_members VALUES (?,?,?,?,?)",
            [
                (run_id, program.program_id, i, *m)
                for i, m in enumerate(program.members)
            ],
        )


def document(db: sqlite3.Connection, run_id: str) -> dict[str, Any] | None:
    row = db.execute(
        "SELECT document_json FROM audio_assignments WHERE analysis_run_id=?", (run_id,)
    ).fetchone()
    if row is None:
        return None
    result: dict[str, Any] = json.loads(row[0])
    return result


def report_snapshot(db: sqlite3.Connection, run_id: str) -> dict[str, Any] | None:
    """Export saved intent, including omitted channels normalized to unknown."""
    row = db.execute(
        "SELECT identity,source_sha256,provenance,policy_version,document_json "
        "FROM audio_assignments WHERE analysis_run_id=?",
        (run_id,),
    ).fetchone()
    if row is None:
        return None
    result = dict(row)
    result["document"] = json.loads(result.pop("document_json"))
    result["channels"] = [
        dict(channel)
        for channel in db.execute(
            "SELECT stream_index,channel_index,role,expectation "
            "FROM audio_assignment_channels WHERE analysis_run_id=? "
            "ORDER BY stream_index,channel_index",
            (run_id,),
        )
    ]
    programs = []
    for program in db.execute(
        "SELECT program_id,layout FROM audio_assignment_programs "
        "WHERE analysis_run_id=? ORDER BY program_id",
        (run_id,),
    ):
        programs.append(
            {
                **dict(program),
                "members": [
                    list(member)
                    for member in db.execute(
                        "SELECT stream_index,channel_index "
                        "FROM audio_assignment_members "
                        "WHERE analysis_run_id=? AND program_id=? ORDER BY ordinal",
                        (run_id, program["program_id"]),
                    )
                ],
            }
        )
    result["programs"] = programs
    return result
