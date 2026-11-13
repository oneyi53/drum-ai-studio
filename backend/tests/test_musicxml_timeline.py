from __future__ import annotations

from fractions import Fraction
from xml.etree import ElementTree as ET

import pytest

from app.musicxml_adapter import (
    reconstruct_and_validate_measure,
    reconstruct_and_validate_musicxml,
)


def parse(body: str) -> ET.Element:
    return ET.fromstring(body)


def test_reconstructs_simple_4_4_voice_and_silent_gaps():
    measure = parse("""<measure number="1">
      <attributes><divisions>4</divisions><time><beats>4</beats><beat-type>4</beat-type></time></attributes>
      <forward><duration>2</duration></forward>
      <note><duration>4</duration><voice>1</voice></note>
    </measure>""")
    result = reconstruct_and_validate_measure(measure)
    stream = result["voice_events"][("1", "1")]
    assert stream[0]["onset"] == Fraction(1, 2)
    assert stream[0]["offset_end"] == Fraction(3, 2)
    assert result["expected_capacity"] == 4
    assert result["voice_gaps"][("1", "1")] == [
        (Fraction(0), Fraction(1, 2)),
        (Fraction(3, 2), Fraction(4)),
    ]


def test_6_8_capacity_uses_quarter_note_units():
    measure = parse("""<measure>
      <attributes><divisions>4</divisions><time><beats>6</beats><beat-type>8</beat-type></time></attributes>
      <note><duration>6</duration><voice>1</voice></note>
      <note><duration>6</duration><voice>1</voice></note>
    </measure>""")
    result = reconstruct_and_validate_measure(measure, divisions=4)
    assert result["expected_capacity"] == 3
    assert [event["onset"] for event in result["voice_events"][("1", "1")]] == [
        Fraction(0), Fraction(3, 2)
    ]


def test_shared_cursor_backup_forward_and_chord_onsets():
    measure = parse("""<measure number="1">
      <attributes><divisions>4</divisions><time><beats>4</beats><beat-type>4</beat-type></time></attributes>
      <note><duration>4</duration><voice>1</voice></note>
      <note><chord/><duration>4</duration><voice>1</voice></note>
      <note><rest/><duration>12</duration><voice>1</voice></note>
      <backup><duration>16</duration></backup>
      <note><duration>4</duration><voice>2</voice></note>
      <forward><duration>12</duration></forward>
    </measure>""")
    result = reconstruct_and_validate_measure(measure, divisions=4)
    voice_one = result["voice_events"][("1", "1")]
    voice_two = result["voice_events"][("1", "2")]
    assert voice_one[0]["onset"] == voice_one[1]["onset"] == 0
    assert voice_one[1]["is_chord"] is True
    assert voice_two[0]["onset"] == 0
    assert voice_two[0]["offset_end"] == 1
    assert result["max_cursor"] == 4


def test_same_voice_number_on_different_staves_is_independent():
    measure = parse("""<measure>
      <attributes><divisions>4</divisions><time><beats>4</beats><beat-type>4</beat-type></time></attributes>
      <note><duration>8</duration><voice>1</voice><staff>1</staff></note>
      <backup><duration>8</duration></backup>
      <note><duration>8</duration><voice>1</voice><staff>2</staff></note>
    </measure>""")
    result = reconstruct_and_validate_measure(measure, divisions=4)
    assert set(result["voice_events"]) == {("1", "1"), ("2", "1")}


def test_divisions_change_mid_measure_preserves_quarter_note_cursor():
    measure = parse("""<measure>
      <attributes><divisions>4</divisions><time><beats>4</beats><beat-type>4</beat-type></attributes>
      <note><duration>4</duration><voice>1</voice></note>
      <attributes><divisions>8</divisions></attributes>
      <note><duration>8</duration><voice>1</voice></note>
    </measure>""")
    result = reconstruct_and_validate_measure(measure)
    events = result["voice_events"][("1", "1")]
    assert [event["onset"] for event in events] == [Fraction(0), Fraction(1)]
    assert [event["duration"] for event in events] == [Fraction(1), Fraction(1)]
    assert result["divisions"] == 8


def test_additive_meter_capacity_is_supported():
    measure = parse("""<measure>
      <attributes><divisions>4</divisions><time><beats>3+2</beats><beat-type>8</beat-type></time></attributes>
      <note><duration>10</duration><voice>1</voice></note>
    </measure>""")
    result = reconstruct_and_validate_measure(measure, divisions=4)
    assert result["time_signature"] == (5, 8)
    assert result["expected_capacity"] == Fraction(5, 2)


def test_backup_underflow_is_rejected():
    measure = parse('<measure><backup><duration>1</duration></backup></measure>')
    with pytest.raises(ValueError, match="backup underflow"):
        reconstruct_and_validate_measure(measure, divisions=4)


def test_orphan_chord_is_rejected():
    measure = parse('<measure><note><chord/><duration>1</duration><voice>1</voice></note></measure>')
    with pytest.raises(ValueError, match="no preceding"):
        reconstruct_and_validate_measure(measure, divisions=4)


def test_chord_voice_staff_and_duration_must_match_parent():
    cases = [
        ('<note><duration>4</duration><voice>1</voice></note><note><chord/><duration>4</duration><voice>2</voice></note>', "voice/staff"),
        ('<note><duration>4</duration><voice>1</voice><staff>1</staff></note><note><chord/><duration>4</duration><voice>1</voice><staff>2</staff></note>', "voice/staff"),
        ('<note><duration>4</duration><voice>1</voice></note><note><chord/><duration>2</duration><voice>1</voice></note>', "duration does not match"),
    ]
    for body, message in cases:
        with pytest.raises(ValueError, match=message):
            reconstruct_and_validate_measure(parse(f"<measure>{body}</measure>"), divisions=4)


def test_overlap_after_backup_is_rejected():
    measure = parse("""<measure>
      <attributes><divisions>4</divisions><time><beats>4</beats><beat-type>4</beat-type></time></attributes>
      <note><duration>8</duration><voice>1</voice></note>
      <backup><duration>4</duration></backup>
      <note><duration>4</duration><voice>1</voice></note>
    </measure>""")
    with pytest.raises(ValueError, match="overlapping events"):
        reconstruct_and_validate_measure(measure, divisions=4)


def test_measure_overflow_is_rejected():
    measure = parse("""<measure>
      <attributes><divisions>4</divisions><time><beats>3</beats><beat-type>4</beat-type></time></attributes>
      <note><duration>16</duration><voice>1</voice></note>
    </measure>""")
    with pytest.raises(ValueError, match="overflow"):
        reconstruct_and_validate_measure(measure, divisions=4)


def test_non_positive_durations_and_divisions_are_rejected():
    with pytest.raises(ValueError, match="divisions must be positive"):
        reconstruct_and_validate_measure(parse("<measure/>"), divisions=0)
    with pytest.raises(ValueError, match="note/duration must be positive"):
        reconstruct_and_validate_measure(
            parse("<measure><note><duration>0</duration></note></measure>")
        )
    with pytest.raises(ValueError, match="attributes/divisions must be positive"):
        reconstruct_and_validate_measure(
            parse("<measure><attributes><divisions>0</divisions></attributes></measure>")
        )


def test_document_validator_carries_divisions_and_time_signature_between_measures():
    xml = """<score-partwise version="4.0">
      <part id="P1">
        <measure number="1">
          <attributes><divisions>4</divisions><time><beats>3</beats><beat-type>4</beat-type></time></attributes>
          <note><duration>12</duration><voice>1</voice></note>
        </measure>
        <measure number="2">
          <note><duration>12</duration><voice>1</voice></note>
        </measure>
      </part>
    </score-partwise>"""
    results = reconstruct_and_validate_musicxml(xml)
    assert len(results) == 2
    assert results[1]["time_signature"] == (3, 4)
    assert results[1]["expected_capacity"] == 3
    assert results[1]["divisions"] == 4


def test_document_validator_rejects_invalid_xml_and_non_score_root():
    with pytest.raises(ValueError, match="invalid MusicXML"):
        reconstruct_and_validate_musicxml("<score-partwise>")
    with pytest.raises(ValueError, match="root must be score-partwise"):
        reconstruct_and_validate_musicxml("<not-a-score/>")


def test_empty_implicit_measure_is_valid():
    measure = parse('<measure number="0" implicit="yes"/>')
    result = reconstruct_and_validate_measure(measure)
    assert result["implicit"] is True
    assert result["voice_events"] == {}


def test_namespaced_musicxml_is_supported():
    xml = """<score-partwise xmlns="http://www.musicxml.org/ns/musicxml">
      <part id="P1"><measure number="1">
        <attributes><divisions>4</divisions><time><beats>4</beats><beat-type>4</beat-type></time></attributes>
        <note><duration>4</duration><voice>1</voice></note>
      </measure></part>
    </score-partwise>"""
    result = reconstruct_and_validate_musicxml(xml)
    assert result[0]["part"] == "P1"
    assert result[0]["voice_events"][("1", "1")][0]["duration"] == Fraction(1)


def test_rest_cannot_be_used_as_chord_parent():
    measure = parse("""<measure>
      <attributes><divisions>4</divisions><time><beats>4</beats><beat-type>4</beat-type></time></attributes>
      <note><rest/><duration>4</duration><voice>1</voice></note>
      <note><chord/><duration>4</duration><voice>1</voice></note>
    </measure>""")
    with pytest.raises(ValueError, match="rest cannot be the parent"):
        reconstruct_and_validate_measure(measure, divisions=4)
