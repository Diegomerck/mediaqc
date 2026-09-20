"""Importable fake embedded adapter for spawned Phase 8 test workers only."""

import socket
import time
from pathlib import Path
from typing import cast

from mediaqc_engine import ai


class FakeProvider:
    def __init__(self, path: Path, mode: str = "ok"):
        self.model = ai.Model("embedded-test", "fixture", "1.0", path)
        self.mode = mode

    def compatible(self) -> bool:
        if self.mode == "capability_error":
            raise RuntimeError("Private data must not reach logs")
        return self.mode != "incompatible"

    def review(self, context: dict[str, object], max_output_tokens: int) -> object:
        assert max_output_tokens == 512
        if self.mode == "network_attempt":
            socket.create_connection(("127.0.0.1", 9))
        if self.mode == "fail":
            raise RuntimeError("Sensitive content")
        if self.mode == "timeout":
            time.sleep(10)
        if self.mode == "malformed":
            return {"severity": "INFO"}
        if self.mode == "oversized":
            return "x" * (ai.MAX_OUTPUT + 1)
        if self.mode == "mutate":
            cast(dict[str, object], context["measurements"])["measured"] = -999
        return {
            "schema_version": "1.0.0",
            "finding_id": context["finding_id"],
            "model_id": self.model.model_id,
            "model_version": self.model.version,
            "classification": "AMBIGUOUS",
            "confidence": 0.5,
            "summary": "Review the saved evidence.",
            "recommended_action": "REVIEW",
            "evidence_refs": [
                item["id"] for item in cast(list[dict[str, object]], context["images"])
            ],
        }
