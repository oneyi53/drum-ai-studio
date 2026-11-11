"""Export canonical drum performances as MusicXML partwise scores.

The exporter writes a single percussion staff with separate voices per
instrument, tempo directions, time signatures, and absolute event placement.
"""
from __future__ import annotations

from collections import defaultdict
from xml.etree import ElementTree as ET

from .drum_events import DrumInstrument, DrumPerformance, TempoChange
from .midi_adapter import INSTRUMENT_TO_GM_NOTE

DIVISIONS = 480
NOTE_DURATION = 60  # 32nd note in divisions per quarter note

DISPLAY: dict[DrumInstrument, tuple[str, int, str]] = {
    DrumInstrument.KICK: ("F", 4, "normal"),
    DrumInstrument.SNARE: ("C", 5, "normal"),
    DrumInstrument.CLOSED_HIHAT: ("G", 5, "x"),
    DrumInstrument.OPEN_HIHAT: ("G", 5, "circle-x"),
    DrumInstrument.PEDAL_HIHAT: ("E", 4, "x"),
    DrumInstrument.RIDE: ("F", 5, "x"),
    DrumInstrument.CRASH: ("A", 5, "x"),
    DrumInstrument.HIGH_TOM: ("D", 5, "normal"),
    DrumInstrument.MID_TOM: ("B", 4, "normal"),
    DrumInstrument.LOW_TOM: ("G", 4, "normal"),
    DrumInstrument.OTHER: ("C", 5, "normal"),
}


def _tempo_changes(performance: DrumPerformance) -> list[TempoChange]:
    changes = performance.tempo_map or [
        TempoChange(time_seconds=0, bpm=120, numerator=4, denominator=4)
    ]
    if changes[0].time_seconds > 0:
        changes = [
            TempoChange(time_seconds=0, bpm=120, numerator=4, denominator=4),
            *changes,
        ]
    return changes


def _seconds_to_quarters(seconds: float, changes: list[TempoChange]) -> float:
    elapsed_seconds = 0.0
    quarters = 0.0
    bpm = 120.0
    for change in changes:
        if change.time_seconds > seconds:
            break
        quarters += (change.time_seconds - elapsed_seconds) * bpm / 60.0
        elapsed_seconds = change.time_seconds
        bpm = change.bpm
    return quarters + (seconds - elapsed_seconds) * bpm / 60.0


def _add_text(
    parent: ET.Element, tag: str, value: str | int | float, **attributes: str
) -> ET.Element:
    child = ET.SubElement(parent, tag, attributes)
    child.text = str(value)
    return child


def _add_note(
    measure: ET.Element,
    instrument: DrumInstrument,
    velocity: int,
    duration: int,
    *,
    chord: bool,
) -> None:
    step, octave, notehead = DISPLAY[instrument]
    note = ET.SubElement(measure, "note")
    if chord:
        ET.SubElement(note, "chord")
    unpitched = ET.SubElement(note, "unpitched")
    _add_text(unpitched, "display-step", step)
    _add_text(unpitched, "display-octave", octave)
    ET.SubElement(note, "instrument", id=f"P1-{instrument.value}")
    _add_text(note, "duration", duration)
    _add_text(note, "voice", list(DrumInstrument).index(instrument) + 1)
    _add_text(note, "type", "32nd")
    _add_text(note, "stem", "up")
    _add_text(note, "notehead", notehead)
    play = ET.SubElement(note, "play")
    _add_text(ET.SubElement(play, "other-play", type="midi-velocity"), "value", velocity)


def performance_to_musicxml(performance: DrumPerformance) -> str:
    """Return a MusicXML 4.0 score for a canonical drum performance."""
    changes = _tempo_changes(performance)
    event_beats = [
        (event, _seconds_to_quarters(event.time_seconds, changes))
        for event in performance.events
    ]
    duration_beats = _seconds_to_quarters(performance.duration_seconds, changes)
    total_beats = max(
        duration_beats,
        max((beat + 1 / 16 for _, beat in event_beats), default=0.0),
        1 / 16,
    )

    signature_changes: list[tuple[float, int, int]] = []
    previous_signature: tuple[int, int] | None = None
    for change in changes:
        signature = (change.numerator, change.denominator)
        if signature != previous_signature:
            signature_changes.append(
                (_seconds_to_quarters(change.time_seconds, changes), *signature)
            )
            previous_signature = signature
    if not signature_changes or signature_changes[0][0] > 0:
        signature_changes.insert(0, (0.0, 4, 4))

    measures: list[tuple[float, float, int, int]] = []
    bar_start = 0.0
    while bar_start < total_beats - 1e-9:
        active = max(
            (item for item in signature_changes if item[0] <= bar_start + 1e-9),
            key=lambda item: item[0],
            default=(0.0, 4, 4),
        )
        numerator, denominator = active[1], active[2]
        bar_end = bar_start + numerator * 4.0 / denominator
        next_change = min(
            (item[0] for item in signature_changes if item[0] > bar_start + 1e-9),
            default=bar_end,
        )
        if next_change < bar_end:
            bar_end = next_change
        if bar_end <= bar_start + 1e-9:
            bar_end = bar_start + numerator * 4.0 / denominator
        measures.append((bar_start, bar_end, numerator, denominator))
        bar_start = bar_end

    root = ET.Element(
        "score-partwise",
        version="4.0",
    )
    _add_text(root, "work-title", "DrumAI Studio Drum Score")
    identification = ET.SubElement(root, "identification")
    _add_text(identification, "creator", "DrumAI Studio", type="composer")
    part_list = ET.SubElement(root, "part-list")
    score_part = ET.SubElement(part_list, "score-part", id="P1")
    _add_text(score_part, "part-name", "Drum Set")
    _add_text(score_part, "part-abbreviation", "Drs.")
    for instrument in DrumInstrument:
        instrument_id = f"P1-{instrument.value}"
        score_instrument = ET.SubElement(
            score_part, "score-instrument", id=instrument_id
        )
        _add_text(score_instrument, "instrument-name", instrument.value.replace("_", " ").title())
        midi_instrument = ET.SubElement(score_part, "midi-instrument", id=instrument_id)
        _add_text(midi_instrument, "midi-channel", 10)
        _add_text(midi_instrument, "midi-unpitched", INSTRUMENT_TO_GM_NOTE[instrument] + 1)
        _add_text(midi_instrument, "volume", 80)
        _add_text(midi_instrument, "pan", 0)

    part = ET.SubElement(root, "part", id="P1")
    ordered_events = sorted(event_beats, key=lambda item: (item[1], item[0].instrument.value))
    for measure_number, (start, end, numerator, denominator) in enumerate(measures, 1):
        measure = ET.SubElement(part, "measure", number=str(measure_number))
        attributes = ET.SubElement(measure, "attributes")
        _add_text(attributes, "divisions", DIVISIONS)
        time = ET.SubElement(attributes, "time")
        _add_text(time, "beats", numerator)
        _add_text(time, "beat-type", denominator)
        clef = ET.SubElement(attributes, "clef")
        _add_text(clef, "sign", "percussion")
        _add_text(clef, "line", 2)
        staff_details = ET.SubElement(attributes, "staff-details")
        _add_text(staff_details, "staff-lines", 5)

        for change in changes:
            beat = _seconds_to_quarters(change.time_seconds, changes)
            if start - 1e-9 <= beat < end - 1e-9:
                direction = ET.SubElement(measure, "direction", placement="above")
                direction_type = ET.SubElement(direction, "direction-type")
                metronome = ET.SubElement(direction_type, "metronome")
                _add_text(metronome, "beat-unit", "quarter")
                _add_text(metronome, "per-minute", f"{change.bpm:g}")
                _add_text(direction, "offset", round((beat - start) * DIVISIONS))
                sound = ET.SubElement(direction, "sound")
                sound.set("tempo", f"{change.bpm:g}")

        in_measure = [
            (event, beat)
            for event, beat in ordered_events
            if start - 1e-9 <= beat < end - 1e-9
        ]
        by_instrument: dict[DrumInstrument, list[tuple[object, float]]] = defaultdict(list)
        for event, beat in in_measure:
            by_instrument[event.instrument].append((event, beat))

        voice_number = 0
        for instrument in DrumInstrument:
            notes = by_instrument.get(instrument, [])
            if not notes:
                continue
            voice_number += 1
            if voice_number > 1:
                backup = ET.SubElement(measure, "backup")
                _add_text(backup, "duration", cursor)
            cursor = 0
            index = 0
            while index < len(notes):
                event, beat = notes[index]
                onset = max(0, round((beat - start) * DIVISIONS))
                if onset > cursor:
                    forward = ET.SubElement(measure, "forward")
                    _add_text(forward, "duration", onset - cursor)
                    cursor = onset
                group = []
                while index < len(notes) and round((notes[index][1] - start) * DIVISIONS) == onset:
                    group.append(notes[index][0])
                    index += 1
                next_onset = (
                    round((notes[index][1] - start) * DIVISIONS)
                    if index < len(notes)
                    else round((end - start) * DIVISIONS)
                )
                note_duration = max(1, min(NOTE_DURATION, next_onset - onset))
                for chord_index, grouped_event in enumerate(group):
                    _add_note(
                        measure,
                        instrument,
                        grouped_event.velocity,
                        note_duration,
                        chord=chord_index > 0,
                    )
                cursor = onset + note_duration

    ET.indent(root, space="  ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(
        root, encoding="unicode"
    ) + "\n"
