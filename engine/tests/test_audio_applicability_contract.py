"""Executable developer contract, without persistence or production adjudication."""

from copy import deepcopy
from dataclasses import FrozenInstanceError
from typing import Any, cast

import pytest
from audio_applicability_contract import parse_contract, silence_applicability


def assignment(mxf: bool = False) -> tuple[dict[str, Any], dict[int, int]]:
    inventory = dict.fromkeys(range(1, 9), 1) if mxf else {0: 7}
    members = [(s, c) for s, count in inventory.items() for c in range(count)]
    return {
        "schema_version": "0.1.0",
        "source_sha256": "a" * 64,
        "provenance": "owner-review:production-assignment",
        "channels": [
            {
                "member": list(m),
                "role": "mix" if i < 2 else "iso",
                "expectation": "unused" if mxf and i >= 2 else "expected",
            }
            for i, m in enumerate(members)
        ],
        "programs": [
            {
                "program_id": "production",
                "layout": "stereo",
                "members": [list(m) for m in members[:2]],
            }
        ],
    }, inventory


@pytest.mark.parametrize("mxf", [False, True])
def test_assignments_separate_role_expectation_and_program(mxf: bool) -> None:
    document, inventory = assignment(mxf)
    snapshot = parse_contract(document, inventory, "a" * 64)
    assert snapshot.programs[0].members == (
        ((1, 0), (2, 0)) if mxf else ((0, 0), (0, 1))
    )
    for i, channel in enumerate(snapshot.channels):
        assert silence_applicability(snapshot, channel.member) == (
            "EXPECTED_UNUSED" if mxf and i >= 2 else "APPLICABLE"
        )
    document["channels"][0]["expectation"] = "unused"
    assert snapshot.channels[0].expectation == "expected"
    with pytest.raises(FrozenInstanceError):
        cast(Any, snapshot).provenance = "mutated"


def test_required_iso_never_inherits_unused_status() -> None:
    document, inventory = assignment(True)
    previous = parse_contract(document, inventory, "a" * 64)
    document["channels"][2]["expectation"] = "expected"
    revised = parse_contract(document, inventory, "a" * 64)
    assert revised.identity != previous.identity
    assert silence_applicability(revised, (3, 0)) == "APPLICABLE"
    assert silence_applicability(previous, (3, 0)) == "EXPECTED_UNUSED"
    assert silence_applicability(revised, (4, 0)) == "EXPECTED_UNUSED"


def test_omitted_channels_remain_unknown_and_inventory_is_bound() -> None:
    document, inventory = assignment()
    document["channels"] = document["channels"][:2]
    snapshot = parse_contract(document, inventory, "a" * 64)
    assert silence_applicability(snapshot, (0, 2)) == "UNRESOLVED"
    with pytest.raises(ValueError, match="Unknown measurement"):
        silence_applicability(snapshot, (9, 0))
    expanded = parse_contract(document, {0: 8}, "a" * 64)
    assert expanded.identity != snapshot.identity


@pytest.mark.parametrize(
    "invalid",
    [
        "version",
        "source",
        "provenance",
        "extra",
        "negative",
        "boolean",
        "missing_stream",
        "out_of_range",
        "duplicate_channel",
        "role",
        "expectation",
        "duplicate_program",
        "duplicate_member",
        "layout",
        "unused_program",
        "unknown_program",
        "extra_routing",
    ],
)
def test_invalid_contracts_are_rejected(invalid: str) -> None:
    document, inventory = assignment()
    original = deepcopy(document)
    channel = document["channels"][0]
    program = document["programs"][0]
    if invalid == "version":
        document["schema_version"] = "2"
    elif invalid == "source":
        document["source_sha256"] = "b" * 64
    elif invalid == "provenance":
        document["provenance"] = ""
    elif invalid == "extra":
        document["silence_exemption"] = True
    elif invalid == "negative":
        channel["member"] = [0, -1]
    elif invalid == "boolean":
        channel["member"] = [False, 0]
    elif invalid == "missing_stream":
        channel["member"] = [1, 0]
    elif invalid == "out_of_range":
        channel["member"] = [0, 7]
    elif invalid == "duplicate_channel":
        document["channels"].append(deepcopy(channel))
    elif invalid == "role":
        channel["role"] = "lav_means_unused"
    elif invalid == "expectation":
        channel["expectation"] = "optional"
    elif invalid == "duplicate_program":
        document["programs"].append(deepcopy(program))
    elif invalid == "duplicate_member":
        program["members"][1] = [0, 0]
    elif invalid == "layout":
        program["layout"] = "automatic"
    elif invalid == "unused_program":
        channel["expectation"] = "unused"
    elif invalid == "unknown_program":
        channel["expectation"] = "unknown"
    elif invalid == "extra_routing":
        program["gain"] = 0.5
    with pytest.raises(ValueError):
        parse_contract(document, inventory, "a" * 64)
    assert original["channels"][0]["expectation"] == "expected"


def test_program_order_is_part_of_scope_and_identity() -> None:
    document, inventory = assignment()
    before = parse_contract(document, inventory, "a" * 64)
    document["programs"][0]["members"].reverse()
    after = parse_contract(document, inventory, "a" * 64)
    assert after.identity != before.identity
    assert after.programs[0].members == ((0, 1), (0, 0))


def test_current_stream_silence_is_not_channel_coverage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace
    from typing import cast

    import numpy as np

    from mediaqc_engine.detectors.audio.levels import LevelDetector
    from mediaqc_engine.detectors.contract import DetectorContext
    from mediaqc_engine.qc.profiles import builtin

    # Characterize the missing production channel scope, not a clean acceptance:
    # an active mix masks five silent required ISOs in the stream RMS predicate.
    samples = np.zeros((96000, 7))
    samples[:, :2] = 0.1
    context = cast(
        DetectorContext, SimpleNamespace(qc_profile=builtin(), media_asset={})
    )
    monkeypatch.setattr(
        "mediaqc_engine.detectors.audio.levels.windows",
        lambda *_: iter([(0, samples, 48000)]),
    )
    result = LevelDetector("audio.silence").measure(
        context, {"id": "multitrack", "channel_count": 7, "duration_seconds": 2}
    )
    assert not result.findings
    assert result.metrics["channel_rms_dbfs"] == pytest.approx([-20, -20] + [-300] * 5)
