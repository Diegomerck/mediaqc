"""Qualify stream measurements using saved metadata, without changing verdicts."""

import sqlite3


def notes(db: sqlite3.Connection, run_id: str) -> list[str]:
    assignment = db.execute(
        "SELECT policy_version FROM audio_assignments WHERE analysis_run_id=?",
        (run_id,),
    ).fetchone()
    if assignment:
        result = [
            "Explicit audio applicability: silence is evaluated per channel; "
            "only expected channels use profile severity. Unused and unknown "
            "silence is retained as INFO. Unknown coverage is not a clean "
            "technical conclusion.",
            "Program loudness uses the saved ordered channel mapping. Raw "
            "stream loudness is retained as scope evidence, not designated "
            "program compliance. Inspect program measurements and execution "
            "errors; PASS does not resolve unknown channel expectations.",
        ]
        if not db.execute(
            "SELECT 1 FROM audio_assignment_programs WHERE analysis_run_id=? LIMIT 1",
            (run_id,),
        ).fetchone():
            result.append(
                "No audio program is designated; "
                "program loudness compliance is unresolved."
            )
        unknown = db.execute(
            "SELECT COUNT(*) FROM audio_assignment_channels "
            "WHERE analysis_run_id=? AND expectation='unknown'",
            (run_id,),
        ).fetchone()[0]
        if unknown:
            result.append(
                f"{unknown} audio channels have unknown activity expectations; "
                "silence coverage remains unresolved for those channels."
            )
        return result
    streams = list(
        db.execute(
            "SELECT s.stream_index,s.channel_count,s.channel_layout "
            "FROM media_streams s "
            "JOIN analysis_runs r ON r.media_asset_id=s.media_asset_id "
            "WHERE r.id=? AND s.stream_type='audio' ORDER BY s.stream_index",
            (run_id,),
        )
    )
    result = []
    for stream in streams:
        layout = str(stream["channel_layout"] or "").strip().lower()
        if (stream["channel_count"] or 0) > 2 and (
            not layout or layout in {"unknown", "unspecified"} or " channels" in layout
        ):
            result.append(
                f"Audio stream {stream['stream_index']} has "
                f"{stream['channel_count']} channels "
                "but no declared channel assignment. "
                "Loudness may use a decoder-guessed layout and is provisional. "
                "Confirm the channel assignment before judging program loudness "
                "compliance. Saved measurements and profile findings are unchanged."
            )
    if len(streams) > 1:
        result.append(
            "Loudness is measured separately for each audio stream. Their intended "
            "program grouping is unknown; these results do not establish combined "
            "program loudness compliance. No streams were mixed or reassigned."
        )
    return result
