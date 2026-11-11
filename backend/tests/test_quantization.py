import pytest

from app.drum_events import DrumEvent, DrumInstrument, DrumPerformance, TempoChange
from app.quantization import quantize_performance


def make_performance():
    return DrumPerformance(
        duration_seconds=5,
        events=[
            DrumEvent(time_seconds=0.61, instrument=DrumInstrument.KICK, velocity=111),
            DrumEvent(time_seconds=1.12, instrument=DrumInstrument.SNARE),
            DrumEvent(time_seconds=2.2, instrument=DrumInstrument.CLOSED_HIHAT),
        ],
        tempo_map=[
            TempoChange(time_seconds=0, bpm=120, numerator=4, denominator=4),
            TempoChange(time_seconds=2, bpm=60, numerator=3, denominator=4),
        ],
    )


def test_quantize_quarter_note_grid_at_full_strength():
    result = quantize_performance(make_performance(), subdivision="1/4")
    assert result.events[0].time_seconds == pytest.approx(0.5)
    assert result.events[1].time_seconds == pytest.approx(1.0)
    assert result.events[2].time_seconds == pytest.approx(2.0)


def test_quantize_strength_interpolates_without_changing_event_metadata():
    original = make_performance()
    result = quantize_performance(original, subdivision="1/4", strength=50)
    assert result.events[0].time_seconds == pytest.approx(0.555)
    assert result.events[0].velocity == 111
    assert result.events[0].id == original.events[0].id
    assert result.events[0].instrument == DrumInstrument.KICK


def test_zero_strength_is_noop_and_does_not_mutate_input():
    original = make_performance()
    result = quantize_performance(original, strength=0)
    assert result.events[0].time_seconds == original.events[0].time_seconds
    assert original.events[0].time_seconds == 0.61


@pytest.mark.parametrize("subdivision", ["1/4", "1/8", "1/16", "1/32"])
def test_all_supported_subdivisions_are_available(subdivision):
    result = quantize_performance(make_performance(), subdivision=subdivision)
    assert len(result.events) == 3


@pytest.mark.parametrize("strength", [-1, 101, float("inf")])
def test_invalid_strength_is_rejected(strength):
    with pytest.raises(ValueError):
        quantize_performance(make_performance(), strength=strength)


def test_invalid_subdivision_is_rejected():
    with pytest.raises(ValueError):
        quantize_performance(make_performance(), subdivision="1/64")
