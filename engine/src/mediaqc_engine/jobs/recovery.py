"""Small recovery journal of DB paths; the project DB remains authoritative."""

import json
import logging
import msvcrt
from pathlib import Path
from typing import BinaryIO

from mediaqc_engine.app.errors import AppError
from mediaqc_engine.db.batches import reconcile
from mediaqc_engine.db.project import Project
from mediaqc_engine.db.runs import recover


class Lease:
    """Prevent recovery or concurrent ownership of a live project by another engine."""

    def __init__(self, project: Path):
        path = project.parent / "cache/engine.lock"
        path.parent.mkdir(parents=True, exist_ok=True)
        self.file: BinaryIO = path.open("a+b")
        self.file.seek(0)
        try:
            msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            self.file.close()
            raise AppError(
                "PROJECT_INVALID", "Project is open in another engine"
            ) from exc

    def close(self) -> None:
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
