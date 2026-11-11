"""Render canonical drum events as a printable percussion-staff PDF."""
from __future__ import annotations

from io import BytesIO
from math import floor

from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas

from .drum_events import DrumInstrument, DrumPerformance, TempoChange

PAGE_W, PAGE_H = landscape(A4)
LEFT, RIGHT = 38.0, 38.0
STAFF_TOP = 0.0
SYSTEM_HEIGHT = 154.0
MEASURE_GAP = 5.0
MEASURES_PER_SYSTEM = 4
SYSTEMS_PER_PAGE = 3
STAFF_SPACING = 8.0
INSTRUMENT_Y = {
    DrumInstrument.CRASH: 4,
    DrumInstrument.RIDE: 3,
    DrumInstrument.OPEN_HIHAT: 2,
    DrumInstrument.CLOSED_HIHAT: 2,
    DrumInstrument.PEDAL_HIHAT: 1,
    DrumInstrument.HIGH_TOM: 1,
    DrumInstrument.SNARE: 0,
    DrumInstrument.MID_TOM: -1,
    DrumInstrument.LOW_TOM: -2,
    DrumInstrument.KICK: -3,
    DrumInstrument.OTHER: 0,
}
LABELS = {
    DrumInstrument.KICK: "Kick",
    DrumInstrument.SNARE: "Snare",
    DrumInstrument.CLOSED_HIHAT: "Closed HH",
    DrumInstrument.OPEN_HIHAT: "Open HH",
    DrumInstrument.PEDAL_HIHAT: "Pedal HH",
    DrumInstrument.RIDE: "Ride",
    DrumInstrument.CRASH: "Crash",
    DrumInstrument.HIGH_TOM: "High Tom",
    DrumInstrument.MID_TOM: "Mid Tom",
    DrumInstrument.LOW_TOM: "Low Tom",
    DrumInstrument.OTHER: "Other",
}


def _tempo_changes(performance: DrumPerformance) -> list[TempoChange]:
    changes = performance.tempo_map or [
        TempoChange(time_seconds=0, bpm=120, numerator=4, denominator=4)
    ]
    if changes[0].time_seconds > 0:
        changes = [TempoChange(time_seconds=0, bpm=120, numerator=4, denominator=4), *changes]
    return changes


def _seconds_to_quarters(seconds: float, changes: list[TempoChange]) -> float:
    elapsed = 0.0
    quarters = 0.0
    bpm = 120.0
    for change in changes:
        if change.time_seconds > seconds:
            break
        quarters += (change.time_seconds - elapsed) * bpm / 60.0
        elapsed = change.time_seconds
        bpm = change.bpm
    return quarters + (seconds - elapsed) * bpm / 60.0


def _measure_boundaries(performance: DrumPerformance, changes: list[TempoChange]) -> list[tuple[float, float, int, int]]:
    total = max(
        _seconds_to_quarters(performance.duration_seconds, changes),
        max((_seconds_to_quarters(event.time_seconds, changes) for event in performance.events), default=0.0) + 0.25,
        0.25,
    )
    signatures: list[tuple[float, int, int]] = []
    previous: tuple[int, int] | None = None
    for change in changes:
        signature = (change.numerator, change.denominator)
        if signature != previous:
            signatures.append((_seconds_to_quarters(change.time_seconds, changes), *signature))
            previous = signature
    if not signatures or signatures[0][0] > 0:
        signatures.insert(0, (0.0, 4, 4))
    bars: list[tuple[float, float, int, int]] = []
    start = 0.0
    while start < total - 1e-8:
        active = max((item for item in signatures if item[0] <= start + 1e-8), key=lambda item: item[0], default=(0.0, 4, 4))
        numerator, denominator = active[1], active[2]
        end = start + numerator * 4.0 / denominator
        next_change = min((item[0] for item in signatures if item[0] > start + 1e-8), default=end)
        end = min(end, next_change, total)
        if end <= start + 1e-8:
            end = start + numerator * 4.0 / denominator
        bars.append((start, end, numerator, denominator))
        start = end
    return bars


def _draw_note(pdf: canvas.Canvas, x: float, y: float, instrument: DrumInstrument, velocity: int) -> None:
    pdf.saveState()
    pdf.setLineWidth(0.9)
    size = 3.0 + velocity / 127.0
    if instrument in {
        DrumInstrument.CLOSED_HIHAT, DrumInstrument.OPEN_HIHAT,
        DrumInstrument.PEDAL_HIHAT, DrumInstrument.RIDE, DrumInstrument.CRASH,
    }:
        pdf.line(x - size, y - size, x + size, y + size)
        pdf.line(x - size, y + size, x + size, y - size)
        if instrument == DrumInstrument.OPEN_HIHAT:
            pdf.circle(x, y, size + 2.0, stroke=1, fill=0)
    else:
        pdf.ellipse(x - size - 1, y - size, x + size + 1, y + size, stroke=1, fill=1)
    pdf.line(x + size + 1, y, x + size + 1, y + 25)
    pdf.restoreState()


def performance_to_pdf(performance: DrumPerformance, title: str = "DrumAI Studio — Drum Score") -> bytes:
    """Return a landscape, printable PDF score derived from canonical drum events."""
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=landscape(A4), pageCompression=1)
    pdf.setTitle(title)
    pdf.setAuthor("DrumAI Studio")
    changes = _tempo_changes(performance)
    bars = _measure_boundaries(performance, changes)
    event_beats = [
        (event, _seconds_to_quarters(event.time_seconds, changes))
        for event in performance.events
    ]
    usable_width = PAGE_W - LEFT - RIGHT
    measure_width = (usable_width - (MEASURES_PER_SYSTEM - 1) * MEASURE_GAP) / MEASURES_PER_SYSTEM
    page_system = 0

    for system_index in range(0, len(bars), MEASURES_PER_SYSTEM):
        if page_system == 0:
            pdf.setFont("Helvetica-Bold", 16)
            pdf.drawString(LEFT, PAGE_H - 32, title[:90])
            pdf.setFont("Helvetica", 8)
            first = changes[0]
            pdf.drawString(LEFT, PAGE_H - 46, f"Tempo: {first.bpm:g} BPM    Meter: {first.numerator}/{first.denominator}    Duration: {performance.duration_seconds:.1f}s")
            pdf.drawRightString(PAGE_W - RIGHT, PAGE_H - 46, f"{len(performance.events)} drum events")
        top = PAGE_H - 76 - page_system * SYSTEM_HEIGHT
        staff_mid = top - 43
        x0 = LEFT + 24
        pdf.setFont("Helvetica-Bold", 8)
        pdf.drawString(LEFT, staff_mid + 13, f"System {system_index // MEASURES_PER_SYSTEM + 1}")
        # Five-line percussion staff.
        for line in range(5):
            y = staff_mid + (line - 2) * STAFF_SPACING
            pdf.setLineWidth(0.55)
            pdf.line(x0, y, PAGE_W - RIGHT, y)
        pdf.setFont("Helvetica-Bold", 9)
        pdf.drawString(LEFT, staff_mid - 2, "Drums")
        system_bars = bars[system_index:system_index + MEASURES_PER_SYSTEM]
        for local_index, (bar_start, bar_end, numerator, denominator) in enumerate(system_bars):
            bx = x0 + local_index * (measure_width + MEASURE_GAP)
            pdf.setFont("Helvetica", 8)
            pdf.drawString(bx + 3, staff_mid + 27, f"{system_index + local_index + 1}")
            pdf.setLineWidth(0.7)
            pdf.line(bx, staff_mid - 22, bx, staff_mid + 22)
            pdf.line(bx + measure_width, staff_mid - 22, bx + measure_width, staff_mid + 22)
            if local_index == 0 or (bar_start, numerator, denominator) != (0.0, 4, 4):
                pdf.setFont("Helvetica", 7)
                pdf.drawString(bx + 4, staff_mid + 31, f"{numerator}/{denominator}")
            for event, beat in event_beats:
                if bar_start - 1e-8 <= beat < bar_end - 1e-8:
                    ratio = (beat - bar_start) / max(bar_end - bar_start, 1e-8)
                    x = bx + 5 + ratio * (measure_width - 10)
                    y = staff_mid + INSTRUMENT_Y[event.instrument] * (STAFF_SPACING / 2)
                    _draw_note(pdf, x, y, event.instrument, event.velocity)
        # Footer legend uses all instrument types actually present.
        if system_index + MEASURES_PER_SYSTEM >= len(bars) or page_system == SYSTEMS_PER_PAGE - 1:
            present = sorted({event.instrument for event in performance.events}, key=lambda item: item.value)
            legend = "   •   ".join(LABELS[item] for item in present) or "No detected drum events"
            pdf.setFont("Helvetica", 7)
            pdf.drawString(LEFT, 22, f"Legend: {legend[:150]}")
            pdf.drawRightString(PAGE_W - RIGHT, 22, "Generated from the latest editable drum events")
        page_system += 1
        if page_system >= SYSTEMS_PER_PAGE and system_index + MEASURES_PER_SYSTEM < len(bars):
            pdf.showPage()
            page_system = 0
    if not bars:
        pdf.setFont("Helvetica", 12)
        pdf.drawString(LEFT, PAGE_H - 90, "No measures or drum events to display.")
    pdf.save()
    return buffer.getvalue()
