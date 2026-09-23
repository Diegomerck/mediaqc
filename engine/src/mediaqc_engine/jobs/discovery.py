"""Streaming, non-following discovery. Extension eligibility is not a QC verdict."""

import os
import sqlite3
import stat
from pathlib import Path

from mediaqc_engine.app.errors import AppError
from mediaqc_engine.db import batches
from mediaqc_engine.jobs.cancellation import CancellationToken

EXTENSIONS = (".wav", ".mp3", ".mp4", ".mxf")


def linked(path: Path) -> bool:
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
    )


def owned(path: Path, project_file: Path) -> bool:
    path = path.resolve()
    return (
        path == project_file
        or str(path).startswith(str(project_file) + "-")
        or any(
            path.is_relative_to(project_file.parent / name)
            for name in ("cache", "logs", "evidence", "reports")
        )
        or (
            path.name.startswith("project.schema-v")
            and path.parent == project_file.parent
        )
    )


def discover(
    db: sqlite3.Connection,
    batch_id: str,
    project_file: Path,
    source: Path,
    recursive: bool,
    folder: bool,
    token: CancellationToken,
) -> None:
    def add(path: Path, reason: str | None = None, code: str | None = None) -> None:
        token.check()
        relative = (
            str(path.relative_to(source)) if folder and path != source else path.name
        )
        batches.add_item(
            db,
            batch_id,
            path,
            relative,
            reason,
            code,
            "Directory could not be read" if code else None,
        )

    def scan(directory: Path, root: bool = False) -> None:
        token.check()
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    token.check()
                    path = Path(entry.path)
                    try:
                        if linked(path):
                            add(path, "LINK_NOT_FOLLOWED")
                        elif owned(path, project_file):
                            add(path, "PROJECT_ARTIFACT")
                        elif entry.is_dir(follow_symlinks=False):
                            if recursive:
                                scan(path)
                        elif path.suffix.lower() in EXTENSIONS:
                            add(path)
                        else:
                            add(path, "UNSUPPORTED_EXTENSION")
                    except OSError:
                        # A supported path stays a candidate even if stat is denied.
                        add(
                            path,
                            None
                            if path.suffix.lower() in EXTENSIONS
                            else "UNREADABLE_ENTRY",
                        )
        except OSError as exc:
            if root:
                raise AppError(
                    "BATCH_IMPORT_FAILED", "Source folder cannot be read"
                ) from exc
            add(directory, "DIRECTORY_ERROR", "MEDIA_INSPECTION_FAILED")

    if folder:
        if linked(source):
            add(source, "LINK_NOT_FOLLOWED")
        else:
            scan(source, True)
    else:
        add(source, "PROJECT_ARTIFACT" if owned(source, project_file) else None)
    token.check()
