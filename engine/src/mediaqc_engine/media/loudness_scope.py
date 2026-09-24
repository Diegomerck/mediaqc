"""Qualify stream measurements using saved metadata, without changing verdicts."""

import sqlite3


def notes(db: sqlite3.Connection, run_id: str) -> list[str]:
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
