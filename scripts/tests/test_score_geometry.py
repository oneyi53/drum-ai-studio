"""Tests for scripts/score_geometry.py (first-system height gate).

Synthetic images only: the CI evaluation job installs pytest, pretty-midi
and pillow, but no backend or Verovio, so no real renders are used here.
The live check on a real render is scripts/api_engine_smoke.py itself,
which runs in the engine-validation workflow.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from score_geometry import FIRST_SYSTEM_MIN_HEIGHT_RATIO, first_system_height_ratio

PAGE_WIDTH = 1404
PAGE_HEIGHT = 993


def _blank_page() -> Image.Image:
    return Image.new("RGB", (PAGE_WIDTH, PAGE_HEIGHT), "white")


def _draw_staff(draw: ImageDraw.ImageDraw, top: int, spacing: int = 11) -> None:
    """Five 2px staff lines spanning the system width."""
    for line in range(5):
        y = top + line * spacing
        draw.rectangle([60, y, 1340, y + 1], fill="black")


def _draw_tempo_text(draw: ImageDraw.ImageDraw, top: int = 24) -> None:
    """A solid block standing in for the 'Tempo: 120 BPM' text."""
    draw.rectangle([100, top, 300, top + 20], fill="black")


def test_blank_page_returns_none() -> None:
    assert first_system_height_ratio(_blank_page()) is None


def test_scattered_ink_without_staff_returns_none() -> None:
    image = _blank_page()
    draw = ImageDraw.Draw(image)
    # A few noteheads but no staff lines: no system to locate.
    for x in (200, 500, 900):
        draw.rectangle([x, 200, x + 12, 212], fill="black")
    assert first_system_height_ratio(image) is None


def test_single_system_height() -> None:
    image = _blank_page()
    draw = ImageDraw.Draw(image)
    _draw_tempo_text(draw)
    _draw_staff(draw, top=89)
    # Stems hanging below the staff, as in a real groove.
    draw.rectangle([200, 100, 201, 160], fill="black")
    draw.rectangle([600, 100, 601, 160], fill="black")
    ratio = first_system_height_ratio(image)
    assert ratio is not None
    assert ratio == (160 - 24 + 1) / PAGE_HEIGHT
    assert ratio >= FIRST_SYSTEM_MIN_HEIGHT_RATIO


def test_two_systems_measures_first_only() -> None:
    image = _blank_page()
    draw = ImageDraw.Draw(image)
    _draw_tempo_text(draw)
    _draw_staff(draw, top=89)
    draw.rectangle([200, 100, 201, 160], fill="black")
    _draw_staff(draw, top=300)
    draw.rectangle([200, 310, 201, 370], fill="black")
    ratio = first_system_height_ratio(image)
    assert ratio is not None
    # First system only: 24..160, not the whole page down to 370.
    assert ratio == (160 - 24 + 1) / PAGE_HEIGHT


def test_tempo_text_gap_does_not_split_system() -> None:
    image = _blank_page()
    draw = ImageDraw.Draw(image)
    _draw_tempo_text(draw)
    # No stems bridging the tempo text and the staff: a 44px blank band
    # sits between them, wider than the system-gap threshold. The first
    # system must still span tempo text to staff bottom, because the
    # terminating gap is only searched for *below* the first staff line.
    _draw_staff(draw, top=89)
    draw.rectangle([200, 120, 212, 132], fill="black")  # a notehead on the staff
    ratio = first_system_height_ratio(image)
    assert ratio is not None
    assert ratio == (134 - 24 + 1) / PAGE_HEIGHT
    assert ratio >= FIRST_SYSTEM_MIN_HEIGHT_RATIO


def test_sparse_single_system_passes_threshold() -> None:
    image = _blank_page()
    draw = ImageDraw.Draw(image)
    _draw_tempo_text(draw)
    _draw_staff(draw, top=57)
    draw.rectangle([200, 70, 201, 120], fill="black")
    ratio = first_system_height_ratio(image)
    assert ratio is not None
    assert ratio == (120 - 24 + 1) / PAGE_HEIGHT
    assert ratio >= FIRST_SYSTEM_MIN_HEIGHT_RATIO


def test_squashed_system_fails_threshold() -> None:
    image = _blank_page()
    draw = ImageDraw.Draw(image)
    _draw_tempo_text(draw, top=10)
    # Staff squeezed to ~4px line spacing: a broken engraving scale.
    _draw_staff(draw, top=40, spacing=4)
    draw.rectangle([200, 44, 201, 60], fill="black")
    ratio = first_system_height_ratio(image)
    assert ratio is not None
    assert ratio == (60 - 10 + 1) / PAGE_HEIGHT
    assert ratio < FIRST_SYSTEM_MIN_HEIGHT_RATIO


def test_threshold_sits_below_smallest_known_good_render() -> None:
    # Smallest first-system height measured on a known-good render is
    # 9.8% (single-system sparse score); the threshold must stay clearly
    # below it or the gate can false-fail a correct short score again.
    assert FIRST_SYSTEM_MIN_HEIGHT_RATIO < 0.098 * 0.75
