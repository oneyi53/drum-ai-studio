"""Tests for the Beat This! tempo correction (app.beat_this_tempo)."""

from __future__ import annotations

import os
from itertools import accumulate
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.beat_this_tempo import (
    beat_tempo_from_beats,
    correct_tempo_map,
    fold_tempo_into_range,
    fuse_tempo,
    resolve_checkpoint,
)
from app.drum_events import TempoChange


def _beats_from_iois(iois: list[float]) -> list[float]:
    return [0.0, *accumulate(iois)]


def test_beat_tempo_steady_beats():
    beats = [i * (60.0 / 140.0) for i in range(25)]
    assert beat_tempo_from_beats(beats) == pytest.approx(140.0, rel=0.01)


def test_beat_tempo_subdivided_beats_pick_longer_mode():
    # Rock-like: Beat This! fires on 8ths most of the time (24 IOIs at
    # 0.214 s) but the quarter grid (15 IOIs at 0.429 s) is the true beat.
    iois = [60.0 / 280.0] * 24 + [60.0 / 140.0] * 15
    assert beat_tempo_from_beats(_beats_from_iois(iois)) == pytest.approx(140.0, rel=0.01)


def test_beat_tempo_blues_like_bimodal():
    iois = [0.34] * 20 + [0.68] * 15
    assert beat_tempo_from_beats(_beats_from_iois(iois)) == pytest.approx(88.24, rel=0.01)


def test_beat_tempo_too_sparse_returns_none():
    assert beat_tempo_from_beats([]) is None
    assert beat_tempo_from_beats([0.0, 0.5, 1.0, 1.5, 2.0]) is None
    # Ten beats, but every IOI is outside the [0.15, 1.5] s window.
    assert beat_tempo_from_beats([i * 2.0 for i in range(10)]) is None


def test_fold_tempo_into_range():
    assert fold_tempo_into_range(215.33203125) == pytest.approx(107.666015625)
    # Already in range: untouched (69.8 is only fixed when Beat This!
    # itself produces a tempo; folding never invents a new octave).
    assert fold_tempo_into_range(69.83741554054055) == pytest.approx(69.83741554054055)
    assert fold_tempo_into_range(85.0) == pytest.approx(85.0)
    assert fold_tempo_into_range(30.0) == pytest.approx(60.0)
    assert fold_tempo_into_range(400.0) == pytest.approx(100.0)


def test_fuse_tempo_prefers_beat_this():
    bpm, source = fuse_tempo(142.857, 69.8)
    assert bpm == pytest.approx(142.857)
    assert source == "beat_this"
    bpm, source = fuse_tempo(None, 215.33203125)
    assert bpm == pytest.approx(107.666015625)
    assert source == "fallback"
    bpm, source = fuse_tempo(None, 86.13)
    assert bpm == pytest.approx(86.13)
    assert source == "fallback"


def test_resolve_checkpoint_explicit_and_env(tmp_path, monkeypatch):
    # The env var must not leak into the explicit-path assertions.
    monkeypatch.delenv("BEAT_THIS_CHECKPOINT", raising=False)
    checkpoint = tmp_path / "final0.ckpt"
    checkpoint.write_bytes(b"fake")
    assert resolve_checkpoint(checkpoint) == checkpoint
    assert resolve_checkpoint(tmp_path / "missing.ckpt") is None
    monkeypatch.setenv("BEAT_THIS_CHECKPOINT", str(checkpoint))
    assert resolve_checkpoint() == checkpoint
    monkeypatch.delenv("BEAT_THIS_CHECKPOINT")
    assert resolve_checkpoint() is None


def _install_fake_beat_this(monkeypatch, beats=None, error=None):
    """Stub ``beat_this.inference.File2Beats`` in sys.modules."""

    class FakeFile2Beats:
        def __init__(self, checkpoint_path=None, device=None, dbn=None):
            self.checkpoint_path = checkpoint_path

        def __call__(self, path):
            if error is not None:
                raise error
            return beats, []

    import sys

    fake_inference = SimpleNamespace(File2Beats=FakeFile2Beats)
    monkeypatch.setitem(sys.modules, "beat_this", SimpleNamespace(inference=fake_inference))
    monkeypatch.setitem(sys.modules, "beat_this.inference", fake_inference)


def test_correct_tempo_map_unavailable_without_checkpoint(tmp_path, monkeypatch):
    monkeypatch.delenv("BEAT_THIS_CHECKPOINT", raising=False)
    original = [TempoChange(time_seconds=0.0, bpm=69.8)]
    result, source = correct_tempo_map(original, tmp_path / "song.mp3")
    assert result == original
    assert source == "unavailable"


def test_correct_tempo_map_uses_beat_this(tmp_path, monkeypatch):
    checkpoint = tmp_path / "final0.ckpt"
    checkpoint.write_bytes(b"fake")
    iois = [60.0 / 280.0] * 24 + [60.0 / 140.0] * 15
    _install_fake_beat_this(monkeypatch, beats=_beats_from_iois(iois))
    original = [TempoChange(time_seconds=0.0, bpm=69.8, numerator=3, denominator=4)]
    result, source = correct_tempo_map(original, tmp_path / "song.mp3", checkpoint)
    assert source == "beat_this"
    assert len(result) == 1
    assert result[0].time_seconds == 0.0
    assert result[0].bpm == pytest.approx(140.0, rel=0.01)
    # Meter is preserved from the original map.
    assert (result[0].numerator, result[0].denominator) == (3, 4)


def test_correct_tempo_map_fallback_when_beat_this_silent(tmp_path, monkeypatch):
    checkpoint = tmp_path / "final0.ckpt"
    checkpoint.write_bytes(b"fake")
    _install_fake_beat_this(monkeypatch, beats=[0.0, 1.0, 2.0])
    original = [TempoChange(time_seconds=0.0, bpm=215.33203125)]
    result, source = correct_tempo_map(original, tmp_path / "song.mp3", checkpoint)
    assert source == "fallback"
    assert result[0].bpm == pytest.approx(107.666015625)


def test_correct_tempo_map_returns_original_on_inference_error(tmp_path, monkeypatch):
    checkpoint = tmp_path / "final0.ckpt"
    checkpoint.write_bytes(b"fake")
    _install_fake_beat_this(monkeypatch, error=RuntimeError("model exploded"))
    original = [TempoChange(time_seconds=0.0, bpm=69.8)]
    result, source = correct_tempo_map(original, tmp_path / "song.mp3", checkpoint)
    assert result == original
    assert source == "unavailable"


@pytest.mark.skipif(
    not os.environ.get("BEAT_THIS_CHECKPOINT")
    or not Path(os.environ["BEAT_THIS_CHECKPOINT"]).is_file()
    or not os.environ.get("BEAT_THIS_ROCK_AUDIO")
    or not Path(os.environ["BEAT_THIS_ROCK_AUDIO"]).is_file(),
    reason=(
        "requires Beat This! checkpoint + rock audio; "
        "set BEAT_THIS_CHECKPOINT and BEAT_THIS_ROCK_AUDIO"
    ),
)
def test_correct_tempo_map_real_rock_audio():
    """Real-audio check: rock fuses to ~140 BPM (stock says 69.8)."""
    pytest.importorskip("beat_this")
    checkpoint = Path(os.environ["BEAT_THIS_CHECKPOINT"])
    audio = Path(os.environ["BEAT_THIS_ROCK_AUDIO"])
    original = [TempoChange(time_seconds=0.0, bpm=69.8)]
    result, source = correct_tempo_map(original, audio, checkpoint)
    assert source == "beat_this"
    assert result[0].bpm == pytest.approx(140.0, rel=0.05)
