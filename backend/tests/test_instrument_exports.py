from __future__ import annotations

import xml.etree.ElementTree as ET

from app.drum_events import DrumEvent, DrumInstrument, DrumPerformance, TempoChange
from app.main import _filter_performance_instrument
from app.midi_adapter import midi_to_performance, performance_to_midi
from app.musicxml_adapter import performance_to_musicxml
from app.pdf_adapter import performance_to_pdf
from app.project_file import annotation_csv_text


def sample_performance() -> DrumPerformance:
    return DrumPerformance(
        duration_seconds=2.0,
        tempo_map=[TempoChange(time_seconds=0, bpm=120)],
        events=[
            DrumEvent(time_seconds=0.25, instrument=DrumInstrument.KICK, velocity=110),
            DrumEvent(time_seconds=0.5, instrument=DrumInstrument.SNARE, velocity=96),
            DrumEvent(time_seconds=0.75, instrument=DrumInstrument.CLOSED_HIHAT, velocity=80),
        ],
    )


def test_voice_filter_keeps_only_selected_instrument_and_tempo() -> None:
    original = sample_performance()
    filtered = _filter_performance_instrument(original, DrumInstrument.SNARE)

    assert [event.instrument for event in filtered.events] == [DrumInstrument.SNARE]
    assert filtered.duration_seconds == original.duration_seconds
    assert filtered.tempo_map == original.tempo_map
    assert len(original.events) == 3


def test_no_voice_filter_preserves_full_performance() -> None:
    original = sample_performance()
    assert _filter_performance_instrument(original, None) is original


def test_csv_voice_export_contains_only_selected_events() -> None:
    filtered = _filter_performance_instrument(sample_performance(), DrumInstrument.KICK)
    csv_text = annotation_csv_text(filtered)

    assert csv_text.splitlines() == ["onset_seconds,instrument", "0.250,kick"]


def test_midi_voice_export_round_trips_only_selected_events(tmp_path) -> None:
    filtered = _filter_performance_instrument(sample_performance(), DrumInstrument.SNARE)
    midi_path = tmp_path / "snare.mid"

    performance_to_midi(filtered, midi_path)
    exported = midi_to_performance(midi_path)

    assert [event.instrument for event in exported.events] == [DrumInstrument.SNARE]


def test_musicxml_voice_export_contains_only_selected_voice() -> None:
    filtered = _filter_performance_instrument(sample_performance(), DrumInstrument.CLOSED_HIHAT)
    xml_text = performance_to_musicxml(filtered)
    root = ET.fromstring(xml_text)

    assert root.findtext(".//part-name") == "Drum Set"
    assert len(root.findall(".//note")) == 1


def test_pdf_voice_export_is_a_valid_pdf_document() -> None:
    filtered = _filter_performance_instrument(sample_performance(), DrumInstrument.KICK)
    pdf = performance_to_pdf(filtered, title="Kick only")

    assert pdf.startswith(b"%PDF-")
