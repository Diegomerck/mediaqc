"""One active worker per engine. Requests never wait for analysis to finish."""

import json
import logging
import threading
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

from mediaqc_engine.app.errors import AppError
from mediaqc_engine.db import runs
from mediaqc_engine.db.project import Project, now
from mediaqc_engine.detectors.contract import Detector, DetectorContext
from mediaqc_engine.jobs.cancellation import CancellationToken, Cancelled
from mediaqc_engine.jobs.recovery import Journal
from mediaqc_engine.media.inspection import fingerprint, map_probe
from mediaqc_engine.media.tools import MediaTools
from mediaqc_engine.qc import profiles

EventSink = Callable[[str, dict[str, object]], None]
METHODS = {"analysis.start", "analysis.cancel", "analysis.retry", "analysis.get"}
LOG = logging.getLogger(__name__)


class JobManager:
    def __init__(
        self,
        emit: EventSink,
        journal: Journal,
        detectors: tuple[Detector, ...] = (),
        tool_factory: Callable[[], MediaTools] = MediaTools,
    ):
        self.emit = emit
        self.journal = journal
        self.detectors = detectors
        self.tool_factory = tool_factory
        self.worker: threading.Thread | None = None
        self.token = CancellationToken()
        self.tools: MediaTools | None = None
        self.identifier: str | None = None
        self.progress: dict[str, object] = {}
        self.lock = threading.RLock()
        self.stopping = False

    @property
    def active(self) -> bool:
        return self.worker is not None and self.worker.is_alive()

    def dispatch(
        self, project: Project, method: str, params: dict[str, object]
    ) -> dict[str, object]:
        expected = (
            {
                "project_id",
                "media_asset_id",
                "profile_key",
                "profile_version",
                "ai_mode",
            }
            if method == "analysis.start"
            else {"analysis_run_id"}
        )
        if set(params) != expected or any(
            not isinstance(value, str) for value in params.values()
        ):
            raise AppError("INVALID_REQUEST", "Invalid analysis parameters")
        with self.lock:
            if method == "analysis.start":
                if params["project_id"] != project.id:
                    raise AppError(
                        "PROJECT_NOT_FOUND", "Open the requested project first"
                    )
                if params["ai_mode"] != "OFF":
                    raise AppError("INVALID_REQUEST", "Only AI OFF is available")
                profile = profiles.get(params["profile_key"], params["profile_version"])
                return self.start(project, str(params["media_asset_id"]), profile)
            identifier = str(params["analysis_run_id"])
            run = runs.fetch(project.connection, identifier)
            if method == "analysis.get":
                result = runs.summary(project.connection, identifier)
                result["progress"] = (
                    dict(self.progress)
                    if identifier == self.identifier
                    else {
                        "overall_progress": 1.0
                        if run["status"] == "COMPLETED"
                        else 0.0,
                        "stage": run["status"],
                        "current_detector_id": None,
                        "media_time_seconds": None,
                        "media_duration_seconds": None,
                        "message": run["error_message"] or "Saved run state",
                    }
                )
                return result
            if method == "analysis.retry":
                if run["status"] not in runs.TERMINAL:
                    raise AppError(
                        "RUN_START_FAILED",
                        "Wait for the previous run to finish before retrying",
                    )
                snapshot = json.loads(str(run["qc_profile_snapshot_json"]))
                profiles.validate(snapshot)
                return self.start(project, str(run["media_asset_id"]), snapshot)
            if run["status"] in runs.TERMINAL:
                raise AppError("RUN_ALREADY_TERMINAL", "Run has already finished")
            if identifier != self.identifier:
                raise AppError(
                    "RUN_NOT_FOUND", "This engine does not own the active run"
                )
            self.token.cancel()
            if self.tools is not None:
                self.tools.cancel()
            return {
                "analysis_run_id": identifier,
                "status": run["status"],
                "cancellation_requested": True,
            }

    def start(
        self, project: Project, asset_id: str, profile: dict[str, object]
    ) -> dict[str, object]:
        if (
            self.active
            and self.identifier is not None
            and runs.fetch(project.connection, self.identifier)["status"]
            in runs.TERMINAL
        ):
            assert self.worker is not None
            self.worker.join(1)
        if self.stopping or self.active:
            raise AppError(
                "RUN_START_FAILED",
                "One run may be active; cancel or wait before starting another",
            )
        profiles.validate(profile)
        row = project.connection.execute(
            "SELECT * FROM media_assets WHERE id=? AND project_id=?",
            (asset_id, project.id),
        ).fetchone()
        if row is None:
            raise AppError("MEDIA_NOT_FOUND", "Select media in this project")
        asset = dict(row)
        if asset["inspection_status"] != "COMPLETED":
            raise AppError(
                "RUN_START_FAILED", "Inspect the media successfully before analysis"
            )
        identifier = runs.create(
            project.connection,
            project.id,
            asset_id,
            profile,
            asset["fast_fingerprint_sha256"],
        )
        self.identifier = identifier
        self.token = CancellationToken()
        self.tools = self.tool_factory()
        self.tools.cancelled = self.token.event
        self.tools.cache = project.path.parent / "cache" / identifier
        self.progress = {
            "overall_progress": 0.0,
            "stage": "QUEUED",
            "current_detector_id": None,
            "media_time_seconds": None,
            "media_duration_seconds": asset["duration_seconds"],
            "message": "Queued locally",
        }
        try:
            self.journal.record(identifier, project.path)
            self.worker = threading.Thread(
                target=self.execute,
                args=(project.path, identifier, asset, profile, self.tools, self.token),
                name=f"run-{identifier}",
            )
            self.worker.start()
        except (OSError, RuntimeError) as exc:
            runs.transition(
                project.connection,
                identifier,
                "FAILED",
                "RUN_START_FAILED",
                "Could not start the local worker",
            )
            raise AppError(
                "RUN_START_FAILED", "Could not start the local worker"
            ) from exc
        return {"analysis_run_id": identifier, "status": "QUEUED"}

    def send(self, event: str, identifier: str, data: dict[str, object]) -> None:
        self.emit(event, {"analysis_run_id": identifier, **data})

    def update(
        self,
        identifier: str,
        stage: str,
        fraction: float,
        message: str,
        detector: str | None = None,
    ) -> None:
        with self.lock:
            self.progress.update(
                stage=stage,
                overall_progress=max(0.0, min(1.0, fraction)),
                current_detector_id=detector,
                message=message,
            )
            value = dict(self.progress)
        self.send("analysis.progress", identifier, value)

    def execute(
        self,
        path: Path,
        identifier: str,
        asset: dict[str, object],
        profile: dict[str, object],
        tools: MediaTools,
        token: CancellationToken,
    ) -> None:
        project: Project | None = None
        try:
            project = Project.open(path)
            db = project.connection
            self.send("analysis.status", identifier, {"status": "QUEUED"})
            token.check()
            runs.transition(db, identifier, "INSPECTING")
            self.send("analysis.status", identifier, {"status": "INSPECTING"})
            self.update(
                identifier,
                "INSPECTING",
                0.0,
                "Verifying source identity and bundled tools",
            )
            source = Path(str(asset["absolute_path"]))
            if (
                fingerprint(source)["fast_fingerprint_sha256"]
                != asset["fast_fingerprint_sha256"]
            ):
                raise AppError(
                    "MEDIA_CHANGED", "Source changed since inspection; inspect it again"
                )
            for tool in ("ffmpeg", "ffprobe"):
                token.check()
                version = tools.capability(tool)
                token.check()
                if not version["available"]:
                    raise AppError(
                        "RUN_START_FAILED", "Bundled media tools are unavailable"
                    )
                with db:
                    db.execute(
                        f"UPDATE analysis_runs SET {tool}_version=? WHERE id=?",
                        (version["version"], identifier),
                    )
            map_probe(tools.probe(source))
            token.check()
            if (
                fingerprint(source)["fast_fingerprint_sha256"]
                != asset["fast_fingerprint_sha256"]
            ):
                raise AppError("MEDIA_CHANGED", "Source changed during run preparation")
            streams = tuple(
                dict(row)
                for row in db.execute(
                    "SELECT * FROM media_streams WHERE media_asset_id=? "
                    "ORDER BY stream_index",
                    (asset["id"],),
                )
            )
            context = DetectorContext(
                identifier,
                asset,
                streams,
                profile,
                str(tools.cache),
                token,
                tools,
                logging.LoggerAdapter(LOG, {"analysis_run_id": identifier}),
            )
            runs.transition(db, identifier, "ANALYZING")
            self.send("analysis.status", identifier, {"status": "ANALYZING"})
            self.update(identifier, "ANALYZING", 0.1, "Scheduling available detectors")
            scheduled = [
                detector
                for detector in self.detectors
                if profiles.enabled(profile, detector.detector_id)
            ]
            if not scheduled:
                raise AppError(
                    "RUN_START_FAILED",
                    "No QC detectors are installed in Phase 3; orchestration "
                    "is ready for Phase 4",
                )
            execution_ids = []
            with db:
                for detector in scheduled:
                    execution_id = str(uuid4())
                    execution_ids.append(execution_id)
                    db.execute(
                        "INSERT INTO detector_executions "
                        "(id,analysis_run_id,detector_id,detector_version,"
                        "status,progress) VALUES (?,?,?,?,?,?)",
                        (
                            execution_id,
                            identifier,
                            detector.detector_id,
                            detector.detector_version,
                            "PENDING",
                            0.0,
                        ),
                    )
            failed = False
            for index, (detector, execution_id) in enumerate(
                zip(scheduled, execution_ids, strict=True)
            ):
                token.check()
                status, code, message = "COMPLETED", None, None
                metrics: dict[str, object] = {}
                self.update(
                    identifier,
                    "ANALYZING",
                    0.1 + 0.9 * index / len(scheduled),
                    "Running detector",
                    detector.detector_id,
                )
                with db:
                    db.execute(
                        "UPDATE detector_executions SET "
                        "status='RUNNING',started_at=? WHERE id=?",
                        (now(), execution_id),
                    )
                self.send(
                    "analysis.detector_status",
                    identifier,
                    {"detector_id": detector.detector_id, "status": "RUNNING"},
                )
                try:
                    if not detector.supports(context):
                        status = "SKIPPED"
                    else:
                        result = detector.analyze(context)
                        token.check()
                        # Phase 3 has no production detectors/findings. Later algorithms
                        # integrate their persistence at this explicit result boundary.
                        if result.findings:
                            raise AppError(
                                "ENGINE_INTERNAL_ERROR",
                                "Finding-producing detectors are unavailable "
                                "in this phase",
                            )
                        metrics = result.metrics
                        runs.encode(metrics)
                        for warning in result.warnings:
                            context.logger.warning(
                                "Detector warning: %s",
                                warning.get("code", "DETECTOR_WARNING"),
                            )
                except Cancelled:
                    raise
                except Exception as exc:
                    token.check()
                    status, code, message = (
                        "FAILED",
                        "ENGINE_INTERNAL_ERROR",
                        "Detector execution failed; see engine log",
                    )
                    failed = True
                    context.logger.error(
                        "detector=%s failure=%s",
                        detector.detector_id,
                        type(exc).__name__,
                    )
                with db:
                    db.execute(
                        "UPDATE detector_executions SET "
                        "status=?,completed_at=?,progress=1,error_code=?,"
                        "error_message=?,metrics_json=? WHERE id=?",
                        (
                            status,
                            now(),
                            code,
                            message,
                            runs.encode(metrics),
                            execution_id,
                        ),
                    )
                self.send(
                    "analysis.detector_status",
                    identifier,
                    {
                        "detector_id": detector.detector_id,
                        "status": status,
                        "error_code": code,
                        "error_message": message,
                    },
                )
            token.check()
            if failed:
                raise AppError(
                    "ENGINE_INTERNAL_ERROR",
                    "One or more detectors failed; remaining safe work finished",
                )
            self.finish(project, identifier, "COMPLETED", token)
        except Exception as exc:
            if project is not None:
                cancelled = token.event.is_set() or isinstance(exc, Cancelled)
                code = (
                    exc.code if isinstance(exc, AppError) else "ENGINE_INTERNAL_ERROR"
                )
                message = (
                    exc.message
                    if isinstance(exc, AppError)
                    else "Run failed; see engine log"
                )
                LOG.warning("run=%s failure=%s", identifier, type(exc).__name__)
                self.finish(
                    project,
                    identifier,
                    "CANCELLED" if cancelled else "FAILED",
                    token,
                    code,
                    message,
                )
        finally:
            tools.cancel()
            if project is not None:
                project.close()

    def finish(
        self,
        project: Project,
        identifier: str,
        status: str,
        token: CancellationToken,
        code: str | None = None,
        message: str | None = None,
    ) -> None:
        # Serialize terminal commit against cancellation acceptance.
        with self.lock:
            if token.event.is_set():
                status, code, message = "CANCELLED", None, None
            if self.tools is not None:
                self.tools.cancel()
            with project.connection:
                project.connection.execute(
                    "UPDATE detector_executions SET status=?,completed_at=? "
                    "WHERE analysis_run_id=? AND status IN ('PENDING','RUNNING')",
                    (
                        "CANCELLED" if status == "CANCELLED" else "FAILED",
                        now(),
                        identifier,
                    ),
                )
            runs.transition(project.connection, identifier, status, code, message)
            self.progress.update(stage=status, message=message or status)
            if status == "COMPLETED":
                self.progress["overall_progress"] = 1.0
        self.send("analysis.status", identifier, {"status": status})
        self.send("analysis.progress", identifier, dict(self.progress))
        data: dict[str, object] = {"status": status}
        if status == "COMPLETED":
            data.update(overall_result="PASS", counts={"INFO": 0, "WARN": 0, "FAIL": 0})
        if status == "FAILED":
            data.update(error_code=code, error_message=message)
        self.send(f"analysis.{status.lower()}", identifier, data)
        self.journal.finish(identifier)

    def shutdown(self) -> None:
        with self.lock:
            self.stopping = True
            self.token.cancel()
            if self.tools is not None:
                self.tools.cancel()
        if self.worker is not None:
            self.worker.join()
