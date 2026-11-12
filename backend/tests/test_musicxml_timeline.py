"""Regression coverage for shared-cursor MusicXML reconstruction."""
import xml.etree.ElementTree as ET

import pytest

from app.musicxml_adapter import reconstruct_and_validate_measure


def parse(body: str) -> ET.Element:
    return ET.fromstring(body)


def test_compound_6_8_capacity_and_dotted_quarters():
    measure = parse("""<measure number="1">
      <attributes><divisions>4</divisions><time><beats>6</beats><beat-type>8</beat-type></time></attributes>
      <note><duration>6</duration><type>quarter</type><dot/><voice>1</voice></note>
      <note><duration>6</duration><type>quarter</type><dot/><voice>1</voice></note>
    </measure>""")
    result = reconstruct_and_validate_measure(measure, divisions=4)
    assert result["expected_capacity"] == 12
    assert [e["onset"] for e in result["voice_events"]["1"]] == [0, 6]
    assert result["voice_events"]["1"][-1]["offset_end"] == 12


@pytest.mark.parametrize(("beats", "beat_type", "capacity"), [(4, 4, 16), (3, 4, 12), (6, 8, 12)])
def test_meter_capacity(beats, beat_type, capacity):
    measure = parse(f"""<measure number="1">
      <attributes><divisions>4</divisions><time><beats>{beats}</beats><beat-type>{beat_type}</beat-type></time></attributes>
    </measure>""")
    assert reconstruct_and_validate_measure(measure, divisions=4)["expected_capacity"] == capacity


def test_shared_cursor_backup_forward_and_chord_onsets():
    measure = parse("""<measure number="1">
      <attributes><divisions>4</divisions><time><beats>4</beats><beat-type>4</beat-type></time></attributes>
      <note><duration>4</duration><voice>1</voice></note>
      <note><chord/><duration>4</duration><voice>1</voice></note>
      <note><rest/><duration>12</duration><voice>1</voice></note>
      <backup><duration>16</duration></backup>
      <note><duration>4</duration><voice>2</voice></note>
      <note><duration>12</duration><voice>2</voice></note>
    </measure>""")
    result = reconstruct_and_validate_measure(measure, divisions=4)
    voice1, voice2 = result["voice_events"]["1"], result["voice_events"]["2"]
    assert voice1[0]["onset"] == voice1[1]["onset"] == 0
    assert voice1[1]["is_chord"] is True
    assert voice2[0]["onset"] == 0
    assert voice2[-1]["offset_end"] == 16


def test_backup_underflow_is_rejected():
    measure = parse('<measure><backup><duration>1</duration></backup></measure>')
    with pytest.raises(ValueError, match="backup underflow"):
        reconstruct_and_validate_measure(measure, divisions=4)


def test_divisions_from_measure_attributes_override_default():
    measure = parse("""<measure><attributes><divisions>8</divisions>
      <time><beats>3</beats><beat-type>4</beat-type></time></attributes></measure>""")
    result = reconstruct_and_validate_measure(measure, divisions=480)
    assert result["divisions"] == 8
    assert result["expected_capacity"] == 24


def test_chord_without_parent_is_rejected():
    measure = parse('<measure><note><chord/><duration>1</duration><voice>1</voice></note></measure>')
    with pytest.raises(ValueError, match="no preceding"):
        reconstruct_and_validate_measure(measure, divisions=4)


def test_measure_overflow_is_rejected():
    measure = parse("""<measure><attributes><divisions>4</divisions>
      <time><beats>3</beats><beat-type>4</beat-type></time></attributes>
      <note><duration>16</duration><voice>1</voice></note></measure>""")
    with pytest.raises(ValueError, match="overflow"):
        reconstruct_and_validate_measure(measure, divisions=4)


def test_forward_advances_shared_cursor():
    measure = parse("""<measure><attributes><divisions>4</divisions>
      <time><beats>4</beats><beat-type>4</beat-type></time></attributes>
      <forward><duration>4</duration></forward>
      <note><duration>12</duration><voice>1</voice></note></measure>""")
    result = reconstruct_and_validate_measure(measure, divisions=4)
    assert result["voice_events"]["1"][0]["onset"] == 4
    assert result["voice_events"]["1"][0]["offset_end"] == 16


def test_chord_duration_must_match_parent():
    measure = parse("""<measure><note><duration>4</duration><voice>1</voice></note>
      <note><chord/><duration>2</duration><voice>1</voice></note></measure>""")
    with pytest.raises(ValueError, match="duration does not match"):
        reconstruct_and_validate_measure(measure, divisions=4)


def test_same_voice_number_on_different_staves_is_validated_independently():
    measure = parse("""<measure><attributes><divisions>4</divisions>
      <time><beats>4</beats><beat-type>4</beat-type></time></attributes>
      <note><duration>8</duration><voice>1</voice><staff>1</staff></note>
      <backup><duration>8</duration></backup>
      <note><duration>8</duration><voice>1</voice><staff>2</staff></note>
    </measure>""")
    result = reconstruct_and_validate_measure(measure, divisions=4)
    assert len(result["voice_events"]["1"]) == 2
