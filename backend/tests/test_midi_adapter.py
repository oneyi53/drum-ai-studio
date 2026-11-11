import mido
import pytest

from app.drum_events import DrumEvent, DrumInstrument, DrumPerformance, TempoChange
from app.midi_adapter import (
    gm_note_to_instrument,
    midi_to_performance,
    performance_to_midi,
)


def _write_midi(path, tracks, ticks_per_beat=480):
    midi = mido.MidiFile(ticks_per_beat=ticks_per_beat)
    for messages in tracks:
        track = mido.MidiTrack()
        track.extend(messages)
        midi.tracks.append(track)
    midi.save(path)


def test_maps_common_gm_percussion_keys_and_preserves_unknowns():
    assert gm_note_to_instrument(36) == DrumInstrument.KICK
    assert gm_note_to_instrument(38) == DrumInstrument.SNARE
    assert gm_note_to_instrument(42) == DrumInstrument.CLOSED_HIHAT
    assert gm_note_to_instrument(46) == DrumInstrument.OPEN_HIHAT
    assert gm_note_to_instrument(37) == DrumInstrument.OTHER  # Side stick
    assert gm_note_to_instrument(39) == DrumInstrument.OTHER  # Hand clap
    assert gm_note_to_instrument(99) == DrumInstrument.OTHER


def test_imports_percussion_events_velocity_and_tempo_map(tmp_path):
    path = tmp_path / "groove.mid"
    _write_midi(
        path,
        [[
            mido.Message("note_on", channel=9, note=36, velocity=110, time=0),
            mido.Message("note_off", channel=9, note=36, velocity=0, time=120),
            mido.MetaMessage("set_tempo", tempo=400_000, time=360),
            mido.Message("note_on", channel=9, note=38, velocity=88, time=480),
            mido.MetaMessage("time_signature", numerator=3, denominator=4, time=0),
        ]],
    )
    performance = midi_to_performance(path)
    assert len(performance.events) == 2
    assert performance.events[0].instrument == DrumInstrument.KICK
    assert performance.events[0].velocity == 110
    assert performance.events[0].time_seconds == pytest.approx(0)
    assert performance.events[1].instrument == DrumInstrument.SNARE
    assert performance.events[1].time_seconds == pytest.approx(0.9)
    assert performance.tempo_map[-1].bpm == pytest.approx(150)
    assert performance.tempo_map[-1].numerator == 3


def test_filters_non_percussion_channels_by_default(tmp_path):
    path = tmp_path / "channels.mid"
    _write_midi(path, [[
        mido.Message("note_on", channel=0, note=36, velocity=90, time=0),
        mido.Message("note_on", channel=9, note=36, velocity=90, time=0),
    ]])
    assert len(midi_to_performance(path).events) == 1
    assert len(midi_to_performance(path, percussion_channel_only=False).events) == 2


def test_can_drop_unmapped_keys(tmp_path):
    path = tmp_path / "unknown.mid"
    _write_midi(path, [[mido.Message("note_on", channel=9, note=99, velocity=70, time=0)]])
    assert midi_to_performance(path).events[0].instrument == DrumInstrument.OTHER
    assert midi_to_performance(path, include_unmapped_notes=False).events == []


def test_missing_file_fails_clearly(tmp_path):
    with pytest.raises(FileNotFoundError):
        midi_to_performance(tmp_path / "missing.mid")


def test_exports_canonical_events_with_tempo_and_velocity(tmp_path):
    performance = DrumPerformance(
        duration_seconds=2.0,
        tempo_map=[
            TempoChange(time_seconds=0, bpm=120, numerator=4, denominator=4),
            TempoChange(time_seconds=1, bpm=100, numerator=3, denominator=4),
        ],
        events=[
            DrumEvent(
                time_seconds=0.5,
                instrument=DrumInstrument.KICK,
                velocity=112,
                source="manual",
                manually_corrected=True,
            ),
            DrumEvent(
                time_seconds=1.4,
                instrument=DrumInstrument.OPEN_HIHAT,
                velocity=77,
                source="manual",
                manually_corrected=True,
            ),
        ],
    )
    path = performance_to_midi(performance, tmp_path / "edited.mid")
    restored = midi_to_performance(path)

    assert [event.instrument for event in restored.events] == [
        DrumInstrument.KICK,
        DrumInstrument.OPEN_HIHAT,
    ]
    assert [event.velocity for event in restored.events] == [112, 77]
    assert [event.time_seconds for event in restored.events] == pytest.approx([0.5, 1.4])
    assert restored.tempo_map[-1].bpm == pytest.approx(100)
    assert restored.tempo_map[-1].numerator == 3
    assert restored.duration_seconds == pytest.approx(2.0)
