"""Tempo-map-aware quantization for canonical drum performances."""
from __future__ import annotations

from math import floor, isfinite
from typing import Literal

from .drum_events import DrumPerformance, TempoChange

Subdivision = Literal["1/4", "1/8", "1/16", "1/32"]
_GRID_DENOMINATORS = {"1/4": 4, "1/8": 8, "1/16": 16, "1/32": 32}


def quantize_performance(
    performance: DrumPerformance,
    *,
    subdivision: Subdivision = "1/16",
    strength: float = 100,
) -> DrumPerformance:
    """Move event times toward the nearest local tempo grid.

    Each tempo segment starts a fresh grid at its change timestamp. Grid spacing
    is expressed in quarter-note subdivisions, independent of the bar meter.
    A segment's last grid point is clamped before its next tempo change.
    """
    if subdivision not in _GRID_DENOMINATORS:
        raise ValueError("subdivision must be one of 1/4, 1/8, 1/16, or 1/32")
    if not isfinite(strength) or not 0 <= strength <= 100:
        raise ValueError("strength must be a finite value between 0 and 100")
    if strength == 0 or not performance.events:
        return performance.model_copy(deep=True)

    changes = list(performance.tempo_map)
    if not changes or changes[0].time_seconds > 0:
        changes.insert(0, TempoChange(time_seconds=0, bpm=120))

    denominator = _GRID_DENOMINATORS[subdivision]
    segments: list[tuple[float, float, float]] = []
    for index, change in enumerate(changes):
        end = changes[index + 1].time_seconds if index + 1 < len(changes) else performance.duration_seconds
        quarter_seconds = 60.0 / change.bpm
        step = quarter_seconds * 4.0 / denominator
        segments.append((change.time_seconds, end, step))

    amount = strength / 100.0
    updated_events = []
    for event in performance.events:
        segment = next(
            (item for item in segments if item[0] <= event.time_seconds < item[1]),
            segments[-1],
        )
        start, end, step = segment
        offset = max(0.0, event.time_seconds - start)
        grid_index = floor(offset / step + 0.5)
        snapped = start + grid_index * step
        if end > start:
            snapped = min(snapped, start + max(0, floor((end - start) / step + 1e-9)) * step)
        target = min(performance.duration_seconds, max(0.0, snapped))
        new_time = event.time_seconds + (target - event.time_seconds) * amount
        updated_events.append(event.model_copy(update={"time_seconds": new_time}))

    return performance.model_copy(update={"events": updated_events})
