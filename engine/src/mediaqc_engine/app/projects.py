"""Phase 2 application services, with one open project per engine instance."""

import logging
import sqlite3

from mediaqc_engine.app.errors import AppError
from mediaqc_engine.db.project import Project, absolute
from mediaqc_engine.media.inspection import fingerprint, map_probe
from mediaqc_engine.media.tools import MediaTools

LOG = logging.getLogger(__name__)
METHODS = {"project.create", "project.open", "project.get", "media.inspect"}


class Projects:
    def __init__(self, tools: MediaTools | None = None):
        self.tools = tools if tools is not None else MediaTools()
        self.project: Project | None = None

    def close(self) -> None:
        if self.project is not None:
            self.project.close()
            self.project = None

    def dispatch(self, method: str, params: dict[str, object]) -> dict[str, object]:
        expected = {
            "project.create": {"directory", "name"},
            "project.open": {"project_file"},
            "project.get": set(),
            "media.inspect": {"project_id", "absolute_path"},
        }[method]
        if set(params) != expected:
            raise AppError(
                "INVALID_REQUEST", "Parameters do not match the documented method"
            )
        try:
            if method in {"project.create", "project.open"}:
                if method == "project.create":
                    name = params["name"]
                    if not isinstance(name, str) or not name.strip() or len(name) > 200:
                        raise AppError(
                            "INVALID_REQUEST",
                            "Project name must contain 1-200 characters",
                        )
                    candidate = Project.create(
                        absolute(params["directory"]), name.strip()
                    )
                else:
                    candidate = Project.open(absolute(params["project_file"]))
                # A failed open/create never discards the current project.
                self.close()
                self.project = candidate
                return candidate.summary()
            project = self.project
            if project is None or (
                method == "media.inspect" and params["project_id"] != project.id
            ):
                raise AppError("PROJECT_NOT_FOUND", "Open the requested project first")
            if method == "project.get":
                return project.summary()
            path = absolute(params["absolute_path"])
            if (
                path == project.path
                or any(
                    path.is_relative_to(project.path.parent / folder)
                    for folder in ("cache", "logs", "evidence", "reports")
                )
                or str(path).startswith(str(project.path) + "-")
            ):
                raise AppError(
                    "MEDIA_UNSUPPORTED",
                    "Choose source media, not an engine-owned project artifact",
                )
            identity = fingerprint(path)
            metadata = dict(identity)
            self.tools.active.set()
            try:
                probe = self.tools.probe(path)
                fields, streams = map_probe(probe)
                if identity != fingerprint(path):
                    raise AppError(
                        "MEDIA_CHANGED",
                        "Source changed during probing; inspect it again",
                    )
                metadata.update(fields)
                metadata["inspection_status"] = "COMPLETED"
                asset_id = project.save_media(metadata, streams)
                public = {
                    key: value
                    for key, value in metadata.items()
                    if key != "ffprobe_json"
                }
                return {
                    "media_asset_id": asset_id,
                    "inspection_status": "COMPLETED",
                    "metadata": public,
                    "streams": streams,
                }
            except AppError as failure:
                excerpt = failure.details.get("stderr_excerpt")
                diagnostic = failure.message + (
                    "\n" + excerpt if isinstance(excerpt, str) else ""
                )
                metadata.update(
                    {
                        "inspection_status": "FAILED",
                        "inspection_error_code": failure.code,
                        "inspection_error_message": diagnostic,
                    }
                )
                asset_id = project.save_media(metadata, [])
                LOG.warning(
                    "%s: media inspection failed (asset=%s)", failure.code, asset_id
                )
                raise AppError(
                    failure.code,
                    failure.message,
                    {**failure.details, "media_asset_id": asset_id},
                ) from failure
            finally:
                self.tools.active.clear()
        except (OSError, sqlite3.Error, ValueError) as failure:
            LOG.warning("Phase 2 operation failed: %s", type(failure).__name__)
            raise AppError(
                "MEDIA_INSPECTION_FAILED"
                if method == "media.inspect"
                else "PROJECT_INVALID",
                "The local operation failed; verify the file and directory permissions",
            ) from failure
