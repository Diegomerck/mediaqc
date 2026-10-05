"""Immutable source-bound audio applicability; explicit_audio_v1."""

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from mediaqc_engine.jobs.cancellation import CancellationToken

type Member = tuple[int, int]
type Applicability = Literal["APPLICABLE", "EXPECTED_UNUSED", "UNRESOLVED"]


@dataclass(frozen=True)
class Channel:
    member: Member
    role: str
    expectation: str


@dataclass(frozen=True)
class Program:
    program_id: str
    layout: str
    members: tuple[Member, ...]


@dataclass(frozen=True)
class Snapshot:
    identity: str
    source_sha256: str
    provenance: str
    channels: tuple[Channel, ...]
    programs: tuple[Program, ...]


def fields(value: Any, expected: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError("Contract fields must match the versioned schema")
    return value


def parse_contract(
    document: dict[str, Any], inventory: Mapping[int, int], source_sha256: str
) -> Snapshot:
    """Validate an explicit source-bound snapshot against probed audio channels."""
    fields(
        document,
        {"schema_version", "source_sha256", "provenance", "channels", "programs"},
    )
    if document["schema_version"] != "0.1.0":
        raise ValueError("Unsupported applicability schema")
    fingerprint = document["source_sha256"]
    if (
        not isinstance(fingerprint, str)
        or not re.fullmatch(r"[0-9a-f]{64}", fingerprint)
        or fingerprint != source_sha256
    ):
        raise ValueError("Source identity mismatch")
    provenance = document["provenance"]
    if not isinstance(provenance, str) or not provenance.strip():
        raise ValueError("Explicit assignment provenance required")
    if not inventory or any(
        type(i) is not int or i < 0 or type(n) is not int or not 1 <= n <= 64
        for i, n in inventory.items()
    ):
        raise ValueError("Invalid probed audio inventory")

    def member(value: Any) -> Member:
        if (
            not isinstance(value, list)
            or len(value) != 2
            or any(type(v) is not int or v < 0 for v in value)
            or value[0] not in inventory
            or value[1] >= inventory[value[0]]
        ):
            raise ValueError("Member must identify an existing audio channel")
        return value[0], value[1]

    if not isinstance(document["channels"], list) or not isinstance(
        document["programs"], list
    ):
        raise ValueError("Channels and programs must be lists")
    channels: dict[Member, Channel] = {}
    for raw in document["channels"]:
        item = fields(raw, {"member", "role", "expectation"})
        key = member(item["member"])
        if key in channels:
            raise ValueError("Duplicate channel assignment")
        if item["role"] not in ("mix", "iso", "other", "unknown"):
            raise ValueError("Invalid role")
        if item["expectation"] not in ("expected", "unused", "unknown"):
            raise ValueError("Invalid activity expectation")
        channels[key] = Channel(key, item["role"], item["expectation"])
    # Missing information is unknown, never an inferred unused channel.
    for index, count in inventory.items():
        for channel in range(count):
            key = (index, channel)
            channels.setdefault(key, Channel(key, "unknown", "unknown"))
    programs: list[Program] = []
    ids: set[str] = set()
    for raw in document["programs"]:
        item = fields(raw, {"program_id", "layout", "members"})
        identifier = item["program_id"]
        if (
            not isinstance(identifier, str)
            or not identifier.strip()
            or identifier in ids
        ):
            raise ValueError("Program IDs must be nonempty and unique")
        if item["layout"] not in ("mono", "stereo") or not isinstance(
            item["members"], list
        ):
            raise ValueError("Explicit mono/stereo layout required")
        members = tuple(member(v) for v in item["members"])
        if len(members) != (1 if item["layout"] == "mono" else 2) or len(
            set(members)
        ) != len(members):
            raise ValueError("Program members must match layout without duplicates")
        if any(channels[m].expectation != "expected" for m in members):
            raise ValueError("Program members require explicit expected audio")
        programs.append(Program(identifier, item["layout"], members))
        ids.add(identifier)
    canonical = json.dumps(
        [document, sorted(inventory.items())],
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    identity = hashlib.sha256(canonical.encode()).hexdigest()
    return Snapshot(
        identity,
        fingerprint,
        provenance,
        tuple(channels[k] for k in sorted(channels)),
        tuple(programs),
    )


def silence_applicability(snapshot: Snapshot, member: Member) -> Applicability:
    """Only exact channel scope qualifies; no clean/defect/severity output."""
    for channel in snapshot.channels:
        if channel.member == member:
            if channel.expectation == "expected":
                return "APPLICABLE"
            if channel.expectation == "unused":
                return "EXPECTED_UNUSED"
            return "UNRESOLVED"
    raise ValueError("Unknown measurement channel")


def inventory(streams: tuple[dict[str, object], ...]) -> dict[int, int]:
    return {
        int(str(s["stream_index"])): int(str(s["channel_count"]))
        for s in streams
        if s["stream_type"] == "audio"
    }


def source_digest(path: "Path", token: "CancellationToken") -> str:
    token.check()
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            token.check()
            digest.update(block)
    token.check()
    return digest.hexdigest()


@dataclass(frozen=True)
class EvaluationPolicy:
    expected_unused: str
    unresolved: str
    unassigned_program: str


@lru_cache(maxsize=1)
def evaluation_policy() -> EvaluationPolicy:
    document = json.loads(
        Path(__file__)
        .with_name("audio_applicability_v1.json")
        .read_text(encoding="utf-8-sig")
    )
    fields(
        document,
        {
            "policy_version",
            "silence_expected_unused_severity",
            "silence_unresolved_severity",
            "unassigned_program_scope_severity",
        },
    )
    values = [
        document[k]
        for k in (
            "silence_expected_unused_severity",
            "silence_unresolved_severity",
            "unassigned_program_scope_severity",
        )
    ]
    if document["policy_version"] != "explicit_audio_v1" or any(
        v not in ("INFO", "WARN", "FAIL") for v in values
    ):
        raise ValueError("Invalid explicit audio applicability policy")
    return EvaluationPolicy(*values)


def applicability_severity(state: str, profile_severity: str) -> str:
    policy = evaluation_policy()
    if state == "APPLICABLE":
        return profile_severity
    if state == "EXPECTED_UNUSED":
        return policy.expected_unused
    if state == "UNRESOLVED":
        return policy.unresolved
    if state == "UNASSIGNED_PROGRAM_SCOPE":
        return policy.unassigned_program
    raise ValueError("Unknown applicability state")
