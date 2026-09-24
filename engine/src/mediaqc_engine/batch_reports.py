"""Compact offline batch exports from a consistent saved SQLite snapshot."""

import html
import json
import logging
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

from mediaqc_engine import reports
from mediaqc_engine.app.errors import AppError
from mediaqc_engine.db import batches
from mediaqc_engine.db.project import Project, now

LOG = logging.getLogger(__name__)


def write_html(path: Path, content: Iterator[tuple[str, str]]) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as output:
        output.write(
            '<!doctype html><html lang="en"><meta charset="utf-8">'
            '<meta http-equiv="Content-Security-Policy" '
            "content=\"default-src 'none'; style-src 'unsafe-inline'\">"
            "<title>MediaQC batch summary</title><style>"
            "body{font:14px system-ui;margin:2em;color:#172536}"
            "table{border-collapse:collapse;width:100%;table-layout:fixed}"
            "td,th{padding:.5em;border:1px solid #ccc;text-align:left;"
            "overflow-wrap:anywhere}pre{white-space:pre-wrap}"
            "</style><body><h1>MediaQC batch summary</h1>"
        )
        for _ in range(2):
            heading, value = next(content)
            output.write(
                f"<h2>{html.escape(heading)}</h2><pre>{html.escape(value)}</pre>"
            )
        output.write(
            "<table><thead><tr><th>File</th><th>Result / issues</th>"
            "</tr></thead><tbody>"
        )
        imports = False
        for heading, value in content:
            if heading.startswith("Import: ") and not imports:
                output.write("</tbody></table><h2>Import results</h2><table><tbody>")
                imports = True
            output.write(
                f"<tr><td>{html.escape(heading)}</td><td>{html.escape(value)}</td></tr>"
            )
        output.write("</tbody></table></body></html>\n")


def sections(
    project: Project, identifier: str, stamp: str
) -> Iterator[tuple[str, str]]:
    db = project.connection
    batch = batches.fetch(db, identifier)
    profile = json.loads(batch["qc_profile_snapshot_json"] or "null")
    label = profile["name"] + " " + profile["version"] if profile else "Not selected"
    yield (
        "Batch summary",
        (
            f"{batch['name']} | {batch['status']}\n"
            f"Revision: {batch['revision']} | Created: {batch['created_at']}\n"
            f"Generated: {stamp}\n"
            f"Profile: {label}\n"
            f"AI: {batch['ai_mode']}\n"
            + (
                "Queue finished; per-file verdicts follow."
                if batch["status"] == "COMPLETED"
                else "INCOMPLETE BATCH: not all files were analyzed."
            )
        ),
    )
    counts = batches.counts(db, identifier)
    yield "Counts", " | ".join(f"{key}: {value}" for key, value in counts.items())
    for row in db.execute(
        "SELECT "
        "i.relative_path,i.status,i.error_message,r.overall_result,i.analysis_run_id"
        " "
        "FROM batch_items i LEFT JOIN analysis_runs r ON r.id=i.analysis_run_id "
        "WHERE i.batch_id=? AND i.status!='EXCLUDED' ORDER BY i.queue_position,i.id",
        (identifier,),
    ):
        from mediaqc_engine.db.findings import counts as issue_counts
        from mediaqc_engine.media.loudness_scope import notes

        scope_notes = (
            notes(db, row["analysis_run_id"]) if row["analysis_run_id"] else []
        )

        issues = (
            issue_counts(db, row["analysis_run_id"])
            if row["status"] == "COMPLETED"
            else None
        )
        yield (
            row["relative_path"],
            (
                f"{row['status']} | {row['overall_result'] or 'No QC verdict'}"
                + (
                    " | "
                    + ", ".join(f"{key}: {value}" for key, value in issues.items())
                    if issues
                    else ""
                )
                + (f" | {row['error_message']}" if row["error_message"] else "")
                + (" | " + " ".join(scope_notes) if scope_notes else "")
            ),
        )
    for row in db.execute(
        "SELECT "
        "relative_path,exclusion_reason,duplicate_count,error_message FROM "
        "batch_items "
        "WHERE batch_id=? AND (status='EXCLUDED' OR duplicate_count>0) "
        "ORDER BY normalized_path_key,id",
        (identifier,),
    ):
        yield (
            "Import: " + row["relative_path"],
            (
                f"{row['exclusion_reason'] or 'Duplicate path'} | "
                f"Duplicate encounters: {row['duplicate_count']}"
                + (f" | {row['error_message']}" if row["error_message"] else "")
            ),
        )


def generate(project: Project, params: dict[str, object]) -> dict[str, object]:
    batch = batches.fetch(project.connection, params.get("batch_id"))
    if batch["status"] not in batches.REPORTABLE:
        raise AppError("BATCH_INVALID_STATE", "Pause or finish the batch before export")
    if params.get("format") not in ("HTML", "PDF"):
        raise AppError("INVALID_REQUEST", "Choose HTML or PDF")
    kind = str(params["format"])
    root = project.path.parent.resolve()
    directory = root / "reports"
    if directory.resolve() != directory or directory.is_symlink():
        raise AppError("REPORT_FAILED", "Reports directory must be project-local")
    report_id, stamp = str(uuid4()), now()
    output = directory / f"batch-{report_id}.{kind.lower()}"
    temporary = directory / f"batch-{report_id}.tmp"
    try:
        with project.connection:
            project.connection.execute("BEGIN")
            revision = batches.fetch(project.connection, batch["id"])["revision"]
            content = sections(project, batch["id"], stamp)
            if kind == "HTML":
                write_html(temporary, content)
            else:
                temporary.touch(exist_ok=False)
                reports.write_pdf(temporary, content, compact=True)
        temporary.rename(output)
        relative = output.relative_to(root).as_posix()
        with project.connection:
            project.connection.execute(
                "INSERT INTO batch_reports VALUES (?,?,?,?,?,?,?)",
                (
                    report_id,
                    batch["id"],
                    kind,
                    relative,
                    stamp,
                    reports.VERSION,
                    revision,
                ),
            )
        return {
            "batch_report_id": report_id,
            "batch_id": batch["id"],
            "batch_revision": revision,
            "format": kind,
            "relative_path": relative,
            "absolute_path": str(output),
            "generated_at": stamp,
        }
    except Exception as exc:
        for path in (temporary, output):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                LOG.warning(
                    "Cannot remove incomplete batch report: batch=%s", batch["id"]
                )
        raise AppError(
            "REPORT_FAILED", "Cannot export batch report; check saved data and storage"
        ) from exc
