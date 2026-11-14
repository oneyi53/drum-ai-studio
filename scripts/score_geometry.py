"""Measure the rendered height of the first staff system of a score page.

The API engine smoke used to gate on the whole-page ink bounding box:
the vertical extent of *all* ink on the page had to be at least 15% of the
page height. That conflates "the score is vertically compressed" with
"the score has few systems": a correct single-system short score measures
only 9.8-11.3% that way (and the smoke itself passed at 16.0% only because
one low rest glyph extends the box), so the gate could false-fail a
correct short score.

This module measures the first system only: from the first ink row on the
page (the tempo text sits above the first staff) down to the last ink row
before the first wide blank band below the first staff. The staff scale is
constant across scores, so the value is stable (9.8-16.0% on the known
good renders) while still catching an empty page or a squashed engraving.
"""

from __future__ import annotations

from PIL import Image

# A pixel counts as ink when it is darker than this grayscale value.
INK_THRESHOLD = 210
# The top 80% of the page is measured; the footer/engraver mark below it
# is excluded, as before.
MEASURED_REGION_FRACTION = 0.80
# A row is a staff line when its ink spans at least this fraction of the
# page width (staff lines run the full system width; beams, text and
# noteheads are much narrower).
STAFF_LINE_MIN_WIDTH_FRACTION = 0.40
# A blank band ends the first system when it is at least this fraction of
# the page height (about 25 px at the smoke render scale). Measured gaps:
# inter-system gaps are ~5.5% of page height, within-system blank runs
# are <1%, so 2.5% sits well between the two.
SYSTEM_GAP_MIN_FRACTION = 0.025
SYSTEM_GAP_MIN_PX = 8
# Smallest first-system height measured on a known-good render is 9.8%
# (single-system sparse score); 6% keeps ~40% margin below it while
# catching an empty page or an engraving squashed to ~60% scale or less.
FIRST_SYSTEM_MIN_HEIGHT_RATIO = 0.06


def _row_ink_counts(grayscale: Image.Image) -> list[int]:
    """Per-row count of ink pixels in the measured (top) region."""
    width, height = grayscale.size
    region_height = int(height * MEASURED_REGION_FRACTION)
    pixels = grayscale.load()
    counts: list[int] = []
    for y in range(region_height):
        count = 0
        for x in range(width):
            if pixels[x, y] < INK_THRESHOLD:
                count += 1
        counts.append(count)
    return counts


def first_system_height_ratio(image: Image.Image) -> float | None:
    """Height of the first staff system as a fraction of the page height.

    Returns ``None`` when no first staff system can be located (blank page
    or no detectable staff lines), so the caller can fail loudly instead
    of passing a render with no readable score.
    """
    grayscale = image.convert("L")
    width, height = grayscale.size
    counts = _row_ink_counts(grayscale)
    ink_rows = [y for y, count in enumerate(counts) if count > 0]
    if not ink_rows:
        return None
    staff_top = next(
        (
            y
            for y, count in enumerate(counts)
            if count > STAFF_LINE_MIN_WIDTH_FRACTION * width
        ),
        None,
    )
    if staff_top is None:
        return None
    gap_min = max(SYSTEM_GAP_MIN_PX, round(SYSTEM_GAP_MIN_FRACTION * height))
    first_ink = ink_rows[0]
    last_ink = ink_rows[-1]
    blank_run = 0
    for y in range(staff_top, len(counts)):
        if counts[y] == 0:
            blank_run += 1
            if blank_run >= gap_min:
                last_ink = y - gap_min
                # Back up over any zero rows just before the run so the
                # bottom lands on the last ink row of the system.
                while last_ink > first_ink and counts[last_ink] == 0:
                    last_ink -= 1
                break
        else:
            blank_run = 0
    return (last_ink - first_ink + 1) / height
