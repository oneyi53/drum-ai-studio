"""Optional DrumScript inference adapter for the API worker.

The heavy DrumScript/PyTorch dependency is loaded lazily so the API can start
and serve uploads/status endpoints even when the engine extra is not installed.
"""
from __future__ import annotations

import importlib
import json
import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from .drum_events import DrumPerformance
from .midi_adapter import midi_to_performance


class EngineUnavailableError(RuntimeError):
    """Raised when the optional transcription runtime is not installed."""


class EngineOutputError(RuntimeError):
    """Raised when DrumScript does not produce a usable MIDI artifact."""


# Upstream DrumScript rule (drumscript/drum_classifier/classify.py, live
# `classify_events` path): an onset is a kick iff
#   lfer >= KICK_LFER_MIN and KICK_FREQ_MIN <= peak_freq <= KICK_FREQ_MAX.
# The classifier lives upstream only; this repo does not vendor it (see
# docs/P0_AUDIT.md). IDMT-SMT-Drums diagnostics show the upstream gate is
# the bottleneck: onset-candidate recall for kick is ~98% while final kick
# recall is 5.3% (RealDrum) / 17.2% (WaveDrum) / 57.1% (TechnoDrum), so
# missed kicks are lost at classification, not at onset detection.
# Feature split of reference-aligned candidates (40 tracks, 947 candidates):
# missed kicks have LFER median 0.18-0.21 (p75 0.21-0.28) while the gate
# sits at 0.32; their peak frequency (median 43-86 Hz) already passes the
# 40-140 Hz range, so the LFER gate alone is the defect.
UPSTREAM_KICK_LFER_MIN = 0.32
UPSTREAM_KICK_FREQ_MIN_HZ = 40.0
UPSTREAM_KICK_FREQ_MAX_HZ = 140.0

# Measured default (2026-11-13, IDMT-SMT-Drums V2, 50 ms tolerance):
# lfer_min 0.10 lifts pooled kick recall 0.25 -> 0.84 at pooled precision
# 0.89 -> 0.84 (F1 0.39 -> 0.84) over 55 tuning tracks (969 refs), and
# holds up on 15 held-out WaveDrum tracks (recall 0.24 -> 0.55, precision
# 0.83 -> 0.77, F1 0.37 -> 0.64). lfer_min 0.15 is the conservative
# alternative (pooled F1 0.79). Pass an explicit
# KickClassificationConfig(lfer_min=0.32) to restore the stock upstream
# rule. See docs/ENGINE_VALIDATION.md.
DEFAULT_KICK_LFER_MIN = 0.10


@dataclass(frozen=True)
class KickClassificationConfig:
    """Kick gate overrides applied to the upstream DrumScript classifier.

    Values are validated ranges, not free-form knobs: lowering ``lfer_min``
    recovers kicks whose low-frequency energy share is diluted by bass or
    mix energy, at the cost of bass-guitar / low-tom false positives.
    The default (``lfer_min=0.10``) is the measured optimum on IDMT-SMT-Drums
    (see module comment); pass ``lfer_min=0.32`` explicitly for the stock
    upstream rule.
    """

    lfer_min: float = DEFAULT_KICK_LFER_MIN
    peak_freq_min_hz: float = UPSTREAM_KICK_FREQ_MIN_HZ
    peak_freq_max_hz: float = UPSTREAM_KICK_FREQ_MAX_HZ

    def __post_init__(self) -> None:
        if not 0.0 <= self.lfer_min <= 1.0:
            raise ValueError(f"lfer_min must be within [0, 1], got {self.lfer_min}")
        if not 0.0 < self.peak_freq_min_hz < self.peak_freq_max_hz:
            raise ValueError(
                "peak frequency range must satisfy 0 < min < max, got "
                f"({self.peak_freq_min_hz}, {self.peak_freq_max_hz})"
            )

    @property
    def is_upstream_default(self) -> bool:
        return (
            self.lfer_min == UPSTREAM_KICK_LFER_MIN
            and self.peak_freq_min_hz == UPSTREAM_KICK_FREQ_MIN_HZ
            and self.peak_freq_max_hz == UPSTREAM_KICK_FREQ_MAX_HZ
        )


# Module attributes the upstream classifier reads as globals at call time.
# `classify_events` does `from ...constants import KICK_LFER_MIN, ...`, so
# patching the constants module alone would NOT change its behaviour; the
# bindings live on `drumscript.drum_classifier.classify` itself.
_KICK_THRESHOLD_ATTRS = (
    ("KICK_LFER_MIN", "lfer_min"),
    ("KICK_FREQ_MIN", "peak_freq_min_hz"),
    ("KICK_FREQ_MAX", "peak_freq_max_hz"),
)


@contextmanager
def _override_kick_thresholds(
    config: KickClassificationConfig,
) -> Iterator[None]:
    """Temporarily set upstream kick thresholds; always restore them.

    A no-op when the config equals the stock upstream rule, so explicitly
    requesting upstream behaviour never depends on upstream module internals.
    Any other config fails closed if the installed DrumScript revision does
    not expose the expected attributes, instead of silently running with the
    stock gate.
    """
    if config.is_upstream_default:
        yield
        return
    try:
        classify_module = importlib.import_module("drumscript.drum_classifier.classify")
    except ImportError as exc:
        raise EngineUnavailableError(
            "cannot apply kick threshold override: drumscript.drum_classifier.classify "
            "is not importable"
        ) from exc
    missing = [attr for attr, _ in _KICK_THRESHOLD_ATTRS if not hasattr(classify_module, attr)]
    if missing:
        raise EngineUnavailableError(
            "cannot apply kick threshold override: installed DrumScript does not "
            f"expose {', '.join(missing)}; refusing to run with unapplied config"
        )
    originals = {attr: getattr(classify_module, attr) for attr, _ in _KICK_THRESHOLD_ATTRS}
    try:
        for attr, field in _KICK_THRESHOLD_ATTRS:
            setattr(classify_module, attr, getattr(config, field))
        yield
    finally:
        for attr, value in originals.items():
            setattr(classify_module, attr, value)


def audio_duration_seconds(audio_path: Path) -> float:
    """Read the source duration with ffprobe; fail closed if unavailable."""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise EngineUnavailableError(
            "ffprobe is required for analysis; install FFmpeg in the API worker image"
        )
    result = subprocess.run(
        [
            ffprobe,
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "json",
            str(audio_path),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    try:
        duration = float(json.loads(result.stdout)["format"]["duration"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise EngineOutputError("ffprobe did not return a valid audio duration") from exc
    if duration <= 0:
        raise EngineOutputError("source audio duration must be positive")
    return duration


class DrumScriptEngine:
    """Run a full-song DrumScript transcription and normalize its MIDI output.

    ``kick_config`` overrides the upstream kick classification gate for this
    engine instance only (module attributes are restored after each call).
    The default applies the measured ``lfer_min=0.10`` gate; pass an
    explicit upstream config for stock DrumScript behaviour.
    """

    def __init__(self, kick_config: KickClassificationConfig | None = None) -> None:
        self.kick_config = kick_config or KickClassificationConfig()

    def analyze(self, audio_path: Path, output_dir: Path) -> tuple[DrumPerformance, Path]:
        audio_path = audio_path.resolve()
        if not audio_path.is_file():
            raise FileNotFoundError(audio_path)
        try:
            engine = importlib.import_module("drumscript")
        except ImportError as exc:
            raise EngineUnavailableError(
                "DrumScript is not installed in this API worker; install the engine runtime"
            ) from exc

        output_dir.mkdir(parents=True, exist_ok=True)
        duration = audio_duration_seconds(audio_path)
        with tempfile.TemporaryDirectory(prefix="drumai-transcribe-") as temp:
            work_dir = Path(temp)
            isolated_audio = work_dir / f"source{audio_path.suffix.lower()}"
            shutil.copy2(audio_path, isolated_audio)
            with _override_kick_thresholds(self.kick_config):
                result = engine.transcribe(
                    str(isolated_audio),
                    full_song=True,
                    midi_only=True,
                    verbose=False,
                )
            if not isinstance(result, dict) or not result.get("midi_path"):
                keys = sorted(result) if isinstance(result, dict) else []
                raise EngineOutputError(
                    f"DrumScript returned no MIDI path (result keys: {keys})"
                )
            reported_path = Path(result["midi_path"])
            candidates = [reported_path]
            if not reported_path.is_absolute():
                candidates.extend([work_dir / reported_path, isolated_audio.parent / reported_path])
            midi_source = next((path for path in candidates if path.is_file()), None)
            if midi_source is None or midi_source.stat().st_size == 0:
                raise EngineOutputError("DrumScript MIDI output is missing or empty")

            normalized = midi_to_performance(midi_source)
            if not normalized.events:
                raise EngineOutputError(
                    "DrumScript MIDI contains no GM percussion events on channel 10"
                )
            event_end = max(event.time_seconds for event in normalized.events)
            tempo_end = max(change.time_seconds for change in normalized.tempo_map)
            performance = normalized.model_copy(
                update={
                    "duration_seconds": max(duration, event_end + 0.001, tempo_end + 0.001),
                }
            )
            midi_destination = output_dir / "performance.mid"
            shutil.copy2(midi_source, midi_destination)

        return performance, midi_destination
