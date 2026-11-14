from __future__ import annotations

import re
from io import BytesIO
from pathlib import Path
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


def _groove_performance(bars: int) -> DrumPerformance:
    """Representative 120 BPM 4/4 groove: kick/snare/hats plus a tom fill."""
    kick, snare = DrumInstrument.KICK, DrumInstrument.SNARE
    closed_hat, open_hat = DrumInstrument.CLOSED_HIHAT, DrumInstrument.OPEN_HIHAT
    crash, ride = DrumInstrument.CRASH, DrumInstrument.RIDE
    toms = (DrumInstrument.HIGH_TOM, DrumInstrument.MID_TOM, DrumInstrument.LOW_TOM)
    events: list[DrumEvent] = []
    for bar in range(bars):
        start = bar * 2.0
        if bar == 0:
            events.append(DrumEvent(time_seconds=start, instrument=crash, velocity=100))
        for beat in (0.0, 0.75, 1.0):
            events.append(DrumEvent(time_seconds=start + beat, instrument=kick, velocity=110))
        for beat in (0.5, 1.5):
            events.append(DrumEvent(time_seconds=start + beat, instrument=snare, velocity=100))
        for step in range(8):
            events.append(
                DrumEvent(time_seconds=start + step * 0.25, instrument=closed_hat, velocity=70)
            )
        if bar % 4 == 3:
            events.append(DrumEvent(time_seconds=start + 1.75, instrument=open_hat, velocity=80))
        if bar % 4 == 1:
            for step in range(4):
                events.append(DrumEvent(time_seconds=start + step * 0.5, instrument=ride, velocity=65))
    if bars >= 2:
        start = (bars - 1) * 2.0
        fill = (toms[0], toms[0], toms[1], toms[1], toms[2], toms[2], snare, snare)
        for step, instrument in enumerate(fill):
            events.append(
                DrumEvent(time_seconds=start + 1.0 + step * 0.125, instrument=instrument, velocity=95)
            )
    events.sort(key=lambda event: event.time_seconds)
    return DrumPerformance(
        duration_seconds=bars * 2.0 + 0.5,
        tempo_map=[TempoChange(time_seconds=0, bpm=120, numerator=4, denominator=4)],
        events=events,
    )


def _timed_measures(score_root: ET.Element) -> list[tuple[str | None, str | None]]:
    return [
        (measure.get("number"), measure.findtext("attributes/time/beats"))
        for measure in score_root.findall("./part/measure")
        if measure.find("attributes/time") is not None
    ]


def _verovio_toolkit():
    import verovio

    toolkit = verovio.toolkit(False)
    resource_path = Path(verovio.__file__).resolve().parent / "data"
    assert toolkit.setResourcePath(str(resource_path))
    return toolkit


def _measures_per_system(svg: str) -> list[int]:
    systems: list[list[int]] = []
    current: list[int] | None = None
    for match in re.finditer(r'<g id="[^"]+" class="(system|measure)"', svg):
        if match.group(1) == "system":
            current = []
            systems.append(current)
        elif match.group(1) == "measure" and current is not None:
            current.append(1)
    return [len(system) for system in systems]


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


def test_prepare_print_score_keeps_time_signature_only_in_first_measure():
    performance = _groove_performance(8)
    score_root = pdf_adapter._prepare_print_score(performance, 4)
    assert _timed_measures(score_root) == [("1", "4")]
    # The canonical MusicXML export is untouched by the print-only strip.
    from app.musicxml_adapter import performance_to_musicxml

    exported = ET.fromstring(performance_to_musicxml(performance))
    measures = exported.findall("./part/measure")
    assert len(exported.findall("./part/measure/attributes/time")) == len(measures)


def test_prepare_print_score_keeps_time_signature_on_meter_change():
    performance = DrumPerformance(
        duration_seconds=14,
        tempo_map=[
            TempoChange(time_seconds=0, bpm=120, numerator=4, denominator=4),
            TempoChange(time_seconds=8, bpm=100, numerator=3, denominator=4),
        ],
        events=[
            DrumEvent(time_seconds=0.5, instrument=DrumInstrument.KICK),
            DrumEvent(time_seconds=8.5, instrument=DrumInstrument.SNARE),
            DrumEvent(time_seconds=12.0, instrument=DrumInstrument.KICK),
        ],
    )
    score_root = pdf_adapter._prepare_print_score(performance, 4)
    assert _timed_measures(score_root) == [("1", "4"), ("5", "3")]


def test_verovio_options_use_explicit_breaks_and_justify_single_system():
    multi = pdf_adapter._verovio_options(16, 4)
    assert multi["breaks"] == "line"
    assert "minLastJustification" not in multi
    five_per_system = pdf_adapter._verovio_options(10, 5)
    assert five_per_system["breaks"] == "line"
    assert "minLastJustification" not in five_per_system
    single = pdf_adapter._verovio_options(2, 4)
    assert single["breaks"] == "auto"
    assert single["minLastJustification"] == 0
    exactly_one_system = pdf_adapter._verovio_options(4, 4)
    assert exactly_one_system["breaks"] == "auto"
    assert exactly_one_system["minLastJustification"] == 0


def test_verovio_system_geometry_matches_configured_grouping():
    for bars, expected in [(16, [4, 4, 4, 4]), (8, [4, 4]), (2, [2])]:
        performance = _groove_performance(bars)
        score_root = pdf_adapter._prepare_print_score(performance, 4)
        measure_count = len(score_root.findall("./part/measure"))
        toolkit = _verovio_toolkit()
        toolkit.setOptions(pdf_adapter._verovio_options(measure_count, 4))
        assert toolkit.loadData(ET.tostring(score_root, encoding="unicode"))
        assert toolkit.getPageCount() == 1
        assert _measures_per_system(toolkit.renderToSVG(1)) == expected


def test_prepare_print_score_rounds_tempo_text_to_one_decimal():
    performance = DrumPerformance(
        duration_seconds=4,
        tempo_map=[TempoChange(time_seconds=0, bpm=60.0927, numerator=4, denominator=4)],
        events=[DrumEvent(time_seconds=0.5, instrument=DrumInstrument.KICK)],
    )
    score_root = pdf_adapter._prepare_print_score(performance, 4)
    words = [element.text for element in score_root.findall(".//words")]
    assert "Tempo: 60.1 BPM" in words
    assert not any("60.0927" in (text or "") for text in words)

    integer_tempo = _groove_performance(1)
    score_root = pdf_adapter._prepare_print_score(integer_tempo, 4)
    words = [element.text for element in score_root.findall(".//words")]
    assert "Tempo: 120 BPM" in words
