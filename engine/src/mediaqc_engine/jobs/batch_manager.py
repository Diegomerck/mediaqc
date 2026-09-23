"""Sequential persistent scheduling above the unchanged deterministic run pipeline."""

import json
import logging
import os
import threading
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from mediaqc_engine.app.errors import AppError
from mediaqc_engine.db import batches, runs
from mediaqc_engine.db.project import Project, absolute, now
from mediaqc_engine.jobs.cancellation import CancellationToken, Cancelled
from mediaqc_engine.jobs.discovery import discover
from mediaqc_engine.jobs.manager import EventSink, JobManager
from mediaqc_engine.media.inspection import fingerprint, map_probe
from mediaqc_engine.media.tools import MediaTools
from mediaqc_engine.qc import profiles

LOG = logging.getLogger(__name__)
METHODS = {
    "batch." + name
    for name in (
        "create",
        "list",
        "get",
        "items",
        "start",
        "pause",
        "resume",
        "stop",
        "retry",
        "report.generate",
    )
} | {"analysis.list"}


class BatchManager:
    def __init__(self, jobs: JobManager, emit: EventSink):
        self.jobs, self.emit = jobs, emit
        self.lock = jobs.lock
        self.worker: threading.Thread | None = None
        self.token = CancellationToken()
        self.tools: MediaTools | None = None
        self.identifier: str | None = None
        self.session = str(uuid4())
        self.sequence = 0
        self.last_revision = 0
        self.fraction = 0.0
        self.progress_item: str | None = None
        self.persistence_failure: tuple[str, str] | None = None

    @property
    def active(self) -> bool:
        return self.worker is not None and self.worker.is_alive()

    def available(self) -> None:
        if self.persistence_failure:
            raise AppError(
                "PROJECT_INVALID",
                "Restart and reopen the project after storage recovery",
            )
        if self.active or self.jobs.active or self.jobs.stopping:
            raise AppError("BATCH_BUSY", "Finish, pause, or stop active work first")

    def snapshot(self, project: Project, identifier: str) -> dict[str, object]:
        db = project.connection
        with self.lock, db:
            db.execute("BEGIN")
            value = batches.summary(db, identifier)
            if identifier == self.identifier:
                self.last_revision = int(str(value["revision"]))
            current = value["current"]
            if (
                isinstance(current, dict)
                and current["analysis_run_id"] == self.jobs.identifier
            ):
                if self.progress_item != current["item_id"]:
                    self.progress_item, self.fraction = current["item_id"], 0.0
                self.fraction = max(
                    self.fraction,
                    min(
                        0.99, float(str(self.jobs.progress.get("overall_progress", 0)))
                    ),
                )
                current.update(
                    file_progress=self.fraction,
                    stage=self.jobs.progress.get("stage", "RUNNING"),
                    media_time_seconds=self.jobs.progress.get("media_time_seconds"),
                    media_duration_seconds=self.jobs.progress.get(
                        "media_duration_seconds"
                    ),
                )
                counts = value["counts"]
                assert isinstance(counts, dict)
                value["overall_progress"] = (counts["processed"] + self.fraction) / max(
                    1, counts["total"]
                )
            value.update(
                engine_session_id=self.session, progress_sequence=self.sequence
            )
            if self.persistence_failure and self.persistence_failure[0] == identifier:
                value.update(
                    status="FAILED",
                    error_code="PROJECT_INVALID",
                    error_message=self.persistence_failure[1],
                    can_continue_pending=False,
                )
            return value

    def notify(
        self,
        project: Project,
        identifier: str,
        event: str = "batch.status",
        item: str | None = None,
    ) -> None:
        with self.lock:
            self.sequence += 1
            value = self.snapshot(project, identifier)
            data = {
                key: value[key]
                for key in (
                    "batch_id",
                    "revision",
                    "status",
                    "counts",
                    "current",
                    "overall_progress",
                    "import_summary",
                    "error_code",
                    "error_message",
                )
            }
            data.update(engine_session_id=self.session, sequence=self.sequence)
            if item:
                row = project.connection.execute(
                    "SELECT analysis_run_id FROM batch_items WHERE id=?", (item,)
                ).fetchone()
                data.update(item_id=item, analysis_run_id=row[0] if row else None)
            self.emit(event, data)

    def dispatch(
        self, project: Project, method: str, params: dict[str, object]
    ) -> dict[str, object]:
        with self.lock:
            return self._dispatch(project, method, params)

    def _dispatch(
        self, project: Project, method: str, params: dict[str, object]
    ) -> dict[str, object]:
        db = project.connection
        if method in {"batch.list", "analysis.list"}:
            if not {"project_id"} <= params.keys() or not params.keys() <= {
                "project_id",
                "limit",
                "offset",
            }:
                raise AppError("INVALID_REQUEST", "Specify project and pagination")
            if params["project_id"] != project.id:
                raise AppError("PROJECT_NOT_FOUND", "Open the requested project")
            limit, offset = batches.page(params)
            if method == "analysis.list":
                with db:
                    db.execute("BEGIN")
                    total = db.execute("SELECT COUNT(*) FROM analysis_runs").fetchone()[
                        0
                    ]
                    values = []
                    for row in db.execute(
                        "SELECT "
                        "r.id,r.media_asset_id,m.file_name,r.status,r.overall_result,r.created_at,r.started_at,r.completed_at,r.qc_profile_snapshot_json"
                        " FROM analysis_runs r JOIN media_assets m ON "
                        "m.id=r.media_asset_id ORDER BY r.created_at "
                        "DESC,r.id LIMIT ? OFFSET ?",
                        (limit, offset),
                    ):
                        value = dict(row)
                        profile = json.loads(value.pop("qc_profile_snapshot_json"))
                        value.update(
                            profile_name=profile["name"],
                            profile_version=profile["version"],
                        )
                        values.append(value)
                    return {
                        "runs": values,
                        "total": total,
                        "limit": limit,
                        "offset": offset,
                    }
            with db:
                db.execute("BEGIN")
                total = db.execute("SELECT COUNT(*) FROM batches").fetchone()[0]
                values = [
                    batches.summary(db, row[0])
                    for row in db.execute(
                        "SELECT id FROM batches ORDER BY created_at DESC,id"
                        " LIMIT ? OFFSET ?",
                        (limit, offset),
                    )
                ]
                for value in values:
                    value.pop("current")
                return {
                    "batches": values,
                    "total": total,
                    "limit": limit,
                    "offset": offset,
                }
        if method == "batch.create":
            required = {"project_id", "name", "source_kind", "absolute_path"}
            if not required <= params.keys() or not params.keys() <= required | {
                "recursive"
            }:
                raise AppError(
                    "INVALID_REQUEST", "Specify batch name and source selection"
                )
            if params["project_id"] != project.id:
                raise AppError("PROJECT_NOT_FOUND", "Open the requested project")
            name, kind, recursive = (
                params["name"],
                params["source_kind"],
                params.get("recursive", False),
            )
            if (
                not isinstance(name, str)
                or not name.strip()
                or len(name) > 200
                or kind not in ("FILE", "FOLDER")
                or type(recursive) is not bool
                or (recursive and kind != "FOLDER")
            ):
                raise AppError("INVALID_REQUEST", "Invalid name or source selection")
            absolute(
                params["absolute_path"]
            )  # Validation; do not resolve folder links.
            source = os.path.abspath(str(params["absolute_path"]))
            self.available()
            identifier = batches.create(
                db, project.id, name.strip(), str(kind), source, recursive
            )
            self.launch(project, identifier, True)
            return {"batch_id": identifier, "status": "IMPORTING", "revision": 0}
        allowed = {"batch_id"}
        if method == "batch.items":
            allowed |= {"filter", "limit", "offset"}
        elif method == "batch.start":
            allowed |= {"profile_key", "profile_version", "ai_mode"}
        elif method == "batch.retry":
            allowed |= {"selection"}
        elif method == "batch.report.generate":
            allowed |= {"format"}
        if (
            "batch_id" not in params
            or not params.keys() <= allowed
            or (
                method in {"batch.start", "batch.retry", "batch.report.generate"}
                and set(params) != allowed
            )
        ):
            raise AppError("INVALID_REQUEST", "Invalid batch parameters")
        batch = batches.fetch(db, params["batch_id"])
        identifier, status = batch["id"], batch["status"]
        if method == "batch.get":
            return self.snapshot(project, identifier)
        if method == "batch.items":
            with db:
                db.execute("BEGIN")
                return batches.items(db, params)
        if method == "batch.report.generate":
            self.available()
            from mediaqc_engine.batch_reports import generate

            return generate(project, params)
        if method == "batch.retry":
            self.available()
            selection = params["selection"]
            if selection not in (
                "ERROR",
                "CANCELLED",
                "UNATTEMPTED",
                "ALL_UNSUCCESSFUL",
            ):
                raise AppError("INVALID_REQUEST", "Unknown retry selection")
            if status not in batches.QUIESCENT or not batch["qc_profile_snapshot_json"]:
                raise AppError(
                    "BATCH_INVALID_STATE", "Retry a saved, stopped or completed batch"
                )
            states = (
                [str(selection)]
                if selection in ("ERROR", "CANCELLED")
                else (
                    ["PENDING"]
                    if selection == "UNATTEMPTED"
                    else ["ERROR", "CANCELLED"]
                    + (["PENDING"] if status == "FAILED" else [])
                )
            )
            if selection == "UNATTEMPTED" and status != "FAILED":
                raise AppError(
                    "BATCH_INVALID_STATE",
                    "Only failed batches have retryable unattempted files",
                )
            where = ",".join("?" for _ in states)
            if not db.execute(
                "SELECT 1 FROM batch_items WHERE batch_id=? "
                f"AND status IN ({where}) LIMIT 1",
                (identifier, *states),
            ).fetchone():
                raise AppError("BATCH_EMPTY", "No matching files to retry")
            new = batches.create(
                db,
                project.id,
                (batch["name"][:190] + " retry"),
                "RETRY",
                None,
                original=batch,
            )
            # Record selection without a JSON queue or in-memory path list.
            with db:
                db.execute(
                    "INSERT INTO batch_items (id,batch_id,original_item_id,"
                    "absolute_path,normalized_path_key,relative_path,status,"
                    "created_at,updated_at) SELECT lower(hex(randomblob(16))),?,"
                    "id,absolute_path,normalized_path_key,relative_path,'PENDING',"
                    "?,? FROM batch_items WHERE batch_id=? "
                    f"AND status IN ({where})",
                    (new, now(), now(), identifier, *states),
                )
            self.launch(project, new, True)
            return {"batch_id": new, "status": "IMPORTING", "revision": 0}
        if method == "batch.start":
            if params["ai_mode"] not in ("OFF", "LOCAL"):
                raise AppError("INVALID_REQUEST", "AI mode must be OFF or LOCAL")
            if batch["qc_profile_snapshot_json"]:
                if any(
                    params[key] != batch[key]
                    for key in ("profile_key", "profile_version", "ai_mode")
                ):
                    raise AppError("BATCH_CONFLICT", "Use the saved batch settings")
                profile = json.loads(batch["qc_profile_snapshot_json"])
            else:
                profile = profiles.get(params["profile_key"], params["profile_version"])
            if status == "RUNNING":
                return self.snapshot(project, identifier)
            if status != "READY":
                raise AppError("BATCH_INVALID_STATE", "Start requires a ready batch")
            self.available()
            if not batches.counts(db, identifier)["pending"]:
                raise AppError("BATCH_EMPTY", "No supported media found")
            with db:
                db.execute(
                    "UPDATE batches SET "
                    "profile_key=?,profile_version=?,qc_profile_snapshot_json=?,ai_mode=?,started_at=?"
                    " WHERE id=?",
                    (
                        profile["profile_key"],
                        profile["version"],
                        runs.encode(profile),
                        params["ai_mode"],
                        now(),
                        identifier,
                    ),
                )
            batches.state(db, identifier, "RUNNING")
            self.launch(project, identifier, False)
        elif method == "batch.resume":
            if status == "RUNNING":
                return self.snapshot(project, identifier)
            if (
                status != "PAUSED"
                and not self.snapshot(project, identifier)["can_continue_pending"]
            ):
                raise AppError(
                    "BATCH_INVALID_STATE",
                    "Only paused or interrupted pending work can resume",
                )
            self.available()
            batches.state(db, identifier, "RUNNING")
            self.launch(project, identifier, False)
        elif method == "batch.pause":
            if status not in {"RUNNING", "PAUSING", "PAUSED"}:
                raise AppError("BATCH_INVALID_STATE", "Only running work can pause")
            if status == "RUNNING":
                batches.state(
                    db,
                    identifier,
                    "PAUSING"
                    if batches.counts(db, identifier)["processing"]
                    else "PAUSED",
                )
        elif method == "batch.stop":
            if status in {"COMPLETED", "FAILED"}:
                raise AppError("BATCH_INVALID_STATE", "Batch has already finished")
            if status not in {"STOPPED", "STOPPING"}:
                batches.state(db, identifier, "STOPPING")
                batches.cancel_pending(db, identifier)
                if self.active and identifier == self.identifier:
                    self.token.cancel()
                    if self.tools:
                        self.tools.cancel()
                    if self.jobs.active:
                        run = runs.fetch(db, str(self.jobs.identifier))
                        if run["status"] not in runs.TERMINAL:
                            self.jobs.dispatch(
                                project,
                                "analysis.cancel",
                                {"analysis_run_id": self.jobs.identifier},
                            )
                else:
                    batches.state(db, identifier, "STOPPED")
        self.notify(project, identifier)
        return self.snapshot(project, identifier)

    def launch(self, project: Project, identifier: str, importing: bool) -> None:
        self.identifier, self.token = identifier, CancellationToken()
        self.last_revision = batches.fetch(project.connection, identifier)["revision"]
        self.worker = threading.Thread(
            target=self.execute,
            args=(project.path, identifier, importing),
            name=f"batch-{identifier}",
        )
        try:
            self.worker.start()
        except RuntimeError as exc:
            batches.state(
                project.connection,
                identifier,
                "FAILED",
                "RUN_START_FAILED",
                "Could not start batch worker",
            )
            raise AppError("RUN_START_FAILED", "Could not start batch worker") from exc

    def execute(self, path: Path, identifier: str, importing: bool) -> None:
        project: Project | None = None
        try:
            project = Project.open(path)
            db = project.connection
            batch = batches.fetch(db, identifier)
            if importing:
                if batch["source_kind"] == "RETRY":
                    for row in db.execute(
                        "SELECT id,absolute_path FROM batch_items WHERE batch_id=?",
                        (identifier,),
                    ):
                        self.token.check()
                        try:
                            identity = Path(row["absolute_path"]).stat()
                        except OSError:
                            continue
                        with db:
                            db.execute(
                                "UPDATE batch_items SET "
                                "import_size_bytes=?,import_modified_at=? "
                                "WHERE id=?",
                                (
                                    identity.st_size,
                                    datetime.fromtimestamp(
                                        identity.st_mtime, UTC
                                    ).isoformat(),
                                    row["id"],
                                ),
                            )
                else:
                    discover(
                        db,
                        identifier,
                        path,
                        Path(batch["source_path"]),
                        bool(batch["recursive"]),
                        batch["source_kind"] == "FOLDER",
                        self.token,
                    )
                with self.lock:
                    self.token.check()
                    batches.finish_import(db, identifier)
                self.notify(project, identifier, "batch.discovery")
                return
            self.process(project, identifier)
        except Exception as exc:
            # Also reap a live run if persistence/event delivery fails while waiting.
            with self.lock:
                if self.jobs.active:
                    self.jobs.token.cancel()
                    if self.jobs.tools:
                        self.jobs.tools.cancel()
            if self.jobs.worker and self.jobs.active:
                self.jobs.worker.join()
            try:
                if project is None:
                    raise AppError(
                        "PROJECT_INVALID", "Batch worker could not open the project"
                    )
                # Reconcile any claimed item after reaping, preserving a committed
                # completion even if failure occurred before the item update.
                for item in project.connection.execute(
                    "SELECT i.id,r.status FROM batch_items i LEFT JOIN analysis_runs r "
                    "ON r.id=i.analysis_run_id WHERE i.batch_id=? "
                    "AND i.status IN ('INSPECTING','RUNNING')",
                    (identifier,),
                ):
                    terminal = {"COMPLETED": "COMPLETED", "CANCELLED": "CANCELLED"}.get(
                        item["status"], "ERROR"
                    )
                    batches.update_item(
                        project.connection,
                        item["id"],
                        terminal,
                        "ENGINE_INTERNAL_ERROR" if terminal == "ERROR" else None,
                        "Batch work stopped unexpectedly"
                        if terminal == "ERROR"
                        else None,
                    )
                if self.token.event.is_set() or isinstance(exc, Cancelled):
                    batches.cancel_pending(project.connection, identifier)
                    batches.state(project.connection, identifier, "STOPPED")
                else:
                    LOG.exception("Batch worker failed: batch=%s", identifier)
                    batches.state(
                        project.connection,
                        identifier,
                        "FAILED",
                        exc.code
                        if isinstance(exc, AppError)
                        else "ENGINE_INTERNAL_ERROR",
                        exc.message
                        if isinstance(exc, AppError)
                        else "Batch stopped; check project storage and logs",
                    )
            except Exception:
                self.persistence_failure = (
                    identifier,
                    "Batch persistence failed; restore storage and reopen the project",
                )
                self.sequence += 1
                self.emit(
                    "batch.failed",
                    {
                        "batch_id": identifier,
                        "status": "FAILED",
                        "engine_session_id": self.session,
                        "sequence": self.sequence,
                        "revision": self.last_revision,
                        "error_code": "PROJECT_INVALID",
                        "error_message": self.persistence_failure[1],
                    },
                )
        finally:
            if self.tools:
                self.tools.cancel()
            if project:
                try:
                    status = batches.fetch(project.connection, identifier)["status"]
                    event = {
                        "COMPLETED": "batch.completed",
                        "STOPPED": "batch.stopped",
                        "FAILED": "batch.failed",
                    }.get(status, "batch.status")
                    self.notify(project, identifier, event)
                except Exception:
                    LOG.error(
                        "Batch terminal state could not be read: batch=%s", identifier
                    )
                finally:
                    project.close()

    def process(self, project: Project, identifier: str) -> None:
        db = project.connection
        while True:
            with self.lock:
                self.token.check()
                batch = batches.fetch(db, identifier)
                item = db.execute(
                    "SELECT * FROM batch_items WHERE batch_id=? AND "
                    "status='PENDING' ORDER BY queue_position LIMIT 1",
                    (identifier,),
                ).fetchone()
                if item is None:
                    batches.state(db, identifier, "COMPLETED")
                    return
                if batch["status"] in {"PAUSING", "PAUSED"}:
                    batches.state(db, identifier, "PAUSED")
                    return
                batches.update_item(db, item["id"], "INSPECTING")
            self.notify(project, identifier, "batch.item_changed", item["id"])
            try:
                self.tools = self.jobs.tool_factory()
                if any(
                    not (self.tools.directory / tool).is_file()
                    for tool in ("ffmpeg.exe", "ffprobe.exe")
                ):
                    raise AppError(
                        "RUN_START_FAILED",
                        "Bundled media tools are missing; reinstall MediaQC",
                    )
                self.token.check()
                source = Path(item["absolute_path"])
                identity = fingerprint(source)
                if item["import_size_bytes"] is not None and (
                    identity["file_size_bytes"] != item["import_size_bytes"]
                    or identity["modified_at"] != item["import_modified_at"]
                ):
                    raise AppError(
                        "MEDIA_CHANGED", "Source changed after import; reimport it"
                    )
                fields, streams = map_probe(self.tools.probe(source))
                self.token.check()
                if fingerprint(source) != identity:
                    raise AppError("MEDIA_CHANGED", "Source changed during inspection")
                asset = project.save_media(
                    {**identity, **fields, "inspection_status": "COMPLETED"}, streams
                )
                with self.lock:
                    self.token.check()
                    self.jobs.start(
                        project,
                        asset,
                        json.loads(batch["qc_profile_snapshot_json"]),
                        batch["ai_mode"],
                        item["id"],
                    )
                self.notify(project, identifier, "batch.item_changed", item["id"])
                assert self.jobs.worker is not None
                while self.jobs.worker.is_alive():
                    self.jobs.worker.join(0.25)
                    self.notify(project, identifier, "batch.progress")
                with self.lock:
                    run = runs.fetch(db, str(self.jobs.identifier))
                    batches.update_item(
                        db,
                        item["id"],
                        {"COMPLETED": "COMPLETED", "CANCELLED": "CANCELLED"}.get(
                            str(run["status"]), "ERROR"
                        ),
                        str(run["error_code"]) if run["error_code"] else None,
                        str(run["error_message"]) if run["error_message"] else None,
                    )
                    if run["error_code"] == "RUN_START_FAILED":
                        raise AppError("RUN_START_FAILED", str(run["error_message"]))
            except (AppError, Cancelled) as exc:
                with self.lock:
                    cancelled = self.token.event.is_set() or isinstance(exc, Cancelled)
                    if isinstance(exc, AppError) and exc.details and not cancelled:
                        # Keep probe diagnostics out of the normal operator row.
                        # They contain tool metadata, never source media bytes.
                        log = (
                            project.path.parent
                            / "logs"
                            / f"batch-item-{item['id']}.json"
                        )
                        if log.parent.resolve() != log.parent:
                            raise OSError(
                                "Batch logs must remain project-local"
                            ) from exc
                        with log.open("x", encoding="utf-8") as output:
                            output.write(
                                runs.encode({"code": exc.code, "details": exc.details})
                            )
                        with db:
                            db.execute(
                                "UPDATE batch_items SET log_reference=? WHERE id=?",
                                (
                                    log.relative_to(project.path.parent).as_posix(),
                                    item["id"],
                                ),
                            )
                    batches.update_item(
                        db,
                        item["id"],
                        "CANCELLED" if cancelled else "ERROR",
                        exc.code if isinstance(exc, AppError) else None,
                        exc.message if isinstance(exc, AppError) else None,
                    )
                if cancelled or (
                    isinstance(exc, AppError) and exc.code == "RUN_START_FAILED"
                ):
                    raise
            finally:
                if self.tools:
                    self.tools.cancel()
            self.notify(project, identifier, "batch.item_changed", item["id"])

    def shutdown(self, project: Project | None) -> None:
        if project and self.active and self.identifier:
            with self.lock:
                status = batches.fetch(project.connection, self.identifier)["status"]
                if status not in {"COMPLETED", "FAILED"}:
                    self.dispatch(project, "batch.stop", {"batch_id": self.identifier})
        if self.worker:
            self.worker.join()
