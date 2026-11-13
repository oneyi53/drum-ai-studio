from __future__ import annotations

from io import BytesIO
from xml.etree import ElementTree as ET

from pypdf import PdfReader

from app import pdf_adapter
from app.drum_events import DrumEvent, DrumInstrument, DrumPerformance, TempoChange
from app.pdf_adapter import _render_fallback_pdf


def _assert_landscape_a4(reader: PdfReader) -> None:
    # PDF dimensions are points (1/72 inch). Allow a small rounding tolerance.
    for page in reader.pages:
        assert abs(float(page.mediabox.width) - 841.89) < 1.0
        assert abs(float(page.mediabox.height) - 595.28) < 1.0


def test_fallback_pdf_keeps_system_labels_and_meter_outside_staff_header():
    performance = DrumPerformance(
        duration_seconds=8,
        tempo_map=[TempoChange(time_seconds=0, bpm=120, numerator=4, denominator=4)],
        events=[
            DrumEvent(time_seconds=0.5, instrument=DrumInstrument.KICK, velocity=110),
            DrumEvent(time_seconds=1.0, instrument=DrumInstrument.SNARE, velocity=90),
            DrumEvent(time_seconds=1.5, instrument=DrumInstrument.CLOSED_HIHAT, velocity=72),
        ],
    )
    reader = PdfReader(BytesIO(_render_fallback_pdf(performance, 'PDF layout regression')))
    assert len(reader.pages) == 1
    _assert_landscape_a4(reader)
    text = reader.pages[0].extract_text()
    assert 'System 1' in text
    assert '4/4' in text
    assert 'Legend:' in text
    assert text.count('4/4') == text.count('System ') + len(reader.pages)


def test_fallback_pdf_starts_new_system_with_its_own_label_and_meter():
    performance = DrumPerformance(
        duration_seconds=34,
        tempo_map=[TempoChange(time_seconds=0, bpm=120, numerator=4, denominator=4)],
        events=[
            DrumEvent(time_seconds=0.5, instrument=DrumInstrument.KICK),
            DrumEvent(time_seconds=16.5, instrument=DrumInstrument.SNARE),
        ],
    )
    reader = PdfReader(BytesIO(_render_fallback_pdf(performance, 'Multi-system score')))
    text = '\\n'.join(page.extract_text() for page in reader.pages)
    assert 'System 1' in text
    assert 'System 2' in text
    _assert_landscape_a4(reader)
    assert text.count('4/4') == text.count('System ') + len(reader.pages)


def test_verovio_pdf_pages_use_landscape_a4_dimensions():
    performance = DrumPerformance(
        duration_seconds=4,
        tempo_map=[TempoChange(time_seconds=0, bpm=120, numerator=4, denominator=4)],
        events=[
            DrumEvent(time_seconds=0.5, instrument=DrumInstrument.KICK),
            DrumEvent(time_seconds=1.0, instrument=DrumInstrument.SNARE),
            DrumEvent(time_seconds=1.5, instrument=DrumInstrument.CLOSED_HIHAT),
        ],
    )
    pdf_bytes = pdf_adapter._render_with_verovio(performance, 'Verovio A4 check')
    reader = PdfReader(BytesIO(pdf_bytes))
    assert len(reader.pages) >= 1
    _assert_landscape_a4(reader)


def test_pdf_export_falls_back_when_verovio_font_resources_are_unavailable(monkeypatch):
    performance = DrumPerformance(duration_seconds=1, events=[])
    def unavailable_engraving(*args, **kwargs):
        raise ValueError('Verovio font resources are unavailable')
    monkeypatch.setattr(pdf_adapter, '_render_with_verovio', unavailable_engraving)
    monkeypatch.setattr(pdf_adapter, '_render_fallback_pdf', lambda *args: b'%PDF-fallback')
    assert pdf_adapter.performance_to_pdf(performance) == b'%PDF-fallback'



def test_pdf_renderer_trims_silent_tail_measures_only():
    score = ET.fromstring(
        '<score-partwise><part id="P1">'
        '<measure number="1"><note/></measure>'
        '<measure number="2"><attributes/></measure>'
        '<measure number="3"><attributes/><direction/></measure>'
        '</part></score-partwise>'
    )
    removed = pdf_adapter._trim_trailing_empty_measures(score)
    measures = score.findall("./part/measure")
    assert removed == 2
    assert len(measures) == 1
    # Directional markings from the tail are not silently discarded.
    assert measures[0].find("direction") is not None


def test_verovio_pdf_system_breaks_group_four_or_five_measures():
    score = ET.fromstring(
        '<score-partwise><part id="P1">'
        + ''.join(f'<measure number="{n}"/>' for n in range(1, 13))
        + '</part></score-partwise>'
    )
    pdf_adapter._apply_system_breaks(score, 4)
    measures = score.findall("./part/measure")
    assert [i + 1 for i, measure in enumerate(measures) if measure.find("print") is not None] == [5, 9]

    score = ET.fromstring(
        '<score-partwise><part id="P1">'
        + ''.join(f'<measure number="{n}"/>' for n in range(1, 13))
        + '</part></score-partwise>'
    )
    pdf_adapter._apply_system_breaks(score, 5)
    measures = score.findall("./part/measure")
    assert [i + 1 for i, measure in enumerate(measures) if measure.find("print") is not None] == [6, 11]


def test_pdf_rejects_unsupported_measures_per_system():
    score = ET.fromstring('<score-partwise><part id="P1"><measure number="1"/></part></score-partwise>')
    try:
        pdf_adapter._apply_system_breaks(score, 3)
    except ValueError as exc:
        assert "4 or 5" in str(exc)
    else:
        raise AssertionError("unsupported measure grouping should be rejected")
