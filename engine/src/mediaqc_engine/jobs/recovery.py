"""Small recovery journal of DB paths; the project DB remains authoritative."""

import json
import logging
import sys
from pathlib import Path
from typing import BinaryIO

if sys.platform == "win32":
    import msvcrt
else:
    import fcntl

from mediaqc_engine.app.errors import AppError
from mediaqc_engine.db.batches import reconcile
from mediaqc_engine.db.project import Project
from mediaqc_engine.db.runs import recover


def _lock_file(file: BinaryIO) -> None:
    if sys.platform == "win32":
        msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock_file(file: BinaryIO) -> None:
    try:
        if sys.platform == "win32":
            file.seek(0)
            msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            fcntl.flock(file.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass


class Lease:
    """Prevent recovery or concurrent ownership of a live project by another engine."""

    def __init__(self, project: Path):
        path = project.parent / "cache/engine.lock"
        path.parent.mkdir(parents=True, exist_ok=True)
        self.file: BinaryIO = path.open("a+b")
        self.file.seek(0)
        try:
            _lock_file(self.file)
        except OSError as exc:
            self.file.close()
            raise AppError(
                "PROJECT_INVALID", "Project is open in another engine"
            ) from exc

    def close(self) -> None:
        try:
            _unlock_file(self.file)
        finally:
            self.file.close()


class Journal:
    def __init__(self, directory: Path | None):
        self.directory = directory

    def record(self, identifier: str, project: Path) -> None:
        if self.directory is not None:
            self.directory.mkdir(parents=True, exist_ok=True)
            path = self.directory / f"{identifier}.json"
            temporary = path.with_suffix(".tmp")
            temporary.write_text(json.dumps(str(project)), encoding="utf-8")
            temporary.replace(path)

    def finish(self, identifier: str) -> None:
        if self.directory is not None:
            (self.directory / f"{identifier}.json").unlink(missing_ok=True)

    def recover(self) -> None:
        if self.directory is None or not self.directory.exists():
            return
        for entry in self.directory.glob("*.json"):
            try:
                path = Path(json.loads(entry.read_text(encoding="utf-8")))
                project = Project.open(path)
                try:
                    lease = Lease(path)
                    try:
                        recover(project.connection)
                        from mediaqc_engine.detectors.audio.pcm import (
                            recover as recover_pcm,
                        )

                        recover_pcm(project.path.parent / "cache")
                        reconcile(project.connection)
                    finally:
                        lease.close()
                finally:
                    project.close()
                entry.unlink()
            except (AppError, OSError, ValueError, TypeError):
                logging.getLogger(__name__).warning(
                    "Recovery deferred for an unavailable project"
                )
