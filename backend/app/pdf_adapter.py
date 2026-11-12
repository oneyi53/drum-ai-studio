"""Render canonical drum events as a printable percussion-staff PDF."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree as ET

from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas

from .drum_events import DrumInstrument, DrumPerformance, TempoChange
from .musicxml_adapter import performance_to_musicxml

PAGE_W, PAGE_H = landscape(A4)
LEFT, RIGHT = 38.0, 38.0
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


def _apply_system_breaks(score_root: ET.Element, measures_per_system: int) -> None:
    """Insert explicit MusicXML line breaks after each configured measure group."""
    if measures_per_system not in {4, 5}:
        raise ValueError("measures_per_system must be 4 or 5")
    measures = score_root.findall("./part/measure")
    for measure_index, measure in enumerate(measures):
        if measure_index and measure_index % measures_per_system == 0:
            measure.insert(0, ET.Element("print", {"new-system": "yes"}))


def _render_with_verovio(
    performance: DrumPerformance, title: str, measures_per_system: int = MEASURES_PER_SYSTEM
) -> bytes:
    """Engrave MusicXML with Verovio and convert its vector SVG pages to PDF."""
    import cairosvg
    import verovio
    from pypdf import PdfReader, PdfWriter

    # The wheel bundles SMuFL fonts in verovio/data, but some CI/container
    # layouts do not resolve the default resource path correctly. Initialize
    # without implicit font loading and point Verovio at its packaged assets.
    toolkit = verovio.toolkit(False)
    resource_path = Path(verovio.__file__).resolve().parent / "data"
    if not resource_path.is_dir() or not toolkit.setResourcePath(str(resource_path)):
        raise ValueError(f"Verovio font resources are unavailable at {resource_path}")
    toolkit.setOptions(
        {
            "inputFrom": "xml",
            "pageWidth": 2970,
            "pageHeight": 2100,
            # Short drum arrangements often contain only one percussion staff.
            # The default 100% scale leaves that single system very small on A4.
            # Use a larger engraving scale for a readable single-system score.
            # Vertical justification spreads sparse systems over the full page and
            # creates large empty regions, so leave system placement natural.
            "scale": 180,
            "unit": 12,
            "justifyVertically": False,
            "breaks": "auto",
        }
    )
    if measures_per_system not in {4, 5}:
        raise ValueError("measures_per_system must be 4 or 5")

    # Verovio's SMuFL metronome-note glyph is missing in some packaged font
    # sets. Preserve the exact tempo in PDF as readable text while keeping the
    # MusicXML download's semantic metronome marking untouched.
    score_root = ET.fromstring(performance_to_musicxml(performance))
    # Explicit MusicXML system breaks keep each printed line to four or five bars.
    _apply_system_breaks(score_root, measures_per_system)
    for metronome in score_root.findall(".//metronome"):
        direction_type = next(
            (parent for parent in score_root.iter() if metronome in list(parent)),
            None,
        )
        if direction_type is None:
            continue
        per_minute = metronome.findtext("per-minute", "120")
        direction_type.remove(metronome)
        ET.SubElement(direction_type, "words").text = f"Tempo: {per_minute} BPM"
    score_xml = ET.tostring(score_root, encoding="unicode")
    if not toolkit.loadData(score_xml):
        raise ValueError("Verovio could not load the generated drum MusicXML.")
    page_count = toolkit.getPageCount()
    if page_count < 1:
        raise ValueError("Verovio produced no pages for the drum score.")

    writer = PdfWriter()
    for page_number in range(1, page_count + 1):
        svg = toolkit.renderToSVG(page_number)
        if not svg:
            raise ValueError(f"Verovio failed to render score page {page_number}.")
        # Normalize SVG pixels to landscape A4 PDF points at CairoSVG 96 DPI.
        page_pdf = cairosvg.svg2pdf(
            bytestring=svg.encode("utf-8"),
            output_width=PAGE_W * 96.0 / 72.0,
            output_height=PAGE_H * 96.0 / 72.0,
        )
        writer.append_pages_from_reader(PdfReader(BytesIO(page_pdf)))
    writer.add_metadata({"/Title": title, "/Author": "DrumAI Studio"})
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def _render_fallback_pdf(
    performance: DrumPerformance, title: str = "DrumAI Studio — Drum Score",
    measures_per_system: int = MEASURES_PER_SYSTEM,
) -> bytes:
    """Render a dependency-light emergency score if the engraving stack is absent."""
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=landscape(A4), pageCompression=1)
    pdf.setTitle(title)
    pdf.setAuthor("DrumAI Studio")
    if measures_per_system not in {4, 5}:
        raise ValueError("measures_per_system must be 4 or 5")
    changes = _tempo_changes(performance)
    bars = _measure_boundaries(performance, changes)
    event_beats = [
        (event, _seconds_to_quarters(event.time_seconds, changes))
        for event in performance.events
    ]
    # Reserve a dedicated left gutter for system labels and meter information.
    # The old layout started the staff only 24pt from the page edge, placing
    # "System", "Drums", bar numbers and the time signature on top of staff lines.
    x0 = LEFT + 58
    usable_width = PAGE_W - RIGHT - x0
    measure_width = (usable_width - (measures_per_system - 1) * MEASURE_GAP) / measures_per_system
    page_system = 0

    for system_index in range(0, len(bars), measures_per_system):
        if page_system == 0:
            pdf.setFont("Helvetica-Bold", 16)
            pdf.drawString(LEFT, PAGE_H - 32, title[:90])
            pdf.setFont("Helvetica", 8)
            first = changes[0]
            pdf.drawString(LEFT, PAGE_H - 46, f"Tempo: {first.bpm:g} BPM    Meter: {first.numerator}/{first.denominator}    Duration: {performance.duration_seconds:.1f}s")
            pdf.drawRightString(PAGE_W - RIGHT, PAGE_H - 46, f"{len(performance.events)} drum events")
        top = PAGE_H - 76 - page_system * SYSTEM_HEIGHT
        staff_mid = top - 48
        pdf.setFont("Helvetica-Bold", 8)
        pdf.drawString(LEFT, staff_mid + 39, f"System {system_index // measures_per_system + 1}")
        # Keep the time signature in the left gutter, not over the first bar.
        first_bar = bars[system_index]
        pdf.setFont("Helvetica", 8)
        pdf.drawString(LEFT + 4, staff_mid + 22, f"{first_bar[2]}/{first_bar[3]}")
        # Five-line percussion staff.
        for line in range(5):
            y = staff_mid + (line - 2) * STAFF_SPACING
            pdf.setLineWidth(0.55)
            pdf.line(x0, y, PAGE_W - RIGHT, y)
        system_bars = bars[system_index:system_index + measures_per_system]
        for local_index, (bar_start, bar_end, numerator, denominator) in enumerate(system_bars):
            bx = x0 + local_index * (measure_width + MEASURE_GAP)
            pdf.setFont("Helvetica", 8)
            # Bar numbers sit above the staff, with enough clearance for note stems.
            pdf.drawString(bx + 3, staff_mid + 34, f"{system_index + local_index + 1}")
            pdf.setLineWidth(0.7)
            pdf.line(bx, staff_mid - 22, bx, staff_mid + 22)
            pdf.line(bx + measure_width, staff_mid - 22, bx + measure_width, staff_mid + 22)
            # Time-signature changes are annotated above the affected measure.
            # The initial signature is already printed in the dedicated gutter.
            if local_index > 0 and (numerator, denominator) != (system_bars[local_index - 1][2], system_bars[local_index - 1][3]):
                pdf.setFont("Helvetica", 7)
                pdf.drawString(bx + 4, staff_mid + 23, f"{numerator}/{denominator}")
            for event, beat in event_beats:
                if bar_start - 1e-8 <= beat < bar_end - 1e-8:
                    ratio = (beat - bar_start) / max(bar_end - bar_start, 1e-8)
                    x = bx + 5 + ratio * (measure_width - 10)
                    y = staff_mid + INSTRUMENT_Y[event.instrument] * (STAFF_SPACING / 2)
                    _draw_note(pdf, x, y, event.instrument, event.velocity)
        # Footer legend uses all instrument types actually present.
        if system_index + measures_per_system >= len(bars) or page_system == SYSTEMS_PER_PAGE - 1:
            present = sorted({event.instrument for event in performance.events}, key=lambda item: item.value)
            legend = "   •   ".join(LABELS[item] for item in present) or "No detected drum events"
            pdf.setFont("Helvetica", 7)
            pdf.drawString(LEFT, 22, f"Legend: {legend[:150]}")
            pdf.drawRightString(PAGE_W - RIGHT, 22, "Generated from the latest editable drum events")
        page_system += 1
        if page_system >= SYSTEMS_PER_PAGE and system_index + measures_per_system < len(bars):
            pdf.showPage()
            page_system = 0
    if not bars:
        pdf.setFont("Helvetica", 12)
        pdf.drawString(LEFT, PAGE_H - 90, "No measures or drum events to display.")
    pdf.save()
    return buffer.getvalue()


def performance_to_pdf(
    performance: DrumPerformance, title: str = "DrumAI Studio — Drum Score",
    measures_per_system: int = 4,
) -> bytes:
    """Return a professionally engraved, printable PDF from canonical drum events.

    Verovio is the primary engraving engine. The ReportLab fallback keeps
    minimal installations usable, but production installs include Verovio.
    """
    try:
        return _render_with_verovio(performance, title, measures_per_system)
    except ImportError as exc:
        missing = exc.name or "engraving dependency"
        if missing not in {"verovio", "cairosvg", "pypdf"}:
            raise
        return _render_fallback_pdf(performance, title, measures_per_system)
    except (ValueError, RuntimeError):
        # Verovio can be installed while its SMuFL font resources are absent
        # from a minimal container. Keep exports usable through the fallback.
        return _render_fallback_pdf(performance, title, measures_per_system)
