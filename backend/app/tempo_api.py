"""Project-scoped tempo scaling endpoint (x2 / 1/2 toggle).

The toggle only moves between half / original / double of the *analysis*
tempo, so repeated clicks can never run the tempo away. The analysis tempo
is the tempo map of the original analysis result (history revision 0); a
project with no edit history yet *is* its analysis result, so its current
map is the anchor.

Only the BPM values change: event times are absolute seconds, so the events,
the duration and the meter stay untouched — only the beat grid (and the
tempo written into the MIDI / MusicXML / PDF exports, which all derive from
the tempo map) moves. The change is saved as a normal edit-history revision,
so undo/redo works exactly like for event edits; the MIDI file is
regenerated from the canonical performance by the shared save path, which
already writes ``set_tempo`` from the tempo map.
"""
from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from . import main as api
from .drum_events import DrumPerformance, TempoChange

router = APIRouter()

#: Toggle gears relative to the analysis tempo: half, original, double.
MIN_RATIO = 0.5
MAX_RATIO = 2.0
#: Hard BPM ceiling from the TempoChange model (bpm <= 400).
MAX_BPM = 400.0
#: The default map the exporters assume when a performance has none.
DEFAULT_BPM = 120.0


class TempoScaleRequest(BaseModel):
    factor: float = Field(
        ...,
        description="2.0 to double the tempo, 0.5 to halve it",
    )

    @field_validator("factor")
    @classmethod
    def only_double_or_half(cls, value: float) -> float:
        if value not in (0.5, 2.0):
            raise ValueError("factor must be 2.0 (double) or 0.5 (half)")
        return value


def _round_tempo(bpm: float) -> float:
    """Render a BPM value with at most one decimal (61.5234 -> 61.5).

    Same rule as the MusicXML exporter's ``_format_tempo``: one decimal, so
    a double-then-half round-trip lands exactly on the displayed value.
    """
    return round(bpm, 1)


def _normalized_map(tempo_map: list[TempoChange]) -> list[TempoChange]:
    """The map the exporters assume when a performance has none."""
    if tempo_map:
        return list(tempo_map)
    return [
        TempoChange(
            time_seconds=0.0, bpm=DEFAULT_BPM, numerator=4, denominator=4
        )
    ]


def _anchor_tempo_map(
    connection: sqlite3.Connection,
    project_id: str,
    current: DrumPerformance,
) -> list[TempoChange]:
    """Tempo map of the original analysis (history revision 0).

    A project with no edit history yet has no revisions; its current map
    *is* the analysis result, so it is its own anchor.
    """
    row = connection.execute(
        "SELECT performance_json FROM performance_revisions "
        "WHERE project_id=? ORDER BY revision ASC LIMIT 1",
        (project_id,),
    ).fetchone()
    if row is None:
        return _normalized_map(current.tempo_map)
    anchor = DrumPerformance.model_validate_json(
        row["performance_json"]
    ).tempo_map
    return _normalized_map(anchor)


def _anchor_bpm_for(
    change: TempoChange, anchor: list[TempoChange]
) -> float:
    """Anchor BPM for one segment: the segment starting at the same time,
    or the change's own BPM when the anchor has no such segment."""
    for anchor_change in anchor:
        if anchor_change.time_seconds == change.time_seconds:
            return anchor_change.bpm
    return change.bpm


def scale_tempo_map(
    tempo_map: list[TempoChange],
    factor: float,
    anchor: list[TempoChange],
) -> list[TempoChange]:
    """Scale every segment's BPM by ``factor``, clamped to the anchor range.

    Each segment lands in [0.5x, 2x] of its analysis BPM (and never above
    400 BPM), rounded to one decimal. Meter and segment times are untouched.
    """
    if factor not in (0.5, 2.0):
        raise ValueError("factor must be 2.0 (double) or 0.5 (half)")
    normalized_anchor = _normalized_map(anchor)
    scaled: list[TempoChange] = []
    for change in _normalized_map(tempo_map):
        anchor_bpm = _anchor_bpm_for(change, normalized_anchor)
        bpm = _round_tempo(
            min(
                max(change.bpm * factor, MIN_RATIO * anchor_bpm),
                min(MAX_RATIO * anchor_bpm, MAX_BPM),
            )
        )
        scaled.append(
            TempoChange(
                time_seconds=change.time_seconds,
                bpm=bpm,
                numerator=change.numerator,
                denominator=change.denominator,
            )
        )
    return scaled


def _tempo_status(
    tempo_map: list[TempoChange], anchor: list[TempoChange]
) -> dict[str, Any]:
    """Current gear of the toggle, from the displayed (first) tempo."""
    current = _normalized_map(tempo_map)
    anchor_map = _normalized_map(anchor)
    ratio = round(current[0].bpm / anchor_map[0].bpm, 2)
    return {
        "tempo_map": [change.model_dump() for change in current],
        "bpm": current[0].bpm,
        "ratio": ratio,
        "at_min": ratio <= MIN_RATIO + 1e-9,
        "at_max": ratio >= MAX_RATIO - 1e-9,
    }


@router.get("/api/projects/{project_id}/tempo")
def get_project_tempo(project_id: str) -> dict[str, Any]:
    with api.connect_db() as connection:
        _, performance = api._load_editable_performance(connection, project_id)
        anchor = _anchor_tempo_map(connection, project_id, performance)
        return _tempo_status(performance.tempo_map, anchor)


@router.post("/api/projects/{project_id}/tempo")
def scale_project_tempo(
    project_id: str, payload: TempoScaleRequest
) -> dict[str, Any]:
    with api.connect_db() as connection:
        connection.execute("BEGIN IMMEDIATE")
        row, performance = api._load_editable_performance(connection, project_id)
        anchor = _anchor_tempo_map(connection, project_id, performance)
        try:
            scaled = scale_tempo_map(
                performance.tempo_map, payload.factor, anchor
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        updated = DrumPerformance.model_validate(
            {
                **performance.model_dump(),
                "tempo_map": [change.model_dump() for change in scaled],
            }
        )
        api._save_edited_performance(
            connection, row["id"], row["midi_filename"], updated
        )
    return {
        "factor": payload.factor,
        "performance": updated.model_dump(),
        **_tempo_status(scaled, anchor),
    }
