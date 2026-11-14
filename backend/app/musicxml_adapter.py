"""Export canonical drum performances as MusicXML partwise scores.

The exporter writes a single percussion staff with separate voices per
instrument, tempo directions, time signatures, and absolute event placement.
"""
from __future__ import annotations

from bisect import bisect_right
from collections import defaultdict
from fractions import Fraction
from math import gcd
from xml.etree import ElementTree as ET

from .drum_events import DrumInstrument, DrumPerformance, TempoChange
from .midi_adapter import INSTRUMENT_TO_GM_NOTE

DIVISIONS = 480
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
    dots: int = 0,
    actual_notes: int = 1,
    normal_notes: int = 1,
    ties: tuple[str, ...] = (),
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
    # Per the MusicXML schema, <tie> (sound) follows <duration> and
    # precedes <voice>; <tied> (notation) lives in <notations>, which
    # follows <notehead> and precedes <play>.
    for tie_type in ties:
        ET.SubElement(note, "tie", type=tie_type)
    _add_text(note, "voice", list(DrumInstrument).index(instrument) + 1)
    _add_text(note, "type", note_type)
    for _ in range(dots):
        ET.SubElement(note, "dot")
    if actual_notes != normal_notes:
        modification = ET.SubElement(note, "time-modification")
        _add_text(modification, "actual-notes", actual_notes)
        _add_text(modification, "normal-notes", normal_notes)
    _add_text(note, "stem", "up")
    _add_text(note, "notehead", notehead)
    if ties:
        notations = ET.SubElement(note, "notations")
        for tie_type in ties:
            ET.SubElement(notations, "tied", type=tie_type)
    play = ET.SubElement(note, "play")
    midi_velocity = ET.SubElement(play, "other-play", type="midi-velocity")
    midi_velocity.text = str(velocity)


def _add_rest(
    measure: ET.Element,
    voice_number: int,
    duration: int,
    note_type: str,
    dots: int = 0,
) -> None:
    note = ET.SubElement(measure, "note")
    ET.SubElement(note, "rest")
    _add_text(note, "duration", duration)
    _add_text(note, "voice", voice_number)
    _add_text(note, "type", note_type)
    for _ in range(dots):
        ET.SubElement(note, "dot")


def _rhythmic_note_values(
    divisions: int = DIVISIONS,
) -> list[tuple[int, str, int]]:
    if divisions <= 0:
        raise ValueError("divisions must be positive")
    values: list[tuple[int, str, int]] = []
    for note_type, quarter_length in _NOTE_TYPE_QUARTERS.items():
        for dots in range(3):
            factor = Fraction(2 ** (dots + 1) - 1, 2**dots)
            duration = Fraction(divisions) * quarter_length * factor
            if duration.denominator == 1 and duration > 0:
                values.append((duration.numerator, note_type, dots))
    return sorted(set(values), key=lambda item: (item[0], -item[2]), reverse=True)


def decompose_rhythmic_duration(
    duration: int, divisions: int = DIVISIONS
) -> list[tuple[int, str, int]]:
    """Express an exact duration as the fewest standard/dotted note values."""
    if duration <= 0:
        raise ValueError("duration must be a positive integer")
    candidates = _rhythmic_note_values(divisions)
    best: list[list[tuple[int, str, int]] | None] = [None] * (duration + 1)
    best[0] = []
    for amount in range(1, duration + 1):
        options = [
            best[amount - value[0]] + [value]
            for value in candidates
            if value[0] <= amount and best[amount - value[0]] is not None
        ]
        if options:
            best[amount] = min(
                options,
                key=lambda parts: (
                    len(parts),
                    sum(item[2] for item in parts),
                    tuple(-item[0] for item in parts),
                ),
            )
    if best[duration] is None:
        raise ValueError(
            f"duration {duration} cannot be represented at divisions={divisions}; "
            "quantize the performance or correct the event timing before export"
        )
    return best[duration]


def _beat_group_boundaries(
    numerator: int, denominator: int, divisions: int = DIVISIONS
) -> list[int]:
    """Tick boundaries of the beat groups inside one measure.

    Beat groups are the units beaming (and meter-aware rest decomposition)
    must not cross: half measures in 4/4, dotted-quarter pulses in compound
    meters, the 3+2+2 eighth groups in 7/8, and one beat unit elsewhere.
    The returned list starts at 0 and ends at the bar length in ticks.
    """
    if numerator <= 0 or denominator <= 0 or divisions <= 0:
        raise ValueError("meter values and divisions must be positive")
    denominator_unit_numerator = divisions * 4
    if denominator_unit_numerator % denominator:
        raise ValueError("meter denominator does not produce an integral duration")
    denominator_unit = denominator_unit_numerator // denominator
    bar_length = numerator * denominator_unit

    if denominator == 8 and numerator == 7:
        return [0, 3 * denominator_unit, 5 * denominator_unit, bar_length]
    if denominator == 8 and numerator > 3 and numerator % 3 == 0:
        group_size = 3 * denominator_unit
    elif numerator == 4 and denominator == 4:
        group_size = 2 * divisions
    else:
        group_size = denominator_unit
    return list(range(0, bar_length + 1, group_size))


def decompose_meter_aware_gap(
    start: int,
    end: int,
    numerator: int,
    denominator: int,
    divisions: int = DIVISIONS,
) -> list[tuple[int, str, int]]:
    """Split a silent interval at meter-group boundaries before spelling rests."""
    if start < 0 or end < start:
        raise ValueError("gap must have a non-negative start and end after start")
    if end == start:
        return []
    boundaries = _beat_group_boundaries(numerator, denominator, divisions)
    bar_length = boundaries[-1]

    result: list[tuple[int, str, int]] = []
    position = start
    while position < end:
        bar_position = position % bar_length
        next_boundary = next(
            (boundary for boundary in boundaries if boundary > bar_position),
            bar_length,
        )
        chunk_end = min(end, position + next_boundary - bar_position)
        result.extend(decompose_rhythmic_duration(chunk_end - position, divisions))
        position = chunk_end
    return result


def _choose_hit_duration(
    gap: int, divisions: int = DIVISIONS
) -> tuple[int, str, int, int, int]:
    """Choose one standard hit value, using a small tuplet below 1/128th."""
    if gap <= 0:
        raise ValueError("consecutive hits must have a positive time gap")
    candidates = [
        value for value in _rhythmic_note_values(divisions)
        if value[0] <= min(gap, divisions)
    ]
    if candidates:
        duration, note_type, dots = candidates[0]
        return duration, note_type, dots, 1, 1

    # At this resolution, sub-128th gaps are represented as an exact tuplet
    # rather than stretching a hit beyond the next onset.
    smallest_type = "128th"
    smallest_ticks = Fraction(divisions, 32)
    if smallest_ticks.denominator != 1:
        raise ValueError(
            f"divisions={divisions} cannot represent a positive sub-128th hit"
        )
    gcd_value = gcd(smallest_ticks.numerator, gap)
    actual_notes = smallest_ticks.numerator // gcd_value
    normal_notes = gap // gcd_value
    return gap, smallest_type, 0, actual_notes, normal_notes


def _tie_markers(position: int, total: int) -> tuple[str, ...]:
    """Tie types for one fragment of a tie chain, by position in the chain.

    The first fragment starts the tie, the last stops it, and a middle
    fragment both stops the previous one and starts the next. A chain
    needs at least two fragments (one on each side of the barline).
    """
    if total < 2:
        raise ValueError("a tie chain needs at least two fragments")
    if position == 0:
        return ("start",)
    if position == total - 1:
        return ("stop",)
    return ("stop", "start")


#: (duration, type, dots) fragments on each side of a barline tie split.
TieFragments = tuple[list[tuple[int, str, int]], list[tuple[int, str, int]]]


def _split_duration_at_barline(
    duration: int, first_segment: int, divisions: int = DIVISIONS
) -> TieFragments | None:
    """Split a note duration at the barline into tied fragments, or None.

    Both sides must decompose into exact standard/dotted note values;
    when either side is not exactly representable the caller keeps the
    old truncated duration instead of emitting an inexact tie, so total
    duration is always conserved by the returned fragments.
    """
    if first_segment <= 0 or first_segment >= duration:
        return None
    try:
        first = decompose_rhythmic_duration(first_segment, divisions)
        second = decompose_rhythmic_duration(duration - first_segment, divisions)
    except ValueError:
        return None
    return first, second


def _next_voice_beat(beats: list[float], beat: float) -> float | None:
    """Next hit beat in a voice after the given beat, or None."""
    index = bisect_right(beats, beat)
    return beats[index] if index < len(beats) else None


_BEAM_LEVELS = {
    "eighth": 1,
    "16th": 2,
    "32nd": 3,
    "64th": 4,
    "128th": 5,
    "256th": 6,
    "512th": 7,
    "1024th": 8,
}


def _beam_level(note_type: str | None) -> int | None:
    """Beam depth for a note type, or None when the note is never beamed."""
    if note_type is None:
        return None
    return _BEAM_LEVELS.get(note_type)


def _insert_beams(note_element: ET.Element, beams: list[tuple[int, str]]) -> None:
    """Insert <beam> children before <notations> or <play>, in MusicXML note order.

    In a <note>, beams sit after stem/notehead and before notations/play.
    The exporter always writes <play> last, so inserting before it keeps
    the schema order without re-serializing the whole note; tied notes
    carry <notations>, which beams must precede.
    """
    anchor = _musicxml_child(note_element, "notations")
    if anchor is None:
        anchor = _musicxml_child(note_element, "play")
    index = list(note_element).index(anchor) if anchor is not None else len(note_element)
    for offset, (number, value) in enumerate(beams):
        beam = ET.Element("beam", {"number": str(number)})
        beam.text = value
        note_element.insert(index + offset, beam)


def _beat_group_index(boundaries: list[int], onset_ticks: Fraction) -> int:
    """Index of the beat group containing an onset given in ticks."""
    for index in range(len(boundaries) - 1):
        if boundaries[index] <= onset_ticks < boundaries[index + 1]:
            return index
    return len(boundaries) - 2


def _secondary_beam_value(
    group: list[tuple[dict[str, object], int]], position: int, beam_level: int
) -> str | None:
    """Beam value at one secondary level, or None when the note has no such beam."""
    _, level = group[position]
    if level < beam_level:
        return None
    # Maximal run of notes at this level (or deeper) containing this note.
    # The level-1 group is contiguous by construction, so a run only splits
    # where a longer note intervenes.
    start = position
    while start > 0:
        previous_record, previous_level = group[start - 1]
        record, _ = group[start]
        if previous_level < beam_level:
            break
        if Fraction(record["onset"]) != Fraction(previous_record["offset_end"]):
            break
        start -= 1
    end = position
    while end + 1 < len(group):
        record, _ = group[end]
        next_record, next_level = group[end + 1]
        if next_level < beam_level:
            break
        if Fraction(next_record["onset"]) != Fraction(record["offset_end"]):
            break
        end += 1
    if end > start:
        if position == start:
            return "begin"
        if position == end:
            return "end"
        return "continue"
    # Lone secondary beam: a hook pointing toward the rest of the group.
    return "backward hook" if position == len(group) - 1 else "forward hook"


def _beam_voice_stream(
    records: list[dict[str, object]],
    boundaries: list[int],
    divisions: int,
) -> None:
    """Add <beam> elements to one voice stream in one measure.

    Beam groups are maximal runs of beamable notes (eighth or shorter,
    no tuplets) that are contiguous in time and stay inside one beat
    group. Rests, forwards, tuplets, and longer notes break a run; a
    single-note run is left unbeamed (flagged). Secondary beams break at
    each eighth-note unit; a lone secondary beam becomes a hook.
    """
    candidates: list[tuple[dict[str, object], int]] = []
    for record in sorted(records, key=lambda item: (item["onset"], bool(item["is_chord"]))):
        if record["is_chord"] or record["is_rest"]:
            continue
        element = record["element"]
        level = _beam_level(element.findtext("type"))
        if level is None:
            continue
        # The MusicXML schema caps <beam> at 6 per note; deeper values keep
        # their flags instead of emitting an invalid seventh beam.
        if level > 6:
            continue
        if _musicxml_child(element, "time-modification") is not None:
            continue
        candidates.append((record, level))

    groups: list[list[tuple[dict[str, object], int]]] = []
    previous_end: Fraction | None = None
    previous_group: int | None = None
    for candidate in candidates:
        record, _ = candidate
        onset_ticks = Fraction(record["onset"]) * divisions
        group_index = _beat_group_index(boundaries, onset_ticks)
        if (
            groups
            and previous_end is not None
            and onset_ticks == previous_end
            and group_index == previous_group
        ):
            groups[-1].append(candidate)
        else:
            groups.append([candidate])
        previous_end = Fraction(record["offset_end"]) * divisions
        previous_group = group_index

    for group in groups:
        if len(group) < 2:
            continue
        max_level = max(level for _, level in group)
        for position, (record, _level) in enumerate(group):
            if position == 0:
                beams: list[tuple[int, str]] = [(1, "begin")]
            elif position == len(group) - 1:
                beams = [(1, "end")]
            else:
                beams = [(1, "continue")]
            for beam_level in range(2, max_level + 1):
                value = _secondary_beam_value(group, position, beam_level)
                if value is not None:
                    beams.append((beam_level, value))
            _insert_beams(record["element"], beams)


def _apply_beams(part: ET.Element) -> None:
    """Add <beam> elements to every measure in a built <part>.

    Runs on the finished MusicXML tree via the same shared-cursor
    reconstruction the validator uses, so beam groups are computed from
    absolute onsets per voice — never from per-voice iteration order.
    """
    effective_divisions = DIVISIONS
    effective_time: tuple[int, int] | None = None
    for measure in _musicxml_children(part, "measure"):
        result = reconstruct_and_validate_measure(
            measure, time_sig=effective_time, divisions=effective_divisions
        )
        effective_divisions = int(result["divisions"])
        effective_time = result["time_signature"]
        boundaries = _beat_group_boundaries(*effective_time, effective_divisions)
        for stream in result["voice_events"].values():
            _beam_voice_stream(stream, boundaries, effective_divisions)


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
    # Per-voice hit beats across the whole performance, for the cross-measure
    # gap a barline-crossing hit needs. Ties are decided at fragment-generation
    # time (when the hit duration is chosen), never by patching the tree.
    voice_beats: dict[DrumInstrument, list[float]] = defaultdict(list)
    for event, beat in event_beats:
        voice_beats[event.instrument].append(beat)
    for beats in voice_beats.values():
        beats.sort()
    # Continuation fragments a tied hit leaves for the next measure, keyed by
    # voice: (velocity, [(duration, type, dots, tie markers), ...]).
    pending_ties: dict[DrumInstrument, tuple[int, list[tuple[int, str, int, tuple[str, ...]]]]] = {}
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
            continuation = pending_ties.pop(instrument, None)
            if not notes and continuation is None:
                continue
            voice_number += 1
            instrument_voice = list(DrumInstrument).index(instrument) + 1
            if voice_number > 1:
                if cursor != measure_duration:
                    raise ValueError(
                        f"voice {instrument_voice} ended at {cursor}, expected {measure_duration}"
                    )
                backup = ET.SubElement(measure, "backup")
                _add_text(backup, "duration", cursor)
            cursor = 0
            if continuation is not None:
                # A tied hit from the previous measure continues here at
                # onset 0; the hit loop below fills any gap to the next hit.
                velocity, fragments = continuation
                for frag_duration, frag_type, frag_dots, frag_ties in fragments:
                    _add_note(
                        measure,
                        instrument,
                        velocity,
                        frag_duration,
                        frag_type,
                        chord=False,
                        dots=frag_dots,
                        ties=frag_ties,
                    )
                    cursor += frag_duration
            index = 0
            while index < len(notes):
                event, beat = notes[index]
                onset = max(0, round((beat - start) * DIVISIONS))
                if onset >= measure_duration:
                    # A hit rounding onto (or past) the barline has no
                    # position inside this measure: emitting it would
                    # leave a zero gap for _choose_hit_duration and
                    # fail the whole export, so skip it.
                    index += 1
                    continue
                if onset > cursor:
                    try:
                        leading_rests = decompose_meter_aware_gap(
                            cursor, onset, numerator, denominator, DIVISIONS
                        )
                    except ValueError:
                        forward = ET.SubElement(measure, "forward")
                        _add_text(forward, "duration", onset - cursor)
                        cursor = onset
                    else:
                        for rest_duration, rest_type, rest_dots in leading_rests:
                            _add_rest(
                                measure, instrument_voice, rest_duration, rest_type, rest_dots
                            )
                            cursor += rest_duration

                group = []
                while index < len(notes) and round((notes[index][1] - start) * DIVISIONS) == onset:
                    group.append(notes[index][0])
                    index += 1

                has_next_hit = index < len(notes)
                if has_next_hit:
                    next_onset = round((notes[index][1] - start) * DIVISIONS)
                else:
                    # Last hit of this voice in the measure: the gap runs to
                    # the next hit of the same voice anywhere, so a duration
                    # chosen from it may cross the barline (and be tied).
                    # The group is beat-ordered, so the last member's beat
                    # is the right lookup point for "after this group".
                    group_end_beat = notes[index - 1][1]
                    next_beat = _next_voice_beat(voice_beats[instrument], group_end_beat)
                    next_onset = (
                        round((next_beat - start) * DIVISIONS)
                        if next_beat is not None
                        else measure_duration
                    )
                available_gap = next_onset - onset
                (
                    note_duration,
                    note_type,
                    note_dots,
                    actual_notes,
                    normal_notes,
                ) = _choose_hit_duration(available_gap, DIVISIONS)
                tie_split: TieFragments | None = None
                if (
                    not has_next_hit
                    and next_onset > measure_duration
                    and onset + note_duration > measure_duration
                ):
                    tie_split = _split_duration_at_barline(
                        note_duration, measure_duration - onset, DIVISIONS
                    )
                    if tie_split is None:
                        # Either side is not exactly representable: keep the
                        # old truncated duration instead of an inexact tie.
                        (
                            note_duration,
                            note_type,
                            note_dots,
                            actual_notes,
                            normal_notes,
                        ) = _choose_hit_duration(measure_duration - onset, DIVISIONS)
                if tie_split is not None:
                    first_fragments, second_fragments = tie_split
                    all_fragments = first_fragments + second_fragments
                    for frag_index, (frag_duration, frag_type, frag_dots) in enumerate(
                        first_fragments
                    ):
                        frag_ties = _tie_markers(frag_index, len(all_fragments))
                        for chord_index, grouped_event in enumerate(group):
                            # Only the parent pitch is tied; chord tones end
                            # at the barline, as with beaming (parent only).
                            _add_note(
                                measure,
                                instrument,
                                grouped_event.velocity,
                                frag_duration,
                                frag_type,
                                chord=chord_index > 0,
                                dots=frag_dots,
                                ties=frag_ties if chord_index == 0 else (),
                            )
                    cursor = measure_duration
                    pending_ties[instrument] = (
                        group[0].velocity,
                        [
                            (
                                frag_duration,
                                frag_type,
                                frag_dots,
                                _tie_markers(
                                    len(first_fragments) + frag_index,
                                    len(all_fragments),
                                ),
                            )
                            for frag_index, (frag_duration, frag_type, frag_dots) in enumerate(
                                second_fragments
                            )
                        ],
                    )
                else:
                    for chord_index, grouped_event in enumerate(group):
                        _add_note(
                            measure,
                            instrument,
                            grouped_event.velocity,
                            note_duration,
                            note_type,
                            chord=chord_index > 0,
                            dots=note_dots,
                            actual_notes=actual_notes,
                            normal_notes=normal_notes,
                        )
                    cursor = onset + note_duration

                if has_next_hit:
                    if cursor < next_onset:
                        try:
                            gap_rests = decompose_meter_aware_gap(
                                cursor, next_onset, numerator, denominator, DIVISIONS
                            )
                        except ValueError:
                            forward = ET.SubElement(measure, "forward")
                            _add_text(forward, "duration", next_onset - cursor)
                            cursor = next_onset
                        else:
                            for rest_duration, rest_type, rest_dots in gap_rests:
                                _add_rest(
                                    measure, instrument_voice, rest_duration, rest_type, rest_dots
                                )
                                cursor += rest_duration
                elif cursor < measure_duration:
                    forward = ET.SubElement(measure, "forward")
                    _add_text(forward, "duration", measure_duration - cursor)
                    cursor = measure_duration

            if cursor < measure_duration:
                forward = ET.SubElement(measure, "forward")
                _add_text(forward, "duration", measure_duration - cursor)
                cursor = measure_duration

    if pending_ties:
        raise ValueError(
            "tied continuations were never emitted: "
            + ", ".join(sorted(item.value for item in pending_ties))
        )

    _apply_beams(part)

    ET.indent(root, space="  ")
    xml_text = '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(
        root, encoding="unicode"
    ) + "\n"
    reconstruct_and_validate_musicxml(xml_text, validate_notation=True)
    return xml_text


def _musicxml_local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _musicxml_child(parent: ET.Element, name: str) -> ET.Element | None:
    return next((item for item in parent if _musicxml_local_name(item.tag) == name), None)


def _musicxml_children(parent: ET.Element, name: str) -> list[ET.Element]:
    return [item for item in parent if _musicxml_local_name(item.tag) == name]


_NOTE_TYPE_QUARTERS = {
    "maxima": Fraction(32),
    "long": Fraction(16),
    "breve": Fraction(8),
    "whole": Fraction(4),
    "half": Fraction(2),
    "quarter": Fraction(1),
    "eighth": Fraction(1, 2),
    "16th": Fraction(1, 4),
    "32nd": Fraction(1, 8),
    "64th": Fraction(1, 16),
    "128th": Fraction(1, 32),
    "256th": Fraction(1, 64),
    "512th": Fraction(1, 128),
    "1024th": Fraction(1, 256),
}


def validate_note_notation(
    note_elem: ET.Element, divisions: int = DIVISIONS
) -> dict[str, object]:
    """Check that MusicXML duration matches type, dots, and tuplet ratio."""
    if divisions <= 0:
        raise ValueError("divisions must be positive")

    duration_elem = _musicxml_child(note_elem, "duration")
    type_elem = _musicxml_child(note_elem, "type")
    if duration_elem is None or not duration_elem.text:
        raise ValueError("note/duration must be present")
    if type_elem is None or not type_elem.text:
        raise ValueError("note/type must be present")

    try:
        duration_units = int(duration_elem.text.strip())
    except ValueError as exc:
        raise ValueError("note/duration must be an integer") from exc
    if duration_units <= 0:
        raise ValueError("note/duration must be positive")

    note_type = type_elem.text.strip()
    if note_type not in _NOTE_TYPE_QUARTERS:
        raise ValueError(f"unsupported MusicXML note type: {note_type}")
    dots = len(_musicxml_children(note_elem, "dot"))
    base_duration = _NOTE_TYPE_QUARTERS[note_type]
    dotted_factor = Fraction(2 ** (dots + 1) - 1, 2**dots)
    notated_duration = base_duration * dotted_factor

    time_modification = _musicxml_child(note_elem, "time-modification")
    actual_notes = normal_notes = 1
    if time_modification is not None:
        actual_elem = _musicxml_child(time_modification, "actual-notes")
        normal_elem = _musicxml_child(time_modification, "normal-notes")
        if actual_elem is None or normal_elem is None:
            raise ValueError("time-modification requires actual-notes and normal-notes")
        try:
            actual_notes = int(actual_elem.text or "")
            normal_notes = int(normal_elem.text or "")
        except ValueError as exc:
            raise ValueError("tuplet note counts must be integers") from exc
        if actual_notes <= 0 or normal_notes <= 0:
            raise ValueError("tuplet note counts must be positive")

    expected_duration = notated_duration * Fraction(normal_notes, actual_notes)
    actual_duration = Fraction(duration_units, divisions)
    if actual_duration != expected_duration:
        raise ValueError(
            f"note duration/type mismatch: duration={actual_duration} quarters, "
            f"type={note_type}, dots={dots}, tuplet={normal_notes}:{actual_notes} "
            f"implies {expected_duration} quarters"
        )
    return {
        "duration_quarters": actual_duration,
        "type": note_type,
        "dots": dots,
        "actual_notes": actual_notes,
        "normal_notes": normal_notes,
    }


def reconstruct_and_validate_measure(
    measure_elem: ET.Element,
    time_sig: tuple[int, int] | None = None,
    divisions: int = DIVISIONS,
    validate_notation: bool = False,
) -> dict[str, object]:
    """Reconstruct one MusicXML measure with its document-order shared cursor.

    Returned onset/duration values are Fractions measured in quarter notes,
    so a divisions change inside a measure cannot corrupt the reconstructed
    timeline. Voice identity is scoped by both staff and voice.
    """
    if divisions <= 0:
        raise ValueError("divisions must be positive")

    effective_divisions = divisions
    effective_time = time_sig or (4, 4)
    cursor = Fraction(0)
    max_cursor = Fraction(0)
    records: list[dict[str, object]] = []
    last_note: dict[str, object] | None = None

    def parse_positive_integer(element: ET.Element | None, label: str) -> int:
        if element is None or element.text is None:
            raise ValueError(f"{label} must contain an integer")
        try:
            value = int(element.text.strip())
        except ValueError as exc:
            raise ValueError(f"{label} must contain an integer") from exc
        if value <= 0:
            raise ValueError(f"{label} must be positive")
        return value

    for child in measure_elem:
        child_name = _musicxml_local_name(child.tag)
        if child_name == "attributes":
            div_elem = _musicxml_child(child, "divisions")
            if div_elem is not None:
                effective_divisions = parse_positive_integer(
                    div_elem, "attributes/divisions"
                )
            time_elem = _musicxml_child(child, "time")
            if time_elem is not None:
                beats_elem = _musicxml_child(time_elem, "beats")
                beat_type_elem = _musicxml_child(time_elem, "beat-type")
                beats_text = beats_elem.text.strip() if beats_elem is not None and beats_elem.text else ""
                try:
                    numerator = sum(int(part) for part in beats_text.split("+"))
                    denominator = parse_positive_integer(
                        beat_type_elem, "time/beat-type"
                    )
                except ValueError as exc:
                    raise ValueError("invalid time signature") from exc
                if not beats_text or numerator <= 0:
                    raise ValueError("time/beats must contain positive additive groups")
                effective_time = (numerator, denominator)
            continue

        if child_name in {"backup", "forward"}:
            raw_duration = parse_positive_integer(
                _musicxml_child(child, "duration"), f"{child_name}/duration"
            )
            movement = Fraction(raw_duration, effective_divisions)
            if child_name == "backup":
                cursor -= movement
                if cursor < 0:
                    raise ValueError(
                        f"backup underflow: shared cursor became {cursor}"
                    )
            else:
                cursor += movement
                max_cursor = max(max_cursor, cursor)
            last_note = None
            continue

        if child_name != "note":
            continue

        duration_units = parse_positive_integer(
            _musicxml_child(child, "duration"), "note/duration"
        )
        duration = Fraction(duration_units, effective_divisions)
        if validate_notation:
            validate_note_notation(child, effective_divisions)
        voice_elem, staff_elem = _musicxml_child(child, "voice"), _musicxml_child(child, "staff")
        voice = (
            voice_elem.text.strip()
            if voice_elem is not None and voice_elem.text
            else "1"
        )
        staff = (
            staff_elem.text.strip()
            if staff_elem is not None and staff_elem.text
            else "1"
        )
        is_chord = _musicxml_child(child, "chord") is not None
        is_rest = _musicxml_child(child, "rest") is not None
        if is_chord and is_rest:
            raise ValueError("a chord tone cannot also be a rest")

        if is_chord:
            if last_note is None:
                raise ValueError("chord tone has no preceding non-chord note")
            if last_note["is_rest"]:
                raise ValueError("a rest cannot be the parent of a chord tone")
            if last_note["voice"] != voice or last_note["staff"] != staff:
                raise ValueError("chord tone voice/staff does not match its parent")
            if last_note["duration"] != duration:
                raise ValueError("chord tone duration does not match its parent")
            onset = last_note["onset"]
        else:
            onset = cursor

        record: dict[str, object] = {
            "element": child,
            "onset": onset,
            "duration": duration,
            "offset_end": onset + duration,
            "is_chord": is_chord,
            "is_rest": is_rest,
            "voice": voice,
            "staff": staff,
        }
        records.append(record)

        if not is_chord:
            last_note = record
            cursor += duration
            max_cursor = max(max_cursor, cursor)

    numerator, denominator = effective_time
    if numerator <= 0 or denominator <= 0:
        raise ValueError(f"invalid time signature: {effective_time}")
    capacity = Fraction(numerator * 4, denominator)

    streams: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for record in records:
        streams[(str(record["staff"]), str(record["voice"]))].append(record)

    voice_gaps: dict[tuple[str, str], list[tuple[Fraction, Fraction]]] = {}
    for (staff, voice), events in streams.items():
        ordered = sorted(
            events,
            key=lambda event: (
                event["onset"],
                bool(event["is_chord"]),
            ),
        )
        previous_onset: Fraction | None = None
        previous_end = Fraction(0)
        occupied: list[tuple[Fraction, Fraction]] = []

        for event in ordered:
            onset = event["onset"]
            end = event["offset_end"]
            if event["is_chord"]:
                if onset != previous_onset:
                    raise ValueError(
                        f"chord onset mismatch in staff {staff}, voice {voice}"
                    )
                continue
            if onset < previous_end:
                raise ValueError(
                    f"overlapping events in staff {staff}, voice {voice} at {onset}"
                )
            if end > capacity:
                stream_detail = [
                    (item["onset"], item["duration"], item["is_rest"], item["is_chord"])
                    for item in ordered
                ]
                raise ValueError(
                    f"staff {staff}, voice {voice} overflow: "
                    f"extent {end} exceeds capacity {capacity}; events={stream_detail}"
                )
            previous_onset = onset
            previous_end = end
            occupied.append((onset, end))

        gaps: list[tuple[Fraction, Fraction]] = []
        position = Fraction(0)
        for onset, end in occupied:
            if onset > position:
                gaps.append((position, onset))
            position = max(position, end)
        if position < capacity:
            gaps.append((position, capacity))
        voice_gaps[(staff, voice)] = gaps

    if max_cursor > capacity:
        raise ValueError(
            f"measure cursor overflow: extent {max_cursor} exceeds capacity {capacity}"
        )

    return {
        "expected_capacity": capacity,
        "divisions": effective_divisions,
        "time_signature": effective_time,
        "max_cursor": max_cursor,
        "voice_events": dict(streams),
        "voice_gaps": voice_gaps,
        "implicit": measure_elem.get("implicit") == "yes",
    }


def reconstruct_and_validate_musicxml(
    xml_text: str, *, validate_notation: bool = False
) -> list[dict[str, object]]:
    """Validate every measure in a score-partwise MusicXML document."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise ValueError(f"invalid MusicXML: {exc}") from exc
    if _musicxml_local_name(root.tag) != "score-partwise":
        raise ValueError("MusicXML root must be score-partwise")

    results: list[dict[str, object]] = []
    for part_index, part in enumerate(_musicxml_children(root, "part"), start=1):
        effective_divisions = DIVISIONS
        effective_time: tuple[int, int] | None = None
        for measure_index, measure in enumerate(_musicxml_children(part, "measure"), start=1):
            result = reconstruct_and_validate_measure(
                measure,
                time_sig=effective_time,
                divisions=effective_divisions,
                validate_notation=validate_notation,
            )
            effective_divisions = int(result["divisions"])
            effective_time = result["time_signature"]
            results.append({
                "part": part.get("id") or str(part_index),
                "measure": measure.get("number") or str(measure_index),
                **result,
            })
    if not results:
        raise ValueError("MusicXML contains no part measures")
    return results
