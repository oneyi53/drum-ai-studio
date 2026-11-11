from __future__ import annotations

from io import BytesIO

from pypdf import PdfReader

from app.drum_events import DrumEvent, DrumInstrument, DrumPerformance, TempoChange
from app.pdf_adapter import _render_fallback_pdf


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

    pdf_bytes = _render_fallback_pdf(performance, "PDF layout regression")
    reader = PdfReader(BytesIO(pdf_bytes))

    assert len(reader.pages) == 1
    text = reader.pages[0].extract_text()
    assert "System 1" in text
    assert "4/4" in text
    assert "Legend:" in text
    # The initial time signature belongs in the left gutter, not repeated
    # above every measure where it competes with bar numbers and note stems.
    assert text.count("4/4") == 1


def test_fallback_pdf_starts_new_system_with_its_own_label_and_meter():
    performance = DrumPerformance(
        duration_seconds=34,
        tempo_map=[TempoChange(time_seconds=0, bpm=120, numerator=4, denominator=4)],
        events=[
            DrumEvent(time_seconds=0.5, instrument=DrumInstrument.KICK),
            DrumEvent(time_seconds=16.5, instrument=DrumInstrument.SNARE),
        ],
    )

    reader = PdfReader(BytesIO(_render_fallback_pdf(performance, "Multi-system score")))
    text = "\\n".join(page.extract_text() for page in reader.pages)

    assert "System 1" in text
    assert "System 2" in text
    assert text.count("4/4") == 2
