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
