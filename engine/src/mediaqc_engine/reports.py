"""Offline exports of one consistent saved run; never open source media."""

import hashlib
import html
import json
import logging
from collections.abc import Iterable
from pathlib import Path
from typing import cast
from uuid import uuid4

from mediaqc_engine import evidence
from mediaqc_engine.app.errors import AppError
from mediaqc_engine.db import audio_assignments, findings, runs
from mediaqc_engine.db.project import Project, now

VERSION = "1.1.0"
# Export resource limits, not QC policy. Exceeding them fails without truncation.
MAX_FINDINGS = 5000
MAX_TEXT_BYTES = 4 * 1024 * 1024
LOG = logging.getLogger(__name__)
Sections = list[tuple[str, str]]


def display(value: object) -> str:
    if value is None:
        return "Unavailable"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)
    return str(value)


def evidence_status(
    root: Path, item: dict[str, object], finding: dict[str, object]
) -> str:
    """Verify saved artifacts against saved results, independent of today's source."""
    try:
        path = evidence.local_path(root, str(item["relative_path"]))
        with path.open("rb") as stream:
            content = stream.read(evidence.MAX_IMAGE_BYTES + 1)
        if len(content) > evidence.MAX_IMAGE_BYTES:
            return "UNAVAILABLE: evidence exceeds loading limit"
        metadata = json.loads(str(item["metadata_json"] or "{}"))
        digest = metadata.get("sha256")
        if digest and digest != hashlib.sha256(content).hexdigest():
            return "STALE: evidence checksum differs from saved artifact"
        if item["mime_type"] == "application/json":
            metrics = json.loads(content)
            if not isinstance(metrics, dict) or any(
                metrics.get(key) != finding[key]
                for key in ("measurements", "threshold")
            ):
                return "STALE: evidence differs from saved measurements"
        elif item["mime_type"] != "image/png" or not content.startswith(
            b"\x89PNG\r\n\x1a\n"
        ):
            return "UNAVAILABLE: unsupported evidence format"
        elif not digest:
            return "UNVERIFIED: no saved evidence checksum"
        return "AVAILABLE: saved artifact verified"
    except (AppError, OSError, ValueError, TypeError):
        return "UNAVAILABLE: evidence missing, unreadable or invalid"


def sections(project: Project, identifier: str) -> Sections:
    db = project.connection
    result: Sections = []
    size = 0

    def add(title: str, value: object) -> None:
        nonlocal size
        text = display(value)
        size += len(text.encode("utf-8")) + len(title.encode("utf-8"))
        if size > MAX_TEXT_BYTES:
            raise AppError("REPORT_FAILED", "Report exceeds the 4 MiB text limit")
        result.append((title, text))

    with db:
        db.execute("BEGIN")
        run = runs.fetch(db, identifier)
        if run["status"] != "COMPLETED":
            raise AppError("REPORT_FAILED", "Only completed runs can be exported")
        total = db.execute(
            "SELECT COUNT(*) FROM findings WHERE analysis_run_id=?", (identifier,)
        ).fetchone()[0]
        if total > MAX_FINDINGS:
            raise AppError("REPORT_FAILED", "Report exceeds the 5000 finding limit")
        profile = json.loads(str(run["qc_profile_snapshot_json"]))
        add("Overall result", findings.overall(db, identifier))
        from mediaqc_engine.media.loudness_scope import notes

        for note in notes(db, identifier):
            add("Loudness interpretation", note)
        assignment = audio_assignments.report_snapshot(db, identifier)
        if assignment is not None:
            add("Saved audio applicability", assignment)
        add("Contributing findings", findings.counts(db, identifier))
        add(
            "Disposition policy",
            "OPEN and CONFIRMED contribute to PASS/WARN/FAIL. "
            "FALSE_POSITIVE and IGNORED do not. All findings remain below.",
        )
        add(
            "Report basis",
            "Saved completed run and current saved dispositions. "
            "Source media was not opened or re-analyzed. Evidence is checked against "
            "saved artifacts, not the current source. "
            "Times are seconds; dates are UTC.",
        )
        add("Generator version", VERSION)
        add(
            "Project",
            dict(
                db.execute(
                    "SELECT id,name,app_version_created FROM projects"
                ).fetchone()
            ),
        )
        add(
            "Run",
            {
                key: value
                for key, value in run.items()
                if key != "qc_profile_snapshot_json"
            },
        )
        add(
            "Saved media",
            dict(
                db.execute(
                    "SELECT id,absolute_path,file_name,file_size_bytes,"
                    "duration_seconds,container_format "
                    "FROM media_assets WHERE id=?",
                    (run["media_asset_id"],),
                ).fetchone()
            ),
        )
        add(
            "QC profile",
            {key: profile[key] for key in ("profile_key", "name", "version")},
        )
        add(
            "Dispositions",
            {
                row[0]: row[1]
                for row in db.execute(
                    "SELECT disposition,COUNT(*) FROM findings WHERE analysis_run_id=? "
                    "GROUP BY disposition ORDER BY disposition",
                    (identifier,),
                )
            },
        )
        add(
            "Detector executions",
            [
                dict(row)
                for row in db.execute(
                    "SELECT * FROM detector_executions WHERE analysis_run_id=? "
                    "ORDER BY detector_id,id",
                    (identifier,),
                )
            ],
        )
        for index, row in enumerate(
            db.execute(
                "SELECT * FROM findings WHERE analysis_run_id=? "
                "ORDER BY start_time_seconds,id",
                (identifier,),
            ),
            1,
        ):
            finding = findings.public(db, row)
            items = cast(list[dict[str, object]], finding.pop("evidence"))
            add(
                f"Finding {index}: {finding['severity']} / {finding['disposition']}",
                finding,
            )
            add(
                f"Evidence for finding {index}",
                [
                    {
                        **item,
                        "availability": evidence_status(
                            project.path.parent, item, finding
                        ),
                    }
                    for item in sorted(items, key=lambda value: str(value["id"]))
                ]
                or "UNAVAILABLE: no saved evidence",
            )
        add("Saved QC profile snapshot", profile)
    return result


def write_html(path: Path, content: Iterable[tuple[str, str]]) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as output:
        output.write(
            '<!doctype html><html lang="en"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width">'
            '<meta http-equiv="Content-Security-Policy" '
            "content=\"default-src 'none'; style-src 'unsafe-inline'\">"
            "<title>MediaQC report</title><style>"
            "body{font:15px system-ui,sans-serif;max-width:960px;"
            "margin:40px auto;padding:20px;color:#172536}"
            "h1,h2{color:#164466}h2{margin-top:28px;font-size:19px}"
            "pre{white-space:pre-wrap;overflow-wrap:anywhere;"
            "font:13px monospace;line-height:1.5}"
            "@media print{body{margin:0}h2{break-after:avoid}}"
            "</style><body><h1>MediaQC report</h1>"
        )
        for heading, text in content:
            output.write(
                f"<section><h2>{html.escape(heading)}</h2><pre>{html.escape(text)}</pre></section>\n"
            )
        output.write("</body></html>\n")


def write_pdf(
    path: Path, content: Iterable[tuple[str, str]], *, compact: bool = False
) -> None:
    # Imports are local so HTML remains usable if the PDF installation is damaged.
    import reportlab  # type: ignore[import-untyped]
    from reportlab.pdfbase import pdfmetrics  # type: ignore[import-untyped]
    from reportlab.pdfbase.ttfonts import TTFont  # type: ignore[import-untyped]
    from reportlab.pdfgen.canvas import Canvas  # type: ignore[import-untyped]

    font = TTFont("ReportVera", str(Path(reportlab.__file__).parent / "fonts/Vera.ttf"))
    pdfmetrics.registerFont(font)
    canvas = Canvas(str(path), pagesize=(595, 842), invariant=1, pageCompression=1)
    canvas.setTitle("MediaQC report")
    canvas.setAuthor("MediaQC")
    y = 790

    def page() -> None:
        canvas.setFont("ReportVera", 9)
        canvas.drawString(
            42, 25, f"MediaQC | Generator {VERSION} | Page {canvas.getPageNumber()}"
        )
        canvas.showPage()

    def line(text: str, size: int = 10) -> None:
        nonlocal y
        if y < 55:
            page()
            y = 790
        canvas.setFont("ReportVera", size)
        canvas.drawString(42, y, text)
        y -= size + 5

    line("MediaQC report", 20)
    line(
        "Unsupported font characters are preserved as \\uXXXX / \\UXXXXXXXX escapes.", 9
    )
    for heading, text in content:
        if y < 100:
            page()
            y = 790
        if compact:
            text = heading + " | " + text
        else:
            y -= 12
            line(heading, 13)
        for original in text.splitlines():
            # Never silently replace characters with missing-glyph squares.
            safe = "".join(
                char
                if ord(char) in font.face.charToGlyph and ord(char) >= 32
                else char.encode("unicode_escape").decode("ascii")
                for char in original
            )
            part = ""
            for char in safe:
                if pdfmetrics.stringWidth(part + char, "ReportVera", 10) > 511:
                    line(part)
                    part = ""
                part += char
            line(part)
    page()
    canvas.save()


def generate(project: Project, params: dict[str, object]) -> dict[str, object]:
    if (
        set(params) != {"analysis_run_id", "format"}
        or not isinstance(params["analysis_run_id"], str)
        or params["format"] not in ("HTML", "PDF")
    ):
        raise AppError(
            "INVALID_REQUEST", "Specify analysis_run_id and HTML or PDF format"
        )
    identifier = str(params["analysis_run_id"])
    kind = str(params["format"])
    output: Path | None = None
    temporary: Path | None = None
    try:
        content = sections(project, identifier)
        root = project.path.parent.resolve()
        directory = root / "reports"
        directory.mkdir(exist_ok=True)
        if directory.resolve() != directory or directory.is_symlink():
            raise AppError("REPORT_FAILED", "Reports directory must be project-local")
        report_id = str(uuid4())
        output = directory / f"{report_id}.{kind.lower()}"
        temporary = directory / f"{report_id}.tmp"
        if kind == "HTML":
            write_html(temporary, content)
        else:
            # Reserve exclusively before giving the filename to ReportLab.
            temporary.touch(exist_ok=False)
            write_pdf(temporary, content)
        temporary.rename(output)
        relative = output.relative_to(root).as_posix()
        stamp = now()
        with project.connection:
            project.connection.execute(
                "INSERT INTO reports VALUES (?,?,?,?,?,?,?)",
                (report_id, identifier, kind, relative, stamp, VERSION, None),
            )
        return {
            "id": report_id,
            "analysis_run_id": identifier,
            "format": kind,
            "relative_path": relative,
            "absolute_path": str(output),
            "generator_version": VERSION,
            "generated_at": stamp,
        }
    except Exception as exc:
        for path in (temporary, output):
            if path is not None:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    LOG.warning("Cannot remove incomplete report: run=%s", identifier)
        LOG.warning(
            "Report failed: run=%s format=%s error=%s",
            identifier,
            kind,
            type(exc).__name__,
        )
        if isinstance(exc, AppError):
            raise
        raise AppError(
            "REPORT_FAILED",
            "Cannot export report; check saved data, free space and permissions",
        ) from exc
