"""Project lifecycle and relational persistence; no analysis services."""

import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from mediaqc_engine import __version__
from mediaqc_engine.app.errors import AppError

SCHEMA = Path(__file__).with_name("migration_001.sql")
FOLDERS = (
    "evidence/audio",
    "evidence/video",
    "evidence/thumbnails",
    "reports",
    "cache",
    "logs",
)


def now() -> str:
    return datetime.now(UTC).isoformat()


def absolute(value: object) -> Path:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise AppError("INVALID_REQUEST", "An absolute local path is required")
    path = Path(value)
    if not path.is_absolute() or value.startswith(("\\\\", "//")):
        raise AppError("INVALID_REQUEST", "Use an absolute path on a local drive")
    return path.resolve()


class Project:
    def __init__(self, path: Path, connection: sqlite3.Connection):
        self.path = path
        self.connection = connection
        self.connection.row_factory = sqlite3.Row
        self.id = str(connection.execute("SELECT id FROM projects").fetchone()[0])

    @classmethod
    def create(cls, directory: Path, name: str) -> "Project":
        if directory.exists() and any(directory.iterdir()):
            raise AppError("PROJECT_INVALID", "Choose a new or empty project directory")
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "project.sqlite"
        path.touch(exist_ok=False)
        connection = sqlite3.connect(path)
        try:
            connection.executescript(
                "BEGIN IMMEDIATE;\n" + SCHEMA.read_text(encoding="utf-8")
            )
            connection.execute("INSERT INTO schema_meta VALUES ('schema_version', '1')")
            stamp = now()
            connection.execute(
                "INSERT INTO projects VALUES (?, ?, ?, ?, ?, NULL)",
                (str(uuid4()), name, stamp, stamp, __version__),
            )
            connection.commit()
            for folder in FOLDERS:
                (directory / folder).mkdir(parents=True, exist_ok=True)
        except BaseException:
            connection.rollback()
            connection.close()
            path.unlink()
            raise
        connection.close()
        return cls.open(path)

    @classmethod
    def open(cls, path: Path) -> "Project":
        if not path.is_file():
            raise AppError("PROJECT_NOT_FOUND", "Project database was not found")
        if path.name != "project.sqlite":
            raise AppError(
                "PROJECT_INVALID", "Select the project's project.sqlite file"
            )
        # Validate without writes before enabling WAL or modifying a user project.
        try:
            with closing(
                sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
            ) as reader:
                version = reader.execute(
                    "SELECT value FROM schema_meta WHERE key='schema_version'"
                ).fetchone()
                if version != ("1",) or reader.execute(
                    "SELECT count(*) FROM projects"
                ).fetchone() != (1,):
                    raise AppError(
                        "PROJECT_INVALID",
                        "Unsupported schema version or invalid project record",
                    )
                with closing(sqlite3.connect(":memory:")) as expected:
                    expected.executescript(SCHEMA.read_text(encoding="utf-8"))
                    tables = expected.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                    for (table,) in tables:
                        # Names come only from the checked-in canonical schema.
                        if (
                            reader.execute(f"PRAGMA table_info({table})").fetchall()
                            != expected.execute(
                                f"PRAGMA table_info({table})"
                            ).fetchall()
                        ):
                            raise AppError(
                                "PROJECT_INVALID",
                                "Project schema does not match version 1",
                            )
                if reader.execute("PRAGMA quick_check").fetchone() != ("ok",):
                    raise AppError("PROJECT_INVALID", "Project database is corrupt")
            connection = sqlite3.connect(path.as_uri() + "?mode=rw", uri=True)
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA synchronous = NORMAL")
            return cls(path, connection)
        except sqlite3.Error as exc:
            raise AppError(
                "PROJECT_INVALID", "Cannot open this project database"
            ) from exc

    def close(self) -> None:
        self.connection.close()

    def summary(self) -> dict[str, object]:
        project = dict(self.connection.execute("SELECT * FROM projects").fetchone())
        assets = []
        for row in self.connection.execute(
            "SELECT * FROM media_assets ORDER BY created_at, id"
        ):
            asset = dict(row)
            asset.pop("ffprobe_json")
            source = Path(asset["absolute_path"])
            try:
                stat = source.stat()
                modified = datetime.fromtimestamp(stat.st_mtime, UTC).isoformat()
                asset["source_status"] = (
                    "UNCHANGED"
                    if stat.st_size == asset["file_size_bytes"]
                    and modified == asset["modified_at"]
                    else "MEDIA_CHANGED"
                )
            except OSError:
                asset["source_status"] = "MEDIA_NOT_FOUND"
            asset["streams"] = [
                dict(stream)
                for stream in self.connection.execute(
                    "SELECT * FROM media_streams WHERE media_asset_id=? "
                    "ORDER BY stream_index",
                    (asset["id"],),
                )
            ]
            assets.append(asset)
        return {
            **project,
            "project_file": str(self.path),
            "media_assets": assets,
            "analysis_runs": [],
        }

    def save_media(
        self, metadata: dict[str, object], streams: list[dict[str, object]]
    ) -> str:
        identifier = str(uuid4())
        stamp = now()
        asset = {
            "id": identifier,
            "project_id": self.id,
            **metadata,
            "created_at": stamp,
            "updated_at": stamp,
        }
        with self.connection:
            columns = ",".join(asset)
            placeholders = ",".join("?" for _ in asset)
            self.connection.execute(
                f"INSERT INTO media_assets ({columns}) VALUES ({placeholders})",
                tuple(asset.values()),
            )
            for stream in streams:
                record = {"id": str(uuid4()), "media_asset_id": identifier, **stream}
                self.connection.execute(
                    f"INSERT INTO media_streams ({','.join(record)}) "
                    f"VALUES ({','.join('?' for _ in record)})",
                    tuple(record.values()),
                )
            self.connection.execute(
                "UPDATE projects SET updated_at=? WHERE id=?", (stamp, self.id)
            )
        return identifier
