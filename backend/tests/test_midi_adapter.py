import mido
import pytest

from app.drum_events import DrumEvent, DrumInstrument, DrumPerformance, TempoChange
from app.midi_adapter import (
    gm_note_to_instrument,
    midi_to_performance,
    performance_to_midi,
    rewrite_midi_tempo,
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


def test_import_collapses_exact_duplicate_note_ons(tmp_path):
    path = tmp_path / "dups.mid"
    _write_midi(
        path,
        [[
            mido.Message("note_on", channel=9, note=38, velocity=100, time=0),
            mido.Message("note_on", channel=9, note=38, velocity=100, time=0),
            mido.Message("note_on", channel=9, note=38, velocity=100, time=480),
            mido.Message("note_on", channel=9, note=36, velocity=100, time=0),
        ]],
    )
    performance = midi_to_performance(path)
    # Two identical snares at tick 0 collapse to one; the snare at tick 480
    # and the kick at the same instant as the second snare are kept.
    assert [(event.instrument, event.time_seconds) for event in performance.events] == [
        (DrumInstrument.SNARE, pytest.approx(0)),
        (DrumInstrument.SNARE, pytest.approx(0.5)),
        (DrumInstrument.KICK, pytest.approx(0.5)),
    ]


def test_export_writes_each_pitch_tick_once(tmp_path):
    performance = DrumPerformance(
        duration_seconds=2.0,
        tempo_map=[TempoChange(time_seconds=0, bpm=120, numerator=4, denominator=4)],
        events=[
            DrumEvent(time_seconds=0.5, instrument=DrumInstrument.KICK, velocity=110),
            DrumEvent(time_seconds=0.5, instrument=DrumInstrument.KICK, velocity=110),
            # 0.5 ms later: quantizes to the same tick at 480 ppq / 120 BPM.
            DrumEvent(time_seconds=0.5005, instrument=DrumInstrument.KICK, velocity=110),
            DrumEvent(time_seconds=0.5, instrument=DrumInstrument.SNARE, velocity=90),
        ],
    )
    path = performance_to_midi(performance, tmp_path / "dedup.mid")
    restored = midi_to_performance(path)
    assert [(event.instrument, event.time_seconds) for event in restored.events] == [
        (DrumInstrument.KICK, pytest.approx(0.5)),
        (DrumInstrument.SNARE, pytest.approx(0.5)),
    ]


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


def _write_drumscript_like_midi(path, stock_bpm=69.8, ticks_per_beat=220):
    """Upstream-shaped MIDI: type 1, conductor track + note track.

    One kick at 1.0 s (0.2 s long) and one snare at 2.0 s (0.1 s long),
    laid out on the stock tempo grid like DrumScript's own output.
    """
    ticks_per_second = ticks_per_beat * stock_bpm / 60.0
    midi = mido.MidiFile(type=1, ticks_per_beat=ticks_per_beat)
    conductor = mido.MidiTrack()
    conductor.append(
        mido.MetaMessage("set_tempo", tempo=round(60_000_000 / stock_bpm), time=0)
    )
    conductor.append(
        mido.MetaMessage(
            "time_signature", numerator=4, denominator=4, time=0
        )
    )
    conductor.append(mido.MetaMessage("end_of_track", time=1))
    midi.tracks.append(conductor)
    notes = mido.MidiTrack()
    notes.append(mido.MetaMessage("track_name", name="DrumScript Output", time=0))
    notes.append(mido.Message("program_change", channel=9, program=0, time=0))
    notes.append(
        mido.Message(
            "note_on", channel=9, note=36, velocity=100,
            time=round(1.0 * ticks_per_second),
        )
    )
    notes.append(
        mido.Message(
            "note_on", channel=9, note=36, velocity=0,
            time=round(0.2 * ticks_per_second),
        )
    )
    notes.append(
        mido.Message(
            "note_on", channel=9, note=38, velocity=90,
            time=round(0.8 * ticks_per_second),
        )
    )
    notes.append(
        mido.Message(
            "note_on", channel=9, note=38, velocity=0,
            time=round(0.1 * ticks_per_second),
        )
    )
    notes.append(mido.MetaMessage("end_of_track", time=0))
    midi.tracks.append(notes)
    midi.save(path)
    return path


def _absolute_notes(path):
    """(note, start_seconds, duration_seconds) for every note on/off pair."""
    midi = mido.MidiFile(path)
    tempo = 500_000
    elapsed = 0.0
    starts: dict[tuple[int, int], float] = {}
    notes: list[tuple[int, float, float]] = []
    for message in mido.merge_tracks(midi.tracks):
        elapsed += mido.tick2second(message.time, midi.ticks_per_beat, tempo)
        if message.type == "set_tempo":
            tempo = message.tempo
            continue
        if message.type != "note_on":
            continue
        key = (message.channel, message.note)
        if message.velocity > 0:
            starts[key] = elapsed
        elif key in starts:
            start = starts.pop(key)
            notes.append((message.note, start, elapsed - start))
    return notes


def test_rewrite_midi_tempo_applies_corrected_tempo_preserving_absolute_times(tmp_path):
    source = _write_drumscript_like_midi(tmp_path / "stock.mid")
    destination = tmp_path / "corrected.mid"
    rewrite_midi_tempo(
        source,
        destination,
        [TempoChange(time_seconds=0, bpm=142.86, numerator=4, denominator=4)],
    )

    rewritten = mido.MidiFile(destination)
    assert rewritten.type == 1
    assert rewritten.ticks_per_beat == 220
    assert len(rewritten.tracks) == 2
    tempos = [
        60_000_000 / message.tempo
        for track in rewritten.tracks
        for message in track
        if message.type == "set_tempo"
    ]
    assert tempos == pytest.approx([142.86])
    # Cosmetic upstream content survives the rewrite.
    assert any(
        message.type == "track_name" and message.name == "DrumScript Output"
        for track in rewritten.tracks
        for message in track
    )
    assert any(
        message.type == "program_change"
        for track in rewritten.tracks
        for message in track
    )
    # Notes keep their absolute times and durations under the new tempo.
    # (220 tpq at 69.8 BPM cannot represent 1.0 s exactly, so compare
    # with tick-rounding tolerance rather than exact equality.)
    notes = _absolute_notes(destination)
    assert [note for note, _, _ in notes] == [36, 38]
    assert [start for _, start, _ in notes] == pytest.approx([1.0, 2.0], abs=0.01)
    assert [duration for _, _, duration in notes] == pytest.approx(
        [0.2, 0.1], abs=0.01
    )
    restored = midi_to_performance(destination)
    assert [event.time_seconds for event in restored.events] == pytest.approx(
        [1.0, 2.0], abs=0.01
    )
    assert restored.tempo_map[0].bpm == pytest.approx(142.86)


def test_rewrite_midi_tempo_empty_map_copies_file_unchanged(tmp_path):
    source = _write_drumscript_like_midi(tmp_path / "stock.mid")
    destination = tmp_path / "copy.mid"
    rewrite_midi_tempo(source, destination, [])
    assert destination.read_bytes() == source.read_bytes()


def test_rewrite_midi_tempo_with_stock_map_is_a_round_trip(tmp_path):
    source = _write_drumscript_like_midi(tmp_path / "stock.mid")
    destination = tmp_path / "roundtrip.mid"
    rewrite_midi_tempo(
        source,
        destination,
        [TempoChange(time_seconds=0, bpm=69.8, numerator=4, denominator=4)],
    )
    notes = _absolute_notes(destination)
    assert [note for note, _, _ in notes] == [36, 38]
    assert [start for _, start, _ in notes] == pytest.approx([1.0, 2.0], abs=0.01)
    assert [duration for _, _, duration in notes] == pytest.approx(
        [0.2, 0.1], abs=0.01
    )
    assert [event.time_seconds for event in midi_to_performance(destination).events] == (
        pytest.approx([1.0, 2.0], abs=0.01)
    )
