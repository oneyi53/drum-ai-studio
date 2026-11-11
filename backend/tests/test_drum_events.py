import pytest
from pydantic import ValidationError

from app.drum_events import (
    DrumEvent,
    DrumInstrument,
    DrumPerformance,
    TempoChange,
    evaluate_performance,
)


def event(time: float, instrument: DrumInstrument = DrumInstrument.KICK) -> DrumEvent:
    return DrumEvent(time_seconds=time, instrument=instrument)


def test_performance_accepts_events_and_tempo_changes():
    performance = DrumPerformance(
        duration_seconds=4,
        events=[event(0.5), event(1.0, DrumInstrument.SNARE)],
        tempo_map=[TempoChange(time_seconds=0, bpm=120), TempoChange(time_seconds=2, bpm=90)],
    )
    assert performance.schema_version == "1.0"
    assert len(performance.events) == 2


def test_event_cannot_exceed_duration():
    with pytest.raises(ValidationError):
        DrumPerformance(duration_seconds=1, events=[event(1.1)])


def test_tempo_map_must_be_strictly_ordered():
    with pytest.raises(ValidationError):
        DrumPerformance(
            duration_seconds=4,
            tempo_map=[TempoChange(time_seconds=2, bpm=100), TempoChange(time_seconds=1, bpm=120)],
        )


def test_evaluator_matches_one_to_one_with_timing_tolerance():
    reference = [event(1.0), event(2.0), event(3.0, DrumInstrument.SNARE)]
    predicted = [
        event(1.02),
        event(2.20),
        event(3.03, DrumInstrument.SNARE),
        event(4.0),
    ]
    report = evaluate_performance(reference, predicted, tolerance_ms=50)
    assert report.overall.true_positives == 2
    assert report.overall.false_positives == 2
    assert report.overall.false_negatives == 1
    assert report.overall.precision == pytest.approx(0.5)
    assert report.overall.recall == pytest.approx(2 / 3)
    assert report.by_instrument["snare"].f1 == pytest.approx(1.0)


def test_empty_inputs_are_perfect_and_invalid_tolerance_rejected():
    assert evaluate_performance([], []).overall.f1 == 1.0
    with pytest.raises(ValueError):
        evaluate_performance([], [], tolerance_ms=-1)


def test_event_rejects_non_finite_time():
    with pytest.raises(ValidationError):
        event(float("inf"))
