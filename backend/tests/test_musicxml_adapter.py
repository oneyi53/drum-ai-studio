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
    assert root.find(".//other-play[@type='midi-velocity']").text == "110"
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
    assert _voice_ties(root, "1") == [
        ("half", "960", True, False, [], []),
        ("quarter", "720", True, False, [], []),
        ("eighth", "240", False, False, ["start"], ["start"]),
    ]
    assert _voice_ties(root, "1", measure_index=1) == [
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
    assert _voice_ties(root, "1")[2] == ("quarter", "480", False, False, [], [])


def test_unrepresentable_barline_split_falls_back_without_tie():
    # Kick at beat 3.9 with the next kick at beat 4.4: the crossing 8th
    # would leave a 48-tick first segment, which is not a standard/dotted
    # value, so the exporter keeps the old truncated duration, untied.
    root = ET.fromstring(performance_to_musicxml(_kick_performance([1.95, 2.2])))
    assert root.findall(".//tie") == []
    assert root.findall(".//tied") == []
    assert _voice_ties(root, "1") == [("64th", "45", False, False, [], [])]


def test_tied_continuation_emitted_for_voice_without_hits_in_next_measure():
    # Kick at beat 3.5, next kick at beat 8.0: the tied 8th continues into
    # measure 2 even though that voice has no hits of its own there.
    root = ET.fromstring(performance_to_musicxml(_kick_performance([1.75, 4.0], 6.0)))
    assert _voice_ties(root, "1", measure_index=1) == [
        ("eighth", "240", False, False, ["stop"], ["stop"]),
    ]


def test_multi_fragment_tie_chain_uses_stop_start_markers():
    # Kick at beat 3.375, next kick at beat 4.5: the quarter splits as
    # 8th + 32nd in measure 1 and a dotted 16th in measure 2.
    root = ET.fromstring(performance_to_musicxml(_kick_performance([1.6875, 2.25])))
    assert _voice_ties(root, "1") == [
        ("half", "960", True, False, [], []),
        ("quarter", "480", True, False, [], []),
        ("16th", "180", True, False, [], []),
        ("eighth", "240", False, False, ["start"], ["start"]),
        ("32nd", "60", False, False, ["stop", "start"], ["stop", "start"]),
    ]
    assert _voice_ties(root, "1", measure_index=1) == [
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
    assert _voice_ties(root, "1") == [
        ("half", "960", True, False, [], []),
        ("quarter", "720", True, False, [], []),
        ("eighth", "240", False, False, ["start"], ["start"]),
        ("eighth", "240", False, True, [], []),
    ]
    assert _voice_ties(root, "1", measure_index=1) == [
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
    assert _voice_notes(root, "3") == [
        ("eighth", False, [("1", "begin")]),
        ("eighth", False, [("1", "continue")]),
        ("eighth", False, [("1", "continue")]),
        ("eighth", False, [("1", "end")]),
        ("quarter", False, []),
    ]


def test_sixteenth_notes_beam_with_second_beam():
    root = ET.fromstring(performance_to_musicxml(_hat_performance([0, 0.125, 0.25, 0.375, 0.5])))
    assert _voice_notes(root, "3") == [
        ("16th", False, [("1", "begin"), ("2", "begin")]),
        ("16th", False, [("1", "continue"), ("2", "continue")]),
        ("16th", False, [("1", "continue"), ("2", "continue")]),
        ("16th", False, [("1", "end"), ("2", "end")]),
        ("quarter", False, []),
    ]


def test_beam_does_not_cross_rest():
    root = ET.fromstring(performance_to_musicxml(_hat_performance([0, 0.25, 0.5, 1.25, 1.5, 1.75])))
    assert _voice_notes(root, "3") == [
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
    assert _voice_notes(root, "3") == [
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
    assert _voice_notes(root, "3", measure_index=0) == [
        ("half", True, []),
        ("quarter", True, []),
        ("eighth", False, [("1", "begin")]),
        ("eighth", False, [("1", "end")]),
    ]
    assert _voice_notes(root, "3", measure_index=1) == [
        ("eighth", False, [("1", "begin")]),
        ("eighth", False, [("1", "end")]),
        ("quarter", False, []),
    ]


def test_lone_sixteenth_gets_secondary_beam_hook():
    forward = ET.fromstring(performance_to_musicxml(_hat_performance([0, 0.125, 0.5])))
    assert _voice_notes(forward, "3") == [
        ("16th", False, [("1", "begin"), ("2", "forward hook")]),
        ("eighth", False, [("1", "end")]),
        ("quarter", False, []),
    ]
    backward = ET.fromstring(performance_to_musicxml(_hat_performance([0, 0.375, 0.5])))
    assert _voice_notes(backward, "3") == [
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
        note for note in root.findall(".//measure/note")
        if note.findtext("voice") == "1"
    ]
    assert [note.find("rest") is not None for note in voice_notes] == [False, True, False]
    assert [note.findtext("type") for note in voice_notes] == [
        "quarter", "quarter", "quarter"
    ]
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
    voice_notes = [
        note for note in first_measure.findall("note")
        if note.findtext("voice") == "1"
    ]
    # The barline hit emits nothing; the gap to the barline is filled
    # with explicit rests (quarter + half = the rest of the measure).
    assert [note.find("rest") is not None for note in voice_notes] == [
        False, True, True
    ]
    assert [note.findtext("type") for note in voice_notes] == [
        "quarter", "quarter", "half"
    ]
    assert [note.findtext("duration") for note in voice_notes] == [
        "480", "480", "960"
    ]


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
    assert any(
        forward.findtext("duration") == "24"
        for forward in root.findall(".//forward")
    )


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
        note for note in root.findall(".//measure/note")
        if note.findtext("voice") == "1"
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
        note for note in root.findall(".//measure/note")
        if note.findtext("voice") == "1"
    ]
    assert [note.find("rest") is not None for note in voice_notes] == [False, True, False]
    assert [note.findtext("type") for note in voice_notes] == [
        "quarter", "eighth", "quarter"
    ]


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
        note for note in root.findall(".//measure/note")
        if note.findtext("voice") == "1" and note.find("rest") is None
    ]
    assert kick_notes[0].findtext("duration") == "1"
    assert kick_notes[0].findtext("type") == "128th"
    assert kick_notes[0].findtext("time-modification/actual-notes") == "15"
    assert kick_notes[0].findtext("time-modification/normal-notes") == "1"
