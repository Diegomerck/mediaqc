"""Bounded project-local visual evidence using the run's owned media processes."""

import base64
import hashlib
import json
import logging
import sqlite3
from pathlib import Path
from typing import cast
from uuid import uuid4

from mediaqc_engine.app.errors import AppError
from mediaqc_engine.db import findings
from mediaqc_engine.db.project import now
from mediaqc_engine.db.runs import encode
from mediaqc_engine.jobs.cancellation import CancellationToken
from mediaqc_engine.media.inspection import fingerprint
from mediaqc_engine.media.tools import MediaTools

MAX_IMAGE_BYTES = 256 * 1024
LOG = logging.getLogger(__name__)


def local_path(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if (
        not path.is_relative_to(root.resolve() / "evidence")
        or Path(relative).is_absolute()
    ):
        raise AppError(
            "EVIDENCE_UNAVAILABLE",
            "Evidence path is outside the project evidence directory",
        )
    return path


def generate(
    db: sqlite3.Connection,
    root: Path,
    run_id: str,
    tools: MediaTools,
    token: CancellationToken,
) -> None:
    asset = db.execute(
        "SELECT m.* FROM media_assets m JOIN analysis_runs r "
        "ON r.media_asset_id=m.id WHERE r.id=?",
        (run_id,),
    ).fetchone()
    source = Path(asset["absolute_path"])
    for row in db.execute("SELECT * FROM findings WHERE analysis_run_id=?", (run_id,)):
        token.check()
        finding = findings.public(db, row)
        metadata = dict(cast(dict[str, object], finding["metadata"]))
        errors: list[dict[str, object]] = []
        video = str(finding["detector_id"]).startswith("video.")
        kinds = (
            ("VIDEO_FRAME_BEFORE", "VIDEO_FRAME", "VIDEO_FRAME_AFTER")
            if video
            else ("AUDIO_WAVEFORM", "AUDIO_SPECTROGRAM")
        )
        start = float(str(finding["start_time_seconds"] or 0))
        end = float(str(finding["end_time_seconds"] or start))
        stream = db.execute(
            "SELECT stream_index FROM media_streams WHERE id=?", (finding["stream_id"],)
        ).fetchone()
        for kind in kinds:
            token.check()
            try:
                if (
                    fingerprint(source)["fast_fingerprint_sha256"]
                    != asset["fast_fingerprint_sha256"]
                ):
                    raise AppError(
                        "MEDIA_CHANGED", "Source changed; inspect and analyze again"
                    )
                if stream is None:
                    raise AppError(
                        "EVIDENCE_UNAVAILABLE",
                        "No single-stream preview is available; "
                        "retained metrics identify the measurement scope",
                    )
                if kind == "VIDEO_FRAME_BEFORE" and start == 0:
                    raise AppError(
                        "EVIDENCE_UNAVAILABLE", "No frame precedes media start"
                    )
                position = max(0, start - (0.25 if video else 1))
                if kind == "VIDEO_FRAME":
                    position = start
                elif kind == "VIDEO_FRAME_AFTER":
                    position = end + 0.25
                duration = float(asset["duration_seconds"] or 0)
                if duration and position >= duration:
                    raise AppError(
                        "EVIDENCE_UNAVAILABLE", "No frame exists after this finding"
                    )
                relative = (
                    f"evidence/{'video' if video else 'audio'}/{run_id}/"
                    f"{finding['id']}-{kind}.png"
                )
                output = local_path(root, relative)
                output.parent.mkdir(parents=True, exist_ok=True)
                args = [
                    "-nostdin",
                    "-v",
                    "error",
                    "-protocol_whitelist",
                    "file",
                    "-ss",
                    str(position),
                    "-i",
                    str(source),
                ]
                window = min(8.0, max(0.01, duration - position)) if duration else 8.0
                if video:
                    args += [
                        "-map",
                        f"0:{stream[0]}",
                        "-vf",
                        "scale=480:270:force_original_aspect_ratio=decrease",
                        "-frames:v",
                        "1",
                    ]
                else:
                    # Input duration stops decoding, not just filtering, after 8 s.
                    args[args.index("-i") : args.index("-i")] = ["-t", str(window)]
                    visual = (
                        "showwavespic=s=640x180:split_channels=0"
                        if kind == "AUDIO_WAVEFORM"
                        else "showspectrumpic=s=640x180:legend=0"
                    )
                    selection = "aformat=channel_layouts=mono"
                    measured = cast(dict[str, object], finding["measurements"])
                    scope = measured.get("measurement_scope")
                    if isinstance(scope, dict) and scope.get("kind") == "channel":
                        members = scope.get("members")
                        if isinstance(members, list) and len(members) == 1:
                            channel = members[0][1]
                            if type(channel) is int and channel >= 0:
                                selection = f"pan=mono|c0=c{channel}"
                    args += [
                        "-filter_complex",
                        f"[0:{stream[0]}]atrim=duration={window},asetpts=PTS-STARTPTS,{selection},aresample=16000,{visual}[out]",
                        "-map",
                        "[out]",
                        "-frames:v",
                        "1",
                    ]
                tools.run("ffmpeg", [*args, "-threads", "1", "-n", str(output)])
                token.check()
                if (
                    fingerprint(source)["fast_fingerprint_sha256"]
                    != asset["fast_fingerprint_sha256"]
                ):
                    raise AppError(
                        "MEDIA_CHANGED", "Source changed during evidence generation"
                    )
                with output.open("rb") as handle:
                    image = handle.read(MAX_IMAGE_BYTES + 1)
                if (
                    not image.startswith(b"\x89PNG\r\n\x1a\n")
                    or len(image) > MAX_IMAGE_BYTES
                ):
                    raise AppError(
                        "EVIDENCE_UNAVAILABLE",
                        "Evidence image is missing or exceeds the size limit",
                    )
                details = {
                    "sha256": hashlib.sha256(image).hexdigest(),
                    "finding_start_seconds": finding["start_time_seconds"],
                    "finding_end_seconds": finding["end_time_seconds"],
                    "window_seconds": None if video else window,
                }
                with db:
                    db.execute(
                        "INSERT INTO evidence VALUES (?,?,?,?,?,?,?,?,?)",
                        (
                            str(uuid4()),
                            finding["id"],
                            kind,
                            relative,
                            "image/png",
                            position,
                            position if video else position + window,
                            encode(details),
                            now(),
                        ),
                    )
            except (AppError, OSError) as exc:
                token.check()
                error: dict[str, object] = {
                    "evidence_type": kind,
                    "code": exc.code
                    if isinstance(exc, AppError)
                    else "EVIDENCE_WRITE_FAILED",
                    "message": exc.message
                    if isinstance(exc, AppError)
                    else "Cannot create evidence; check permissions and free space",
                    "details": exc.details if isinstance(exc, AppError) else {},
                }
                errors.append(error)
                LOG.warning(
                    "run=%s detector=%s evidence=%s code=%s",
                    run_id,
                    finding["detector_id"],
                    kind,
                    error["code"],
                )
        metadata["visual_evidence_errors"] = errors
        with db:
            db.execute(
                "UPDATE findings SET metadata_json=? WHERE id=?",
                (encode(metadata), finding["id"]),
            )


def read(db: sqlite3.Connection, root: Path, identifier: object) -> dict[str, object]:
    if not isinstance(identifier, str):
        raise AppError("INVALID_REQUEST", "Specify evidence_id")
    row = db.execute(
        "SELECT e.*,r.media_fingerprint_sha256,m.absolute_path,"
        "f.measurements_json,f.threshold_json FROM evidence e "
        "JOIN findings f ON f.id=e.finding_id "
        "JOIN analysis_runs r ON r.id=f.analysis_run_id "
        "JOIN media_assets m ON m.id=r.media_asset_id WHERE e.id=?",
        (identifier,),
    ).fetchone()
    if row is None:
        raise AppError(
            "EVIDENCE_UNAVAILABLE", "Evidence reference is missing; rerun analysis"
        )
    try:
        if (
            fingerprint(Path(row["absolute_path"]))["fast_fingerprint_sha256"]
            != row["media_fingerprint_sha256"]
        ):
            raise AppError(
                "EVIDENCE_STALE",
                "Source changed; saved evidence belongs to the previous source",
            )
        path = local_path(root, row["relative_path"])
        with path.open("rb") as handle:
            content = handle.read(MAX_IMAGE_BYTES + 1)
        if len(content) > MAX_IMAGE_BYTES:
            raise AppError("EVIDENCE_UNAVAILABLE", "Evidence exceeds the loading limit")
        metadata: dict[str, object] = json.loads(row["metadata_json"] or "{}")
        if (
            metadata.get("sha256")
            and metadata["sha256"] != hashlib.sha256(content).hexdigest()
        ):
            raise AppError(
                "EVIDENCE_STALE", "Evidence artifact changed; rerun analysis"
            )
        if row["mime_type"] == "image/png" and content.startswith(b"\x89PNG\r\n\x1a\n"):
            return {
                "data_url": "data:image/png;base64,"
                + base64.b64encode(content).decode("ascii"),
                "start_time_seconds": row["start_time_seconds"],
                "end_time_seconds": row["end_time_seconds"],
                "metadata": metadata,
            }
        if row["mime_type"] == "application/json":
            metrics = json.loads(content)
            if not isinstance(metrics, dict) or any(
                metrics.get(key) != json.loads(row[key + "_json"] or "{}")
                for key in ("measurements", "threshold")
            ):
                raise AppError(
                    "EVIDENCE_STALE", "Metrics artifact differs from saved finding"
                )
            return {"text": content.decode("utf-8")}
        raise AppError("EVIDENCE_UNAVAILABLE", "Unsupported or invalid evidence format")
    except (OSError, UnicodeError, ValueError) as exc:
        raise AppError(
            "EVIDENCE_UNAVAILABLE",
            "Evidence cannot be read; restore the artifact or rerun analysis",
        ) from exc
