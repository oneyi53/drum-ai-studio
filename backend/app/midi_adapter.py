"""Normalize General MIDI percussion tracks into the canonical event schema."""
from __future__ import annotations

from pathlib import Path

import mido

from .drum_events import DrumEvent, DrumInstrument, DrumPerformance, TempoChange

# General MIDI percussion key map (channel 10 / zero-based channel 9).
GM_DRUM_MAP: dict[int, DrumInstrument] = {
    35: DrumInstrument.KICK, 36: DrumInstrument.KICK,
    38: DrumInstrument.SNARE, 40: DrumInstrument.SNARE,
    42: DrumInstrument.CLOSED_HIHAT, 44: DrumInstrument.PEDAL_HIHAT,
    46: DrumInstrument.OPEN_HIHAT,
    49: DrumInstrument.CRASH, 52: DrumInstrument.CRASH,
    55: DrumInstrument.CRASH, 57: DrumInstrument.CRASH,
    51: DrumInstrument.RIDE, 53: DrumInstrument.RIDE, 59: DrumInstrument.RIDE,
    41: DrumInstrument.LOW_TOM, 43: DrumInstrument.LOW_TOM,
    45: DrumInstrument.MID_TOM, 47: DrumInstrument.MID_TOM,
    48: DrumInstrument.HIGH_TOM, 50: DrumInstrument.HIGH_TOM,
}


def gm_note_to_instrument(note: int) -> DrumInstrument:
    """Map a General MIDI percussion key; preserve unmapped hits as OTHER."""
    return GM_DRUM_MAP.get(note, DrumInstrument.OTHER)


def midi_to_performance(
    midi_path: str | Path,
    *,
    percussion_channel_only: bool = True,
    include_unmapped_notes: bool = True,
) -> DrumPerformance:
    """Read a Standard MIDI File and normalize percussion note-ons.

    MIDI note-on events with velocity zero are note-offs and are ignored.
    Times are converted to absolute seconds while applying tempo changes.
    By default only MIDI channel 10 (zero-based channel 9) is considered.
    Unmapped percussion pitches are retained as OTHER unless disabled.
    """
    path = Path(midi_path)
    if not path.is_file():
        raise FileNotFoundError(path)

    midi = mido.MidiFile(path)
    if midi.ticks_per_beat <= 0:
        raise ValueError("MIDI ticks_per_beat must be positive")

    tempo = 500_000
    numerator, denominator = 4, 4
    elapsed = 0.0
    tempo_map = [TempoChange(time_seconds=0.0, bpm=120.0, numerator=4, denominator=4)]
    events: list[DrumEvent] = []

    for message in mido.merge_tracks(midi.tracks):
        elapsed += mido.tick2second(message.time, midi.ticks_per_beat, tempo)

        if message.type == "set_tempo":
            tempo = message.tempo
            change = TempoChange(
                time_seconds=elapsed,
                bpm=60_000_000 / tempo,
                numerator=numerator,
                denominator=denominator,
            )
            if elapsed == tempo_map[-1].time_seconds:
                tempo_map[-1] = change
            else:
                tempo_map.append(change)
            continue

        if message.type == "time_signature":
            numerator = message.numerator
            denominator = message.denominator
            change = TempoChange(
                time_seconds=elapsed,
                bpm=60_000_000 / tempo,
                numerator=numerator,
                denominator=denominator,
            )
            if elapsed == tempo_map[-1].time_seconds:
                tempo_map[-1] = change
            else:
                tempo_map.append(change)
            continue

        if message.type != "note_on" or message.velocity <= 0:
            continue
        if percussion_channel_only and message.channel != 9:
            continue

        instrument = gm_note_to_instrument(message.note)
        if instrument == DrumInstrument.OTHER and not include_unmapped_notes:
            continue

        events.append(
            DrumEvent(
                time_seconds=elapsed,
                instrument=instrument,
                velocity=message.velocity,
                source="imported",
            )
        )

    # A file with no note events is still a valid empty performance if it has
    # a positive duration; preserve a non-zero duration for schema validity.
    duration = max(elapsed, max((event.time_seconds for event in events), default=0.0), 0.001)
    return DrumPerformance(
        duration_seconds=duration,
        events=events,
        tempo_map=tempo_map,
    )


# Canonical instrument to General MIDI percussion key. OTHER is represented by
# side stick (37) as a neutral fallback; source metadata remains in canonical JSON.
INSTRUMENT_TO_GM_NOTE: dict[DrumInstrument, int] = {
    DrumInstrument.KICK: 36,
    DrumInstrument.SNARE: 38,
    DrumInstrument.CLOSED_HIHAT: 42,
    DrumInstrument.OPEN_HIHAT: 46,
    DrumInstrument.PEDAL_HIHAT: 44,
    DrumInstrument.RIDE: 51,
    DrumInstrument.CRASH: 49,
    DrumInstrument.HIGH_TOM: 48,
    DrumInstrument.MID_TOM: 45,
    DrumInstrument.LOW_TOM: 41,
    DrumInstrument.OTHER: 37,
}


def performance_to_midi(
    performance: DrumPerformance,
    midi_path: str | Path,
    *,
    ticks_per_beat: int = 480,
) -> Path:
    """Write canonical events to a GM percussion MIDI file on channel 10."""
    if ticks_per_beat <= 0:
        raise ValueError("ticks_per_beat must be positive")
    destination = Path(midi_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    midi = mido.MidiFile(type=0, ticks_per_beat=ticks_per_beat)
    track = mido.MidiTrack()
    midi.tracks.append(track)

    tempo_map = performance.tempo_map or [
        TempoChange(time_seconds=0.0, bpm=120.0, numerator=4, denominator=4)
    ]
    if tempo_map[0].time_seconds > 0:
        tempo_map = [
            TempoChange(time_seconds=0.0, bpm=120.0, numerator=4, denominator=4),
            *tempo_map,
        ]

    change_ticks: list[tuple[int, TempoChange]] = []
    accumulated_ticks = 0.0
    previous_time = 0.0
    previous_tempo = 500_000
    for change in tempo_map:
        accumulated_ticks += (
            (change.time_seconds - previous_time)
            * ticks_per_beat
            * 1_000_000
            / previous_tempo
        )
        tick = round(accumulated_ticks)
        change_ticks.append((tick, change))
        previous_time = change.time_seconds
        previous_tempo = round(60_000_000 / change.bpm)

    def seconds_to_ticks(seconds: float) -> int:
        selected_tick, selected_change = change_ticks[0]
        for tick, change in change_ticks:
            if change.time_seconds > seconds:
                break
            selected_tick, selected_change = tick, change
        tempo = round(60_000_000 / selected_change.bpm)
        return selected_tick + round(
            (seconds - selected_change.time_seconds)
            * ticks_per_beat
            * 1_000_000
            / tempo
        )

    messages: list[tuple[int, int, mido.Message | mido.MetaMessage]] = []
    for tick, change in change_ticks:
        messages.append(
            (tick, 0, mido.MetaMessage("set_tempo", tempo=round(60_000_000 / change.bpm)))
        )
        messages.append(
            (
                tick,
                1,
                mido.MetaMessage(
                    "time_signature",
                    numerator=change.numerator,
                    denominator=change.denominator,
                ),
            )
        )
    for event in performance.events:
        messages.append(
            (
                seconds_to_ticks(event.time_seconds),
                2,
                mido.Message(
                    "note_on",
                    channel=9,
                    note=INSTRUMENT_TO_GM_NOTE[event.instrument],
                    velocity=event.velocity,
                ),
            )
        )
    messages.sort(key=lambda item: (item[0], item[1]))
    previous_tick = 0
    for tick, _, message in messages:
        message.time = tick - previous_tick
        track.append(message)
        previous_tick = tick
    end_tick = seconds_to_ticks(performance.duration_seconds)
    track.append(mido.MetaMessage("end_of_track", time=max(0, end_tick - previous_tick)))
    midi.save(destination)
    return destination
