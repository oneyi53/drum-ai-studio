from __future__ import annotations

from xml.etree import ElementTree as ET

from app.drum_events import DrumEvent, DrumInstrument, DrumPerformance, TempoChange
from app.musicxml_adapter import performance_to_musicxml


def test_exports_percussion_staff_with_tempo_time_signature_and_velocity():
    performance = DrumPerformance(
        duration_seconds=3.0,
        tempo_map=[
            TempoChange(time_seconds=0, bpm=120, numerator=4, denominator=4),
            TempoChange(time_seconds=1, bpm=60, numerator=3, denominator=4),
        ],
        events=[
            DrumEvent(time_seconds=0, instrument=DrumInstrument.KICK, velocity=110),
            DrumEvent(time_seconds=0.5, instrument=DrumInstrument.SNARE, velocity=92),
            DrumEvent(time_seconds=1.5, instrument=DrumInstrument.CLOSED_HIHAT, velocity=75),
            DrumEvent(time_seconds=2.0, instrument=DrumInstrument.CRASH, velocity=100),
        ],
    )

    xml = performance_to_musicxml(performance)
    root = ET.fromstring(xml)
    assert root.tag == "score-partwise"
    assert root.attrib["version"] == "4.0"
    measures = root.findall("./part/measure")
    assert len(measures) == 2
    assert [measure.get("implicit") for measure in measures] == ["yes", "yes"]
    assert root.findall(".//clef/sign")[0].text == "percussion"
    assert root.findall(".//midi-channel")[0].text == "10"
    assert [item.text for item in root.findall(".//time/beats")] == ["4", "3"]
    assert [item.text for item in root.findall(".//time/beat-type")] == ["4", "4"]
    assert len(root.findall(".//note/unpitched")) == 4
    velocities = {
        (
            note.find("instrument").get("id") if note.find("instrument") is not None else ""
        ): note.findtext("play/other-play[@type='midi-velocity']")
        for note in root.findall(".//note")
        if note.find("unpitched") is not None
    }
    assert velocities["P1-kick"] == "110"
    assert velocities["P1-snare"] == "92"
    assert [item.text for item in root.findall(".//per-minute")] == ["120", "60"]


def _voice_notes(root: ET.Element, voice: str, measure_index: int = 0) -> list[tuple]:
    """(type, is_rest, [(beam number, beam value), ...]) per note in one voice."""
    measure = root.findall("./part/measure")[measure_index]
    return [
        (
            note.findtext("type"),
            note.find("rest") is not None,
            [(beam.get("number"), beam.text) for beam in note.findall("beam")],
        )
        for note in measure.findall("note")
        if note.findtext("voice") == voice
    ]


def _hat_performance(times: list[float], duration_seconds: float = 2.0) -> DrumPerformance:
    return DrumPerformance(
        duration_seconds=duration_seconds,
        tempo_map=[TempoChange(time_seconds=0, bpm=120, numerator=4, denominator=4)],
        events=[
            DrumEvent(time_seconds=time, instrument=DrumInstrument.CLOSED_HIHAT) for time in times
        ],
    )


def _kick_performance(times: list[float], duration_seconds: float = 4.0) -> DrumPerformance:
    return DrumPerformance(
        duration_seconds=duration_seconds,
        tempo_map=[TempoChange(time_seconds=0, bpm=120, numerator=4, denominator=4)],
        events=[DrumEvent(time_seconds=time, instrument=DrumInstrument.KICK) for time in times],
    )


def _voice_ties(root: ET.Element, voice: str, measure_index: int = 0) -> list[tuple]:
    """(type, duration, is_rest, is_chord, [tie types], [tied types]) per note."""
    measure = root.findall("./part/measure")[measure_index]
    return [
        (
            note.findtext("type"),
            note.findtext("duration"),
            note.find("rest") is not None,
            note.find("chord") is not None,
            [tie.get("type") for tie in note.findall("tie")],
            [tied.get("type") for tied in note.findall("notations/tied")],
        )
        for note in measure.findall("note")
        if note.findtext("voice") == voice
    ]


def test_hit_crossing_barline_splits_into_tied_fragments():
    # 4/4 @120bpm: kick at beat 3.5, next kick at beat 4.5. The gap is one
    # quarter, so the hit is a quarter tied across the barline as 8th + 8th.
    xml = performance_to_musicxml(_kick_performance([1.75, 2.25]))
    root = ET.fromstring(xml)
    assert _voice_ties(root, "2") == [
        ("half", "960", True, False, [], []),
        ("quarter", "720", True, False, [], []),
        ("eighth", "240", False, False, ["start"], ["start"]),
    ]
    assert _voice_ties(root, "2", measure_index=1) == [
        ("eighth", "240", False, False, ["stop"], ["stop"]),
        ("quarter", "480", False, False, [], []),
    ]
    # Duration is conserved across the split (240 + 240 = one quarter), and
    # the strict validator accepts the tied output on its own.
    from app.musicxml_adapter import reconstruct_and_validate_musicxml

    reconstruct_and_validate_musicxml(xml, validate_notation=True)


def test_hit_inside_measure_gets_no_tie():
    root = ET.fromstring(performance_to_musicxml(_kick_performance([0, 0.5])))
    assert root.findall(".//tie") == []
    assert root.findall(".//tied") == []


def test_hit_ending_exactly_on_barline_gets_no_tie():
    # Kick at beat 3.0 with the next kick at beat 4.0: the quarter ends
    # exactly on the barline, so there is nothing to tie across it.
    root = ET.fromstring(performance_to_musicxml(_kick_performance([1.5, 2.0])))
    assert root.findall(".//tie") == []
    assert root.findall(".//tied") == []
    assert _voice_ties(root, "2")[2] == ("quarter", "480", False, False, [], [])


def test_unrepresentable_barline_split_falls_back_without_tie():
    # Kick at beat 3.9 with the next kick at beat 4.4: the crossing 8th
    # would leave a 48-tick first segment, which is not a standard/dotted
    # value, so the exporter keeps the old truncated duration, untied.
    root = ET.fromstring(performance_to_musicxml(_kick_performance([1.95, 2.2])))
    assert root.findall(".//tie") == []
    assert root.findall(".//tied") == []
    assert _voice_ties(root, "2") == [("64th", "45", False, False, [], [])]


def test_tied_continuation_emitted_for_voice_without_hits_in_next_measure():
    # Kick at beat 3.5, next kick at beat 8.0: the tied 8th continues into
    # measure 2 even though that voice has no hits of its own there.
    root = ET.fromstring(performance_to_musicxml(_kick_performance([1.75, 4.0], 6.0)))
    assert _voice_ties(root, "2", measure_index=1) == [
        ("eighth", "240", False, False, ["stop"], ["stop"]),
    ]


def test_multi_fragment_tie_chain_uses_stop_start_markers():
    # Kick at beat 3.375, next kick at beat 4.5: the quarter splits as
    # 8th + 32nd in measure 1 and a dotted 16th in measure 2.
    root = ET.fromstring(performance_to_musicxml(_kick_performance([1.6875, 2.25])))
    assert _voice_ties(root, "2") == [
        ("half", "960", True, False, [], []),
        ("quarter", "480", True, False, [], []),
        ("16th", "180", True, False, [], []),
        ("eighth", "240", False, False, ["start"], ["start"]),
        ("32nd", "60", False, False, ["stop", "start"], ["stop", "start"]),
    ]
    assert _voice_ties(root, "2", measure_index=1) == [
        ("16th", "180", False, False, ["stop"], ["stop"]),
        ("32nd", "60", True, False, [], []),
        ("quarter", "480", False, False, [], []),
    ]


def test_chord_tie_marks_parent_pitch_only():
    performance = DrumPerformance(
        duration_seconds=4.0,
        tempo_map=[TempoChange(time_seconds=0, bpm=120, numerator=4, denominator=4)],
        events=[
            DrumEvent(time_seconds=1.75, instrument=DrumInstrument.KICK, velocity=110),
            DrumEvent(time_seconds=1.75, instrument=DrumInstrument.KICK, velocity=80),
            DrumEvent(time_seconds=2.25, instrument=DrumInstrument.KICK),
        ],
    )
    root = ET.fromstring(performance_to_musicxml(performance))
    assert _voice_ties(root, "2") == [
        ("half", "960", True, False, [], []),
        ("quarter", "720", True, False, [], []),
        ("eighth", "240", False, False, ["start"], ["start"]),
        ("eighth", "240", False, True, [], []),
    ]
    assert _voice_ties(root, "2", measure_index=1) == [
        ("eighth", "240", False, False, ["stop"], ["stop"]),
        ("quarter", "480", False, False, [], []),
    ]


def test_note_children_follow_xsd_element_order():
    # MusicXML XSD note complexType (musicxml.xsd): full-note
    # (chord?, pitch|unpitched|rest), duration, tie*, instrument?,
    # editorial-voice (voice), type?, dot*, time-modification?, stem?,
    # notehead?, beam*, notations*. <play> is excluded here: it is not in
    # the schema at all, a separate pre-existing issue.
    xsd_order = [
        "chord",
        "pitch",
        "unpitched",
        "rest",
        "duration",
        "tie",
        "instrument",
        "footnote",
        "level",
        "voice",
        "type",
        "dot",
        "accidental",
        "time-modification",
        "stem",
        "notehead",
        "staff",
        "beam",
        "notations",
        "lyric",
    ]
    performance = DrumPerformance(
        duration_seconds=4.0,
        tempo_map=[TempoChange(time_seconds=0, bpm=120, numerator=4, denominator=4)],
        events=[
            DrumEvent(time_seconds=0, instrument=DrumInstrument.CLOSED_HIHAT),
            DrumEvent(time_seconds=0.25, instrument=DrumInstrument.CLOSED_HIHAT),
            DrumEvent(time_seconds=0.5, instrument=DrumInstrument.CLOSED_HIHAT),
            DrumEvent(time_seconds=0.75, instrument=DrumInstrument.CLOSED_HIHAT),
            DrumEvent(time_seconds=1.75, instrument=DrumInstrument.KICK, velocity=110),
            DrumEvent(time_seconds=1.75, instrument=DrumInstrument.KICK, velocity=80),
            DrumEvent(time_seconds=2.25, instrument=DrumInstrument.KICK),
        ],
    )
    root = ET.fromstring(performance_to_musicxml(performance))
    notes = root.findall("./part/measure/note")
    assert notes
    assert any(note.find("chord") is not None for note in notes)
    assert any(note.find("tie") is not None for note in notes)
    assert any(note.find("rest") is not None for note in notes)
    assert any(note.findall("beam") for note in notes)
    for note in notes:
        tags = [child.tag for child in note if child.tag != "play"]
        positions = [xsd_order.index(tag) for tag in tags]
        assert positions == sorted(positions), tags
        if "instrument" in tags:
            assert tags.index("instrument") > tags.index("duration")
            assert all(tags.index("instrument") > i for i, tag in enumerate(tags) if tag == "tie")
        if note.find("rest") is not None:
            assert tags[:2] == ["rest", "duration"]


def test_tied_score_renders_with_verovio():
    from io import BytesIO

    from pypdf import PdfReader

    from app.pdf_adapter import _render_with_verovio

    pdf = _render_with_verovio(_kick_performance([1.75, 2.25]), "Tied score")
    assert len(pdf) > 0
    assert len(PdfReader(BytesIO(pdf)).pages) == 1


def test_eighth_notes_beam_within_one_beat_group():
    root = ET.fromstring(performance_to_musicxml(_hat_performance([0, 0.25, 0.5, 0.75, 1.0])))
    assert _voice_notes(root, "1") == [
        ("eighth", False, [("1", "begin")]),
        ("eighth", False, [("1", "continue")]),
        ("eighth", False, [("1", "continue")]),
        ("eighth", False, [("1", "end")]),
        ("quarter", False, []),
    ]


def test_sixteenth_notes_beam_with_second_beam():
    root = ET.fromstring(performance_to_musicxml(_hat_performance([0, 0.125, 0.25, 0.375, 0.5])))
    assert _voice_notes(root, "1") == [
        ("16th", False, [("1", "begin"), ("2", "begin")]),
        ("16th", False, [("1", "continue"), ("2", "continue")]),
        ("16th", False, [("1", "continue"), ("2", "continue")]),
        ("16th", False, [("1", "end"), ("2", "end")]),
        ("quarter", False, []),
    ]


def test_beam_does_not_cross_rest():
    root = ET.fromstring(performance_to_musicxml(_hat_performance([0, 0.25, 0.5, 1.25, 1.5, 1.75])))
    assert _voice_notes(root, "1") == [
        ("eighth", False, [("1", "begin")]),
        ("eighth", False, [("1", "end")]),
        ("quarter", False, []),
        ("eighth", True, []),
        ("eighth", False, [("1", "begin")]),
        ("eighth", False, [("1", "continue")]),
        ("eighth", False, [("1", "end")]),
    ]


def test_beam_does_not_cross_beat_group_boundary():
    root = ET.fromstring(performance_to_musicxml(_hat_performance([0.5, 0.75, 1.0, 1.25])))
    assert _voice_notes(root, "1") == [
        ("quarter", True, []),
        ("eighth", False, [("1", "begin")]),
        ("eighth", False, [("1", "end")]),
        ("eighth", False, []),
        ("quarter", False, []),
    ]


def test_beam_does_not_cross_barline():
    root = ET.fromstring(
        performance_to_musicxml(_hat_performance([1.5, 1.75, 2.0, 2.25, 2.5], duration_seconds=4.0))
    )
    assert _voice_notes(root, "1", measure_index=0) == [
        ("half", True, []),
        ("quarter", True, []),
        ("eighth", False, [("1", "begin")]),
        ("eighth", False, [("1", "end")]),
    ]
    assert _voice_notes(root, "1", measure_index=1) == [
        ("eighth", False, [("1", "begin")]),
        ("eighth", False, [("1", "end")]),
        ("quarter", False, []),
    ]


def test_lone_sixteenth_gets_secondary_beam_hook():
    forward = ET.fromstring(performance_to_musicxml(_hat_performance([0, 0.125, 0.5])))
    assert _voice_notes(forward, "1") == [
        ("16th", False, [("1", "begin"), ("2", "forward hook")]),
        ("eighth", False, [("1", "end")]),
        ("quarter", False, []),
    ]
    backward = ET.fromstring(performance_to_musicxml(_hat_performance([0, 0.375, 0.5])))
    assert _voice_notes(backward, "1") == [
        ("eighth", False, [("1", "begin")]),
        ("16th", False, [("1", "end"), ("2", "backward hook")]),
        ("quarter", False, []),
    ]


def test_meter_aware_rest_decomposition_preserves_7_8_grouping():
    from app.musicxml_adapter import decompose_meter_aware_gap

    assert decompose_meter_aware_gap(0, 1680, 7, 8, divisions=480) == [
        (720, "quarter", 1),
        (480, "quarter", 0),
        (480, "quarter", 0),
    ]


def test_exports_empty_performance_as_valid_one_measure_score():
    performance = DrumPerformance(duration_seconds=0.5, events=[])
    root = ET.fromstring(performance_to_musicxml(performance))
    assert len(root.findall("./part/measure")) == 1
    assert root.find("./part/measure").get("implicit") == "yes"
    assert root.findall(".//note") == []


def test_engraves_note_values_from_spacing_between_repeated_hits():
    performance = DrumPerformance(
        duration_seconds=1.0,
        events=[
            DrumEvent(time_seconds=0, instrument=DrumInstrument.KICK),
            DrumEvent(time_seconds=0.25, instrument=DrumInstrument.KICK),
        ],
    )
    root = ET.fromstring(performance_to_musicxml(performance))
    assert [item.text for item in root.findall(".//note/type")] == ["eighth", "quarter"]


def test_sparse_kick_voice_emits_explicit_rest_between_hits():
    performance = DrumPerformance(
        duration_seconds=2.0,
        tempo_map=[TempoChange(time_seconds=0, bpm=120, numerator=4, denominator=4)],
        events=[
            DrumEvent(time_seconds=0, instrument=DrumInstrument.KICK),
            DrumEvent(time_seconds=1.0, instrument=DrumInstrument.KICK),
        ],
    )
    root = ET.fromstring(performance_to_musicxml(performance))
    voice_notes = [
        note for note in root.findall(".//measure/note") if note.findtext("voice") == "2"
    ]
    assert [note.find("rest") is not None for note in voice_notes] == [False, True, False]
    assert [note.findtext("type") for note in voice_notes] == ["quarter", "quarter", "quarter"]
    assert [note.findtext("duration") for note in voice_notes] == ["480", "480", "480"]


def test_hit_rounding_onto_barline_is_skipped_instead_of_failing_export():
    # 4/4 @120bpm: one measure is 2s = 960 ticks. A hit at 1.9999999s
    # rounds to exactly measure_duration; without the barline guard
    # _choose_hit_duration sees a zero gap and the whole export fails.
    performance = DrumPerformance(
        duration_seconds=2.0,
        tempo_map=[TempoChange(time_seconds=0, bpm=120, numerator=4, denominator=4)],
        events=[
            DrumEvent(time_seconds=0, instrument=DrumInstrument.KICK),
            DrumEvent(time_seconds=1.9999999, instrument=DrumInstrument.KICK),
        ],
    )
    root = ET.fromstring(performance_to_musicxml(performance))
    first_measure = root.findall("./part/measure")[0]
    voice_notes = [note for note in first_measure.findall("note") if note.findtext("voice") == "2"]
    # The barline hit emits nothing; the gap to the barline is filled
    # with explicit rests (quarter + half = the rest of the measure).
    assert [note.find("rest") is not None for note in voice_notes] == [False, True, True]
    assert [note.findtext("type") for note in voice_notes] == ["quarter", "quarter", "half"]
    assert [note.findtext("duration") for note in voice_notes] == ["480", "480", "960"]


def test_meter_aware_rest_decomposition_preserves_6_8_grouping():
    from app.musicxml_adapter import decompose_meter_aware_gap

    assert decompose_meter_aware_gap(480, 1440, 6, 8, divisions=480) == [
        (240, "eighth", 0),
        (720, "quarter", 1),
    ]


def test_musicxml_export_preserves_irregular_internal_gap_with_forward_skip():
    performance = DrumPerformance(
        duration_seconds=1.0,
        tempo_map=[TempoChange(time_seconds=0, bpm=120, numerator=4, denominator=4)],
        events=[
            DrumEvent(time_seconds=0, instrument=DrumInstrument.KICK),
            DrumEvent(time_seconds=0.15, instrument=DrumInstrument.KICK),
        ],
    )
    root = ET.fromstring(performance_to_musicxml(performance))
    assert any(forward.findtext("duration") == "24" for forward in root.findall(".//forward"))


def test_sparse_voice_uses_three_four_meter_boundaries():
    performance = DrumPerformance(
        duration_seconds=1.5,
        tempo_map=[TempoChange(time_seconds=0, bpm=120, numerator=3, denominator=4)],
        events=[
            DrumEvent(time_seconds=0, instrument=DrumInstrument.KICK),
            DrumEvent(time_seconds=1.0, instrument=DrumInstrument.KICK),
        ],
    )
    root = ET.fromstring(performance_to_musicxml(performance))
    voice_notes = [
        note for note in root.findall(".//measure/note") if note.findtext("voice") == "2"
    ]
    assert [note.find("rest") is not None for note in voice_notes] == [False, True, False]
    assert [note.findtext("duration") for note in voice_notes] == ["480", "480", "480"]


def test_sparse_voice_uses_six_eight_dotted_quarter_pulse():
    performance = DrumPerformance(
        duration_seconds=1.5,
        tempo_map=[TempoChange(time_seconds=0, bpm=120, numerator=6, denominator=8)],
        events=[
            DrumEvent(time_seconds=0, instrument=DrumInstrument.KICK),
            DrumEvent(time_seconds=0.75, instrument=DrumInstrument.KICK),
        ],
    )
    root = ET.fromstring(performance_to_musicxml(performance))
    voice_notes = [
        note for note in root.findall(".//measure/note") if note.findtext("voice") == "2"
    ]
    assert [note.find("rest") is not None for note in voice_notes] == [False, True, False]
    assert [note.findtext("type") for note in voice_notes] == ["quarter", "eighth", "quarter"]


def test_sub_128th_hit_uses_exact_tuplet_duration():
    performance = DrumPerformance(
        duration_seconds=1.0,
        tempo_map=[TempoChange(time_seconds=0, bpm=120, numerator=4, denominator=4)],
        events=[
            DrumEvent(time_seconds=0, instrument=DrumInstrument.KICK),
            DrumEvent(time_seconds=0.001, instrument=DrumInstrument.KICK),
        ],
    )
    root = ET.fromstring(performance_to_musicxml(performance))
    kick_notes = [
        note
        for note in root.findall(".//measure/note")
        if note.findtext("voice") == "2" and note.find("rest") is None
    ]
    assert kick_notes[0].findtext("duration") == "1"
    assert kick_notes[0].findtext("type") == "128th"
    assert kick_notes[0].findtext("time-modification/actual-notes") == "15"
    assert kick_notes[0].findtext("time-modification/normal-notes") == "1"


def test_attributes_appear_only_in_first_measure():
    # Two 4/4 bars, no meter change: divisions, time, clef and staff
    # lines belong in measure 1 only; measure 2 carries no <attributes>.
    root = ET.fromstring(performance_to_musicxml(_kick_performance([0, 2.0])))
    measures = root.findall("./part/measure")
    assert len(measures) == 2
    assert len(root.findall(".//time")) == 1
    assert len(root.findall(".//attributes/divisions")) == 1
    assert len(root.findall(".//clef")) == 1
    assert len(root.findall(".//staff-details")) == 1
    assert measures[1].find("attributes") is None


def test_time_signature_reappears_only_on_meter_change():
    performance = DrumPerformance(
        duration_seconds=3.0,
        tempo_map=[
            TempoChange(time_seconds=0, bpm=120, numerator=4, denominator=4),
            TempoChange(time_seconds=1, bpm=60, numerator=3, denominator=4),
        ],
        events=[
            DrumEvent(time_seconds=0, instrument=DrumInstrument.KICK, velocity=110),
            DrumEvent(time_seconds=0.5, instrument=DrumInstrument.SNARE, velocity=92),
            DrumEvent(time_seconds=1.5, instrument=DrumInstrument.CLOSED_HIHAT, velocity=75),
            DrumEvent(time_seconds=2.0, instrument=DrumInstrument.CRASH, velocity=100),
        ],
    )
    root = ET.fromstring(performance_to_musicxml(performance))
    assert [item.text for item in root.findall(".//time/beats")] == ["4", "3"]
    first_attributes = root.findall("./part/measure")[0].find("attributes")
    assert [child.tag for child in first_attributes] == [
        "divisions",
        "time",
        "clef",
        "staff-details",
    ]
    second_attributes = root.findall("./part/measure")[1].find("attributes")
    assert [child.tag for child in second_attributes] == ["time"]


def test_tempo_rounds_to_one_decimal():
    performance = DrumPerformance(
        duration_seconds=2.0,
        tempo_map=[TempoChange(time_seconds=0, bpm=61.5234, numerator=4, denominator=4)],
        events=[DrumEvent(time_seconds=0, instrument=DrumInstrument.KICK)],
    )
    root = ET.fromstring(performance_to_musicxml(performance))
    assert [item.text for item in root.findall(".//per-minute")] == ["61.5"]
    assert [sound.get("tempo") for sound in root.findall(".//sound")] == ["61.5"]


def test_two_voice_layout_hands_up_feet_down():
    performance = DrumPerformance(
        duration_seconds=2.0,
        tempo_map=[TempoChange(time_seconds=0, bpm=120, numerator=4, denominator=4)],
        events=[
            DrumEvent(time_seconds=0, instrument=DrumInstrument.KICK),
            DrumEvent(time_seconds=0, instrument=DrumInstrument.CLOSED_HIHAT),
            DrumEvent(time_seconds=0.5, instrument=DrumInstrument.SNARE),
            DrumEvent(time_seconds=1.0, instrument=DrumInstrument.PEDAL_HIHAT),
            DrumEvent(time_seconds=1.5, instrument=DrumInstrument.CRASH),
        ],
    )
    root = ET.fromstring(performance_to_musicxml(performance))
    notes = root.findall("./part/measure/note")
    assert {note.findtext("voice") for note in notes} == {"1", "2"}
    for note in notes:
        if note.find("rest") is not None:
            continue
        instrument_elem = note.find("instrument")
        instrument_id = (
            instrument_elem.get("id") if instrument_elem is not None else ""
        ).removeprefix("P1-")
        if instrument_id in {"kick", "pedal_hihat"}:
            assert note.findtext("voice") == "2"
            assert note.findtext("stem") == "down"
        else:
            assert note.findtext("voice") == "1"
            assert note.findtext("stem") == "up"
    # Each voice spells its own rests; no third voice exists.
    rests = [note for note in notes if note.find("rest") is not None]
    assert {note.findtext("voice") for note in rests} == {"1", "2"}


def test_display_positions_follow_weinberg_pas_layout():
    events = [
        DrumEvent(time_seconds=step * 0.25, instrument=instrument)
        for step, instrument in enumerate(DrumInstrument)
    ]
    performance = DrumPerformance(
        duration_seconds=4.0,
        tempo_map=[TempoChange(time_seconds=0, bpm=120, numerator=4, denominator=4)],
        events=events,
    )
    root = ET.fromstring(performance_to_musicxml(performance))
    positions = {}
    for note in root.findall(".//note"):
        unpitched = note.find("unpitched")
        if unpitched is None:
            continue
        instrument_elem = note.find("instrument")
        instrument_id = (
            instrument_elem.get("id") if instrument_elem is not None else ""
        ).removeprefix("P1-")
        positions[instrument_id] = (
            unpitched.findtext("display-step"),
            unpitched.findtext("display-octave"),
        )
    assert positions == {
        "kick": ("F", "4"),
        "snare": ("C", "5"),
        "closed_hihat": ("G", "5"),
        "open_hihat": ("G", "5"),
        "pedal_hihat": ("D", "4"),
        "ride": ("F", "5"),
        "crash": ("A", "5"),
        "high_tom": ("E", "5"),
        "mid_tom": ("B", "4"),
        # Low floor tom: MuseScore's default drumset puts GM 41 on G4
        # (second line from the bottom), not Weinberg's A4 — the high
        # floor tom (GM 43) owns A4 there. MuseScore's display wins.
        "low_tom": ("G", "4"),
        "other": ("C", "5"),
    }


def test_simultaneous_hand_instruments_share_one_voice_as_chord():
    performance = DrumPerformance(
        duration_seconds=2.0,
        tempo_map=[TempoChange(time_seconds=0, bpm=120, numerator=4, denominator=4)],
        events=[
            DrumEvent(time_seconds=0, instrument=DrumInstrument.SNARE),
            DrumEvent(time_seconds=0, instrument=DrumInstrument.CLOSED_HIHAT),
        ],
    )
    root = ET.fromstring(performance_to_musicxml(performance))
    hand_notes = [
        note for note in root.findall("./part/measure/note") if note.findtext("voice") == "1"
    ]
    assert len(hand_notes) == 2
    assert hand_notes[1].find("chord") is not None
    assert hand_notes[0].findtext("duration") == hand_notes[1].findtext("duration")
    assert hand_notes[0].findtext("type") == hand_notes[1].findtext("type")


def test_rests_carry_display_position_in_their_voice_zone():
    """Rests sit in their voice's zone (MusicXML percussion tutorial):
    hands rests on the middle line (B4), feet rests below the staff
    (D4). Bare <rest/> left MuseScore to drop foot-voice rests
    mid-staff."""
    performance = DrumPerformance(
        duration_seconds=2.0,
        tempo_map=[TempoChange(time_seconds=0, bpm=120, numerator=4, denominator=4)],
        events=[
            DrumEvent(time_seconds=0.0, instrument=DrumInstrument.CLOSED_HIHAT),
            DrumEvent(time_seconds=1.0, instrument=DrumInstrument.KICK),
        ],
    )
    root = ET.fromstring(performance_to_musicxml(performance))
    rests = [note for note in root.findall(".//note") if note.find("rest") is not None]
    assert rests
    for rest_note in rests:
        rest = rest_note.find("rest")
        if rest_note.findtext("voice") == "1":
            assert (rest.findtext("display-step"), rest.findtext("display-octave")) == ("B", "4")
        else:
            assert rest_note.findtext("voice") == "2"
            assert (rest.findtext("display-step"), rest.findtext("display-octave")) == ("D", "4")


def test_percussion_clef_carries_no_line():
    """Both gold files (MuseScore's testImportDrums.xml, the MusicXML
    percussion tutorial) write <clef><sign>percussion</sign></clef> with
    no <line>: the percussion clef spans the staff."""
    performance = DrumPerformance(
        duration_seconds=1.0,
        tempo_map=[TempoChange(time_seconds=0, bpm=120, numerator=4, denominator=4)],
        events=[DrumEvent(time_seconds=0.0, instrument=DrumInstrument.SNARE)],
    )
    root = ET.fromstring(performance_to_musicxml(performance))
    clefs = root.findall(".//clef")
    assert len(clefs) == 1
    assert clefs[0].findtext("sign") == "percussion"
    assert clefs[0].find("line") is None
