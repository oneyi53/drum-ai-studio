"""Canonical drum-event schema and deterministic transcription metrics.

Times are absolute seconds from the start of the audio. MIDI velocity uses
the standard 1..127 range. This module deliberately does not infer events.
"""
from __future__ import annotations

from collections import defaultdict
from enum import Enum
from math import isfinite
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DrumInstrument(str, Enum):
    KICK = "kick"
    SNARE = "snare"
    CLOSED_HIHAT = "closed_hihat"
    OPEN_HIHAT = "open_hihat"
    PEDAL_HIHAT = "pedal_hihat"
    RIDE = "ride"
    CRASH = "crash"
    HIGH_TOM = "high_tom"
    MID_TOM = "mid_tom"
    LOW_TOM = "low_tom"
    OTHER = "other"


class DrumEvent(BaseModel):
    """One note-like drum hit in absolute audio time."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: str(uuid4()))
    time_seconds: float = Field(ge=0, description="Absolute time from audio start")
    instrument: DrumInstrument
    velocity: int = Field(default=96, ge=1, le=127)
    confidence: float | None = Field(default=None, ge=0, le=1)
    source: Literal["model", "manual", "imported"] = "model"
    manually_corrected: bool = False

    @field_validator("time_seconds")
    @classmethod
    def finite_time(cls, value: float) -> float:
        if not isfinite(value):
            raise ValueError("time_seconds must be finite")
        return value


class TempoChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    time_seconds: float = Field(ge=0)
    bpm: float = Field(gt=0, le=400)
    numerator: int = Field(default=4, ge=1, le=32)
    denominator: int = Field(default=4, ge=1, le=32)


class DrumPerformance(BaseModel):
    """Canonical editable performance shared by editor and exporters."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    duration_seconds: float = Field(gt=0)
    events: list[DrumEvent] = Field(default_factory=list)
    tempo_map: list[TempoChange] = Field(default_factory=list)

    @field_validator("duration_seconds")
    @classmethod
    def finite_duration(cls, value: float) -> float:
        if not isfinite(value):
            raise ValueError("duration_seconds must be finite")
        return value

    @field_validator("events")
    @classmethod
    def events_within_duration(cls, events: list[DrumEvent], info):
        duration = info.data.get("duration_seconds")
        if duration is not None and any(event.time_seconds > duration for event in events):
            raise ValueError("event time cannot exceed performance duration")
        return events

    @field_validator("tempo_map")
    @classmethod
    def ordered_tempo_map(cls, changes: list[TempoChange]):
        times = [change.time_seconds for change in changes]
        if times != sorted(times) or len(times) != len(set(times)):
            raise ValueError("tempo_map must be strictly ordered by time_seconds")
        return changes


class InstrumentMetrics(BaseModel):
    reference_events: int
    predicted_events: int
    true_positives: int
    false_positives: int
    false_negatives: int
    precision: float
    recall: float
    f1: float
    mean_absolute_timing_error_ms: float | None


class EvaluationReport(BaseModel):
    tolerance_ms: float
    overall: InstrumentMetrics
    by_instrument: dict[str, InstrumentMetrics]


def _metrics(reference: list[DrumEvent], predicted: list[DrumEvent], tolerance: float) -> InstrumentMetrics:
    """Match events one-to-one by nearest chronological opportunity.

    Inputs are sorted by time. The two-pointer matcher maximizes the number of
    matches for a fixed tolerance and prevents one prediction matching twice.
    """
    refs = sorted(reference, key=lambda event: event.time_seconds)
    preds = sorted(predicted, key=lambda event: event.time_seconds)
    i = j = 0
    errors: list[float] = []
    while i < len(refs) and j < len(preds):
        delta = preds[j].time_seconds - refs[i].time_seconds
        if abs(delta) <= tolerance:
            errors.append(abs(delta))
            i += 1
            j += 1
        elif delta < -tolerance:
            j += 1
        else:
            i += 1

    tp = len(errors)
    fp = len(preds) - tp
    fn = len(refs) - tp
    precision = tp / (tp + fp) if tp + fp else (1.0 if fn == 0 else 0.0)
    recall = tp / (tp + fn) if tp + fn else (1.0 if fp == 0 else 0.0)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return InstrumentMetrics(
        reference_events=len(refs),
        predicted_events=len(preds),
        true_positives=tp,
        false_positives=fp,
        false_negatives=fn,
        precision=precision,
        recall=recall,
        f1=f1,
        mean_absolute_timing_error_ms=(sum(errors) / tp * 1000) if tp else None,
    )


def evaluate_performance(
    reference: list[DrumEvent],
    predicted: list[DrumEvent],
    *,
    tolerance_ms: float = 50.0,
) -> EvaluationReport:
    """Compare predicted hits to a human-annotated reference.

    Instrument identity must match exactly. Matching is one-to-one and timing
    is measured in seconds; the default acceptance window is +/-50 ms.
    """
    if not isfinite(tolerance_ms) or tolerance_ms < 0:
        raise ValueError("tolerance_ms must be a finite non-negative number")

    reference_by: dict[str, list[DrumEvent]] = defaultdict(list)
    predicted_by: dict[str, list[DrumEvent]] = defaultdict(list)
    for event in reference:
        reference_by[event.instrument.value].append(event)
    for event in predicted:
        predicted_by[event.instrument.value].append(event)

    names = sorted(set(reference_by) | set(predicted_by))
    by_instrument = {
        name: _metrics(reference_by[name], predicted_by[name], tolerance_ms / 1000)
        for name in names
    }
    overall = _metrics(reference, predicted, tolerance_ms / 1000)
    return EvaluationReport(
        tolerance_ms=tolerance_ms,
        overall=overall,
        by_instrument=by_instrument,
    )
