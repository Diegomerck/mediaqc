"""Optional embedded AI. Only copied, allowlisted evidence crosses the boundary.

Providers are trusted application code, never loaded from project/model files.
They must run entirely in-process in the isolated worker, use no network or
downloads, spawn no children, and honor the supplied token/resource limits.
Production runtime/model selection is deliberately deferred to Phase 9.
"""

import json
import logging
import math
import multiprocessing
import sqlite3
import time
from dataclasses import dataclass
from multiprocessing.connection import Connection
from pathlib import Path
from typing import Protocol, cast
from uuid import uuid4

from mediaqc_engine import evidence
from mediaqc_engine.db.project import now
from mediaqc_engine.db.runs import encode
from mediaqc_engine.jobs.cancellation import CancellationToken

LOG = logging.getLogger(__name__)
PROMPT_VERSION = "1.0.0"
MAX_INPUT = 1200 * 1024
MAX_OUTPUT = 8192
MAX_REVIEWS = 20
REVIEW_SECONDS = 30.0
RUN_SECONDS = 120.0


@dataclass(frozen=True)
class Model:
    provider: str
    model_id: str
    version: str
    path: Path


class Provider(Protocol):
    """Embedded adapter, with no model-manager or service dependency.

    compatible must validate runtime/model format locally without loading weights.
    review must enforce max_output_tokens and its runtime memory/context budgets.
    Model paths are installation configuration, never IPC/project input.
    """

    model: Model

    def compatible(self) -> bool: ...

    def review(self, context: dict[str, object], max_output_tokens: int) -> object: ...


def _worker(
    connection: Connection, provider: Provider, context: dict[str, object] | None
) -> None:
    # Providers cannot corrupt the engine's protocol or log media/model content.
    import os
    import sys

    def offline(event: str, args: tuple[object, ...]) -> None:
        if event.startswith(("socket.", "urllib.")) or event in {
            "subprocess.Popen",
            "os.system",
            "os.posix_spawn",
        }:
            raise PermissionError("Embedded AI cannot use network or child processes")

    sys.addaudithook(offline)
    with open(os.devnull, "w", encoding="utf-8") as sink:
        os.dup2(sink.fileno(), 1)
        os.dup2(sink.fileno(), 2)
        sys.stdout = sink
        sys.stderr = sink
        try:
            value = (
                provider.compatible()
                if context is None
                else provider.review(context, max_output_tokens=512)
            )
            payload = encode(value).encode("utf-8")
            connection.send_bytes(payload if len(payload) <= MAX_OUTPUT else b"null")
        except Exception:
            connection.send_bytes(b"null")
        finally:
            connection.close()


def invoke(
    provider: Provider,
    context: dict[str, object] | None,
    timeout: float,
    token: CancellationToken,
) -> object:
    """Spawn isolates crashes/hangs; deadlines cover startup and execution."""
    if context is not None and len(encode(context).encode()) > MAX_INPUT:
        raise ValueError("AI_INPUT_LIMIT")
    deadline = time.monotonic() + timeout
    ctx = multiprocessing.get_context("spawn")
    reader, writer = ctx.Pipe(duplex=False)
    process = ctx.Process(target=_worker, args=(writer, provider, context), daemon=True)
    try:
        token.check()
        process.start()
        writer.close()
        while time.monotonic() < deadline:
            token.check()
            if reader.poll(0.025):
                return json.loads(reader.recv_bytes(MAX_OUTPUT))
            if not process.is_alive():
                raise ValueError("AI_RUNTIME_FAILED")
        raise TimeoutError("AI_TIMEOUT")
    finally:
        if process.pid is not None:
            if process.is_alive():
                process.terminate()
            process.join(1)
            if process.is_alive():
                process.kill()
                process.join()
            process.close()
        reader.close()
        writer.close()


def capability(provider: Provider | None) -> dict[str, object]:
    result: dict[str, object] = {
        "local_available": False,
        "provider": None,
        "model_id": None,
        "model_version": None,
        "reason": "No embedded provider/model installed",
    }
    if provider is None:
        return result
    try:
        model = provider.model
        if not all(
            0 < len(item) <= 200
            for item in (model.provider, model.model_id, model.version)
        ):
            raise ValueError("Invalid model identity")
        if not model.path.is_absolute() or str(model.path).startswith(("\\\\", "//")):
            raise ValueError("Model must be an installed local file")
        if not model.path.is_file() or model.path.stat().st_size == 0:
            raise ValueError("Missing model")
        if invoke(provider, None, 3.0, CancellationToken()) is not True:
            raise ValueError("Incompatible model/runtime")
        result.update(
            local_available=True,
            provider=model.provider,
            model_id=model.model_id,
            model_version=model.version,
            reason=None,
        )
    except Exception:
        LOG.warning("AI_UNAVAILABLE: embedded capability check failed")
        result["reason"] = "Embedded runtime/model missing, incompatible or unavailable"
    return result


def grounded_input(
    db: sqlite3.Connection, root: Path, finding: sqlite3.Row
) -> dict[str, object]:
    """No paths, freeform file tags, operator notes, or source bytes are supplied."""
    images: list[dict[str, object]] = []
    for row in db.execute(
        "SELECT id,evidence_type FROM evidence WHERE finding_id=? "
        "AND mime_type='image/png' ORDER BY rowid LIMIT 3",
        (finding["id"],),
    ):
        artifact = evidence.read(db, root, row["id"])
        images.append(
            {
                "id": row["id"],
                "kind": row["evidence_type"],
                "data_url": artifact["data_url"],
                "start_time_seconds": artifact["start_time_seconds"],
                "end_time_seconds": artifact["end_time_seconds"],
            }
        )
    return {
        "prompt_version": PROMPT_VERSION,
        "instruction": "Review only this evidence. Return advisory schema 1.0.0. "
        "Never compute or override measurements, timestamps, severity or disposition.",
        "finding_id": finding["id"],
        "detector_id": finding["detector_id"],
        "detector_version": finding["detector_version"],
        "start_time_seconds": finding["start_time_seconds"],
        "end_time_seconds": finding["end_time_seconds"],
        "measurements": json.loads(finding["measurements_json"]),
        "thresholds": json.loads(finding["threshold_json"] or "{}"),
        "images": images,
    }


def validate(
    value: object, context: dict[str, object], model: Model
) -> dict[str, object]:
    fields = {
        "schema_version",
        "finding_id",
        "model_id",
        "model_version",
        "classification",
        "confidence",
        "summary",
        "recommended_action",
        "evidence_refs",
    }
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError("AI_INVALID_OUTPUT")
    for key, expected in (
        ("schema_version", "1.0.0"),
        ("finding_id", context["finding_id"]),
        ("model_id", model.model_id),
        ("model_version", model.version),
    ):
        if value[key] != expected:
            raise ValueError("AI_INVALID_IDENTITY")
    for key, maximum in (("summary", 2000), ("classification", 100)):
        if (
            not isinstance(value[key], str)
            or not 1 <= len(value[key].strip()) <= maximum
        ):
            raise ValueError("AI_INVALID_TEXT")
    confidence = value["confidence"]
    if (
        type(confidence) not in (int, float)
        or not math.isfinite(confidence)
        or not 0 <= confidence <= 1
    ):
        raise ValueError("AI_INVALID_CONFIDENCE")
    if value["recommended_action"] not in (
        "REVIEW",
        "LIKELY_VALID",
        "LIKELY_FALSE_POSITIVE",
    ):
        raise ValueError("AI_INVALID_ACTION")
    allowed = {
        image["id"] for image in cast(list[dict[str, object]], context["images"])
    }
    refs = value["evidence_refs"]
    if (
        not isinstance(refs, list)
        or len(refs) > 3
        or any(not isinstance(ref, str) or ref not in allowed for ref in refs)
    ):
        raise ValueError("AI_INVALID_EVIDENCE")
    if len(encode(value).encode()) > MAX_OUTPUT:
        raise ValueError("AI_OUTPUT_LIMIT")
    return cast(dict[str, object], value)


def review_run(
    db: sqlite3.Connection,
    root: Path,
    run_id: str,
    provider: Provider | None,
    token: CancellationToken,
) -> None:
    """Optional boundary catches all AI errors, including persistence failure."""
    if (
        db.execute(
            "SELECT ai_mode FROM analysis_runs WHERE id=?", (run_id,)
        ).fetchone()[0]
        == "OFF"
    ):
        return
    try:
        available = capability(provider)["local_available"]
        deadline = time.monotonic() + RUN_SECONDS
        for finding in db.execute(
            "SELECT * FROM findings WHERE analysis_run_id=? ORDER BY rowid LIMIT ?",
            (run_id, MAX_REVIEWS),
        ).fetchall():
            if token.event.is_set():
                return
            output = None
            code = None
            try:
                if not available or provider is None:
                    raise ValueError("AI_UNAVAILABLE")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("AI_BUDGET_EXHAUSTED")
                context = grounded_input(db, root, finding)
                output = validate(
                    invoke(provider, context, min(REVIEW_SECONDS, remaining), token),
                    context,
                    provider.model,
                )
            except Exception as exc:
                code = (
                    "AI_TIMEOUT" if isinstance(exc, TimeoutError) else "AI_UNAVAILABLE"
                )
                LOG.warning(
                    "finding=%s AI review unavailable (%s)", finding["id"], code
                )
            with db:
                db.execute(
                    "INSERT INTO ai_reviews "
                    "(id,finding_id,model_id,model_version,prompt_version,status,"
                    "error_code,output_json,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        str(uuid4()),
                        finding["id"],
                        provider.model.model_id if provider else None,
                        provider.model.version if provider else None,
                        PROMPT_VERSION,
                        "COMPLETED" if output is not None else "UNAVAILABLE",
                        code,
                        encode(output) if output is not None else None,
                        now(),
                    ),
                )
    except Exception:
        LOG.warning(
            "run=%s AI review unavailable; deterministic result retained", run_id
        )
