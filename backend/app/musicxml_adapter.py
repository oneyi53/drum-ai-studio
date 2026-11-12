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
NOTE_VALUES = (
    (DIVISIONS, "quarter"),
    (DIVISIONS // 2, "eighth"),
    (DIVISIONS // 4, "16th"),
    (DIVISIONS // 8, "32nd"),
    (DIVISIONS // 16, "64th"),
    (DIVISIONS // 32, "128th"),
)

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
    parent: ET.Element, tag: str, value: str | float, **attributes: str
) -> ET.Element:
    child = ET.SubElement(parent, tag, attributes)
    child.text = str(value)
    return child


def _add_note(
    measure: ET.Element,
    instrument: DrumInstrument,
    velocity: int,
    duration: int,
    note_type: str,
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
    _add_text(note, "type", note_type)
    _add_text(note, "stem", "up")
    _add_text(note, "notehead", notehead)
    play = ET.SubElement(note, "play")
    midi_velocity = ET.SubElement(play, "other-play", type="midi-velocity")
    midi_velocity.text = str(velocity)


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
        bar_end = min(bar_end, next_change, total_beats)
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
        measure_attributes = {"number": str(measure_number)}
        nominal_measure_beats = numerator * 4.0 / denominator
        if end - start < nominal_measure_beats - 1e-9:
            measure_attributes["implicit"] = "yes"
        measure = ET.SubElement(part, "measure", measure_attributes)
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
        measure_duration = round((end - start) * DIVISIONS)
        cursor = 0
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
                available_gap = max(1, next_onset - onset)
                note_duration, note_type = next(
                    ((duration, kind) for duration, kind in NOTE_VALUES if duration <= available_gap),
                    (1, "128th"),
                )
                note_duration = min(note_duration, available_gap)
                for chord_index, grouped_event in enumerate(group):
                    _add_note(
                        measure,
                        instrument,
                        grouped_event.velocity,
                        note_duration,
                        note_type,
                        chord=chord_index > 0,
                    )
                cursor = onset + note_duration
            if cursor < measure_duration:
                forward = ET.SubElement(measure, "forward")
                _add_text(forward, "duration", measure_duration - cursor)
                cursor = measure_duration

    ET.indent(root, space="  ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(
        root, encoding="unicode"
    ) + "\n"


def reconstruct_and_validate_measure(
    measure_elem: ET.Element,
    time_sig: tuple[int, int] | None = None,
    divisions: int = DIVISIONS,
) -> dict[str, object]:
    """Reconstruct absolute note intervals using MusicXML shared-cursor semantics."""
    if divisions <= 0:
        raise ValueError("divisions must be a positive integer")
    effective_divisions = divisions
    effective_time = time_sig
    for child in measure_elem:
        if child.tag != "attributes":
            continue
        div_elem = child.find("divisions")
        if div_elem is not None:
            if not div_elem.text:
                raise ValueError("attributes/divisions must contain an integer")
            effective_divisions = int(div_elem.text)
            if effective_divisions <= 0:
                raise ValueError("attributes/divisions must be positive")
        time_elem = child.find("time")
        if time_elem is not None:
            beats_elem, beat_type_elem = time_elem.find("beats"), time_elem.find("beat-type")
            if beats_elem is None or not beats_elem.text or beat_type_elem is None or not beat_type_elem.text:
                raise ValueError("time signature requires beats and beat-type")
            effective_time = (int(beats_elem.text), int(beat_type_elem.text))
    if effective_time is None:
        effective_time = (4, 4)
    beats, beat_type = effective_time
    if beats <= 0 or beat_type <= 0:
        raise ValueError(f"invalid time signature: {effective_time}")
    numerator = effective_divisions * 4
    if numerator % beat_type:
        raise ValueError(f"non-integral beat unit at divisions={effective_divisions}, beat-type={beat_type}")
    expected_capacity = beats * (numerator // beat_type)

    cursor = 0
    max_cursor = 0
    records: list[dict[str, object]] = []
    last_non_chord: dict[str, object] | None = None
    for child in measure_elem:
        if child.tag in {"backup", "forward"}:
            duration_elem = child.find("duration")
            if duration_elem is None or not duration_elem.text:
                raise ValueError(f"{child.tag} element missing duration")
            duration = int(duration_elem.text)
            if duration <= 0:
                raise ValueError(f"{child.tag} duration must be positive")
            if child.tag == "backup":
                cursor -= duration
                if cursor < 0:
                    raise ValueError(f"backup underflow: shared cursor became {cursor}")
            else:
                cursor += duration
                max_cursor = max(max_cursor, cursor)
            last_non_chord = None
            continue
        if child.tag != "note":
            continue
        duration_elem = child.find("duration")
        if duration_elem is None or not duration_elem.text:
            raise ValueError("note is missing duration; grace notes are unsupported")
        duration = int(duration_elem.text)
        if duration <= 0:
            raise ValueError(f"note duration must be positive, got {duration}")
        voice_elem, staff_elem = child.find("voice"), child.find("staff")
        voice = voice_elem.text.strip() if voice_elem is not None and voice_elem.text else "1"
        staff = staff_elem.text.strip() if staff_elem is not None and staff_elem.text else "1"
        is_chord, is_rest = child.find("chord") is not None, child.find("rest") is not None
        if is_chord:
            if last_non_chord is None:
                raise ValueError("chord tone has no preceding non-chord note")
            if last_non_chord["voice"] != voice or last_non_chord["staff"] != staff:
                raise ValueError("chord tone voice/staff does not match its parent")
            onset = int(last_non_chord["onset"])
        else:
            onset = cursor
        record: dict[str, object] = {
            "element": child, "onset": onset, "duration": duration,
            "offset_end": onset + duration, "is_chord": is_chord,
            "is_rest": is_rest, "voice": voice, "staff": staff,
        }
        records.append(record)
        if not is_chord:
            last_non_chord = record
            cursor += duration
            max_cursor = max(max_cursor, cursor)

    voice_events: dict[str, list[dict[str, object]]] = defaultdict(list)
    for record in records:
        voice_events[str(record["voice"])].append(record)
    for voice, events in voice_events.items():
        ordered = sorted(events, key=lambda event: (int(event["onset"]), bool(event["is_chord"])))
        previous_end = previous_onset = -1
        for event in ordered:
            onset, end = int(event["onset"]), int(event["offset_end"])
            if not event["is_chord"] and onset < previous_end:
                raise ValueError(f"overlapping non-chord events in voice {voice} at {onset}")
            if event["is_chord"] and onset != previous_onset:
                raise ValueError(f"chord onset mismatch in voice {voice} at {onset}")
            if not event["is_chord"]:
                previous_onset, previous_end = onset, end
        extent = max((int(event["offset_end"]) for event in events), default=0)
        if extent > expected_capacity:
            raise ValueError(f"voice {voice} overflow: extent {extent} exceeds capacity {expected_capacity}")
    if max_cursor > expected_capacity:
        raise ValueError(f"measure cursor overflow: extent {max_cursor} exceeds capacity {expected_capacity}")
    return {
        "expected_capacity": expected_capacity, "divisions": effective_divisions,
        "time_signature": effective_time, "max_cursor": max_cursor,
        "voice_events": dict(voice_events),
    }
