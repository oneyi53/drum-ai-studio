"""Beat This! tempo correction for the transcription path.

The stock DrumScript tempo estimator (librosa tempogram peak-pick, 60-240
BPM, no octave disambiguation) octave-errors on real songs: rock comes out
at 69.8 BPM against a true ~140, electronic at 215.3 against ~108. A wrong
tempo puts the whole 16th-note quantization grid on the wrong lattice, so
every downstream F1 is capped before a single note is classified.

Beat This! (CPJKU, ISMIR 2024, MIT code + weights) is a Transformer
beat/downbeat tracker. It does not output a tempo directly, so the tempo is
derived from its beat track with a longest-strong-IOI-mode rule: histogram
the inter-beat intervals in 0.05 s bins over [0.15, 1.5] s; the dominant
mode is usually an 8th-note subdivision, and the true beat period is the
longest mode that still has real mass (>= max(8, 10% of the dominant mode)
and a center within [1.7x, 2.3x] of the dominant center, i.e. a true
subdivision, not a section gap). The period is refined with the median IOI
within +/-0.05 s of the picked center.

Measured 2026-11-14 (18 tracks: 6 real songs + 12 IDMT): the fused tempo
is within 5% of the reference on 18/18, against 10/18 for the stock
estimator. Beat This! alone is right on 17/17 tracks where it produces a
tempo; the 18th (electronic, 11 beats in 150 s) falls back to the stock
tempo folded into [60, 180] (215.3 -> 107.7, true ~108).

The ``beat_this`` package and its ~81 MB checkpoint are optional: nothing
in this module imports them at import time. ``correct_tempo_map`` returns
the original tempo map unchanged (source ``"unavailable"``) when the
checkpoint is missing, the package is not installed, or inference raises.
Install the package (e.g. ``pip install git+https://github.com/CPJKU/beat_this``)
and set ``BEAT_THIS_CHECKPOINT`` to the ``final0.ckpt`` checkpoint to
enable it. The checkpoint is never committed to the repo.
"""

from __future__ import annotations

import itertools
import os
import statistics
from collections.abc import Sequence
from pathlib import Path

from .drum_events import TempoChange

BEAT_THIS_CHECKPOINT_ENV = "BEAT_THIS_CHECKPOINT"

# IOI histogram for the longest-strong-mode tempo derivation.
_IOI_MIN_SECONDS = 0.15
_IOI_MAX_SECONDS = 1.5
_BIN_WIDTH_SECONDS = 0.05
_MIN_BEATS = 8
# A longer mode must hold at least this fraction of the dominant mode's
# mass (and at least _MIN_BEATS intervals) to count as a real subdivision.
_LONG_MODE_MIN_FRACTION = 0.10
# ... and its center must sit near 2x the dominant center.
_LONG_MODE_RATIO_MIN = 1.7
_LONG_MODE_RATIO_MAX = 2.3

# Range the stock estimator's tempo is folded into when Beat This! runs
# but finds no usable beat track (its near-silence is evidence the stock
# value is an octave error, e.g. electronic 215.3 -> 107.7).
_FALLBACK_TEMPO_LOW_BPM = 60.0
_FALLBACK_TEMPO_HIGH_BPM = 180.0
_DEFAULT_FALLBACK_BPM = 120.0


def beat_tempo_from_beats(beats: Sequence[float]) -> float | None:
    """Derive a tempo (BPM) from Beat This! beat times, or None.

    Returns None when the beat track is too sparse to support a tempo
    (fewer than 8 beats or fewer than 8 inter-beat intervals in range).
    Pure Python so the API image needs no numpy for this derivation.
    """
    times = sorted(float(b) for b in beats)
    if len(times) < _MIN_BEATS:
        return None
    iois = [b - a for a, b in itertools.pairwise(times)]
    iois = [t for t in iois if _IOI_MIN_SECONDS <= t <= _IOI_MAX_SECONDS]
    if len(iois) < _MIN_BEATS:
        return None
    n_bins = round((_IOI_MAX_SECONDS + _BIN_WIDTH_SECONDS - _IOI_MIN_SECONDS) / _BIN_WIDTH_SECONDS)
    counts = [0] * n_bins
    for interval in iois:
        index = min(n_bins - 1, int((interval - _IOI_MIN_SECONDS) / _BIN_WIDTH_SECONDS))
        counts[index] += 1
    centers = [_IOI_MIN_SECONDS + (i + 0.5) * _BIN_WIDTH_SECONDS for i in range(n_bins)]
    dominant = max(range(n_bins), key=lambda i: counts[i])
    threshold = max(_MIN_BEATS, _LONG_MODE_MIN_FRACTION * counts[dominant])
    pick = dominant
    for i in range(dominant + 1, n_bins):
        if counts[i] >= threshold and (
            _LONG_MODE_RATIO_MIN * centers[dominant]
            <= centers[i]
            <= _LONG_MODE_RATIO_MAX * centers[dominant]
        ):
            pick = i  # keep scanning: the longest qualifying mode wins
    near = [t for t in iois if abs(t - centers[pick]) <= _BIN_WIDTH_SECONDS]
    period = statistics.median(near) if near else centers[pick]
    return 60.0 / period


def fold_tempo_into_range(
    bpm: float,
    low: float = _FALLBACK_TEMPO_LOW_BPM,
    high: float = _FALLBACK_TEMPO_HIGH_BPM,
) -> float:
    """Halve/double a tempo until it lands in [low, high] (octave folding)."""
    bpm = float(bpm)
    while bpm > high:
        bpm /= 2.0
    while bpm < low:
        bpm *= 2.0
    return bpm


def fuse_tempo(beat_this_bpm: float | None, fallback_bpm: float) -> tuple[float, str]:
    """Prefer Beat This! when it produced a tempo; else fold the fallback."""
    if beat_this_bpm is not None:
        return float(beat_this_bpm), "beat_this"
    return fold_tempo_into_range(fallback_bpm), "fallback"


def resolve_checkpoint(explicit: Path | str | None = None) -> Path | None:
    """Return the Beat This! checkpoint path, or None when unavailable.

    An explicit path wins; otherwise ``BEAT_THIS_CHECKPOINT`` is read. A
    path that does not exist on disk does not count.
    """
    candidates: list[Path] = []
    if explicit is not None:
        candidates.append(Path(explicit))
    env_path = os.environ.get(BEAT_THIS_CHECKPOINT_ENV)
    if env_path:
        candidates.append(Path(env_path))
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def correct_tempo_map(
    tempo_map: Sequence[TempoChange],
    audio_path: Path,
    checkpoint: Path | str | None = None,
) -> tuple[list[TempoChange], str]:
    """Replace a tempo map with the Beat This! fused tempo.

    Runs Beat This! on the original audio (pre-EQ) and returns a single
    tempo change at t=0 with the fused BPM, plus the source:
    ``"beat_this"`` (Beat This! produced a tempo), ``"fallback"`` (it ran
    but found no usable beat track, so the stock tempo was octave-folded),
    or ``"unavailable"`` (no checkpoint / package missing / inference
    failed — the original map is returned unchanged).
    """
    existing = list(tempo_map)
    fallback_bpm = existing[0].bpm if existing else _DEFAULT_FALLBACK_BPM
    numerator = existing[0].numerator if existing else 4
    denominator = existing[0].denominator if existing else 4
    resolved = resolve_checkpoint(checkpoint)
    if resolved is None:
        return existing, "unavailable"
    try:
        from beat_this.inference import File2Beats

        beats, _downbeats = File2Beats(checkpoint_path=str(resolved), device="cpu", dbn=False)(
            str(audio_path)
        )
    except Exception:  # noqa: BLE001 - any Beat This! failure fails closed
        # to the stock tempo: a missing package, an unreadable file, a
        # model error, or an inference crash must never break transcription.
        return existing, "unavailable"
    beat_this_bpm = beat_tempo_from_beats(beats)
    fused_bpm, source = fuse_tempo(beat_this_bpm, fallback_bpm)
    return (
        [
            TempoChange(
                time_seconds=0.0,
                bpm=fused_bpm,
                numerator=numerator,
                denominator=denominator,
            )
        ],
        source,
    )
