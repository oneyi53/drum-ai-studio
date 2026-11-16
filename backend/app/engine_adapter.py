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

from .beat_this_tempo import correct_tempo_map, resolve_checkpoint
from .drum_events import DrumInstrument, DrumPerformance
from .midi_adapter import midi_to_performance, performance_to_midi


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

# Kick EQ preprocessing (2026-11-14, IDMT-SMT-Drums V2, 50 ms tolerance):
# 2nd-order Butterworth high-pass at 30 Hz followed by an RBJ low-shelf
# +6 dB below 120 Hz. Pooled 55-track kick F1 0.792 -> 0.840
# (recall 0.763 -> 0.919, precision 0.823 -> 0.773) at lfer_min=0.10;
# held-out WaveDrum 16-30 F1 0.643 -> 0.783. The 3 kHz beater boost was
# measured and rejected (it dilutes the LFER share, recall collapses).
# Filters are parameter-identical to the experiment harness
# (~/workspace/.ds-scratch/eq-exp/kick_eq_experiment.py): Butterworth HP
# via scipy.signal.butter, RBJ cookbook low-shelf with Q=1.0, causal
# sosfilt, high-pass first, then the shelf.
# Production insertion point (Phase 1, 2026-11-16): the EQ is applied to
# the SEPARATED drums stem, after Demucs runs on the raw mix — never to
# the mix before separation. EQ on the mix before Demucs was a
# self-inflicted wound: it destroyed the kick signal Demucs routes, so
# kicks leaked into the bass stem (electronic: 4 kicks in the old app
# path). The 55-track numbers above are the direct-path measurement (EQ
# on the mix, no separation); the app path is measured by the Phase 1
# harness (~/workspace/.ds-scratch/downstream-plan/): electronic app-path
# F1 0.184 -> 0.361, rock 0.320 -> 0.329 (direction only, vs circular
# first-pass references). See docs/PROJECT_LOG.md (2026-11-14) and
# ~/workspace/.ds-scratch/downstream-plan/PHASE1_IMPLEMENTATION.md.
EQ_HIGHPASS_HZ = 30.0
EQ_LOWSHELF_FREQ_HZ = 120.0
EQ_LOWSHELF_GAIN_DB = 6.0

# Phase 1 downstream rules (2026-11-16, measured in
# ~/workspace/.ds-scratch/downstream-plan/; full numbers in
# PHASE1_IMPLEMENTATION.md). Only the crash rule below ships as a rule;
# the other two Phase 1 candidates were measured and ROLLED BACK, and the
# code deliberately contains no trace of them — do not re-add without
# re-measuring:
#   * Kick dual-channel (bass-stem LF flux): FALSIFIED. The absolute
#     flux threshold 1.3 (guard calibration) would add 156-385 bogus
#     kicks per track, and the relative-flux variant is anti-informative
#     on rock (AUC 0.426) and weak on electronic (0.606). The addition
#     direction is dead: 0 of 325 "unknown" electronic onsets sit near a
#     reference kick, and the classifier already recalls 90% of
#     reference kicks there — the problem is precision, not recall.
#     The downgrade direction (zero bass flux) is a no-op (0-2 kicks per
#     track). The bass stem is therefore NOT used for kick judgment; it
#     is still separated by Demucs and left in the temp dir for future
#     rules. The kick flooding the reorder exposes (rock 331, jazz 536,
#     electronic 248) needs a learned model or a new feature (Phase 2/3).
#   * One main label per onset (margin-strength argmax + whitelist):
#     FALSIFIED. It does not move snare counts at all (rock 331 -> 331,
#     electronic 253 -> 253 — snare+hat is whitelisted and dominant) and
#     it breaks the IDMT gate: kick F1 0.840 -> 0.746 (recall 0.919 ->
#     0.664). Even the minimal kick+snare-only variant drops the gate to
#     0.830. Rule margins are not calibrated confidences: on IDMT, snare
#     false positives have HIGHER hfer margins than true positives
#     (median 0.575 vs 0.530). Multi-label onsets are kept as-is.
#   * Tom gate: NO CHANGE. The HFER distribution does not separate
#     tom-shaped onsets (median 0.47-0.58 vs 0.569 pooled); tom is marked
#     "to be solved by a learned model".
#   * Crash decay suppression (SHIPPED): see CRASH_DECAY_WINDOW_SECONDS.
CRASH_DECAY_WINDOW_SECONDS = 1.5


@dataclass(frozen=True)
class KickClassificationConfig:
    """Kick gate overrides applied to the upstream DrumScript classifier.

    Values are validated ranges, not free-form knobs: lowering ``lfer_min``
    recovers kicks whose low-frequency energy share is diluted by bass or
    mix energy, at the cost of bass-guitar / low-tom false positives.
    The default (``lfer_min=0.10``) is the measured optimum on IDMT-SMT-Drums
    (see module comment); pass ``lfer_min=0.32`` explicitly for the stock
    upstream rule.

    ``eq_preprocessing`` applies the measured kick EQ curve (30 Hz
    high-pass + 120 Hz low-shelf +6 dB) to the separated drums stem
    before transcription; it is on by default. Pass ``False`` to restore
    the pre-EQ behaviour. Stock upstream behaviour is ``lfer_min=0.32`` with
    ``eq_preprocessing=False``.
    """

    lfer_min: float = DEFAULT_KICK_LFER_MIN
    peak_freq_min_hz: float = UPSTREAM_KICK_FREQ_MIN_HZ
    peak_freq_max_hz: float = UPSTREAM_KICK_FREQ_MAX_HZ
    eq_preprocessing: bool = True

    def __post_init__(self) -> None:
        if not 0.0 <= self.lfer_min <= 1.0:
            raise ValueError(f"lfer_min must be within [0, 1], got {self.lfer_min}")
        if not 0.0 < self.peak_freq_min_hz < self.peak_freq_max_hz:
            raise ValueError(
                "peak frequency range must satisfy 0 < min < max, got "
                f"({self.peak_freq_min_hz}, {self.peak_freq_max_hz})"
            )
        if not isinstance(self.eq_preprocessing, bool):
            raise TypeError(
                f"eq_preprocessing must be a bool, got {self.eq_preprocessing!r}"
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


def _rbj_lowshelf_coefficients(
    freq_hz: float, sample_rate_hz: float, gain_db: float
) -> tuple[object, object]:
    """RBJ cookbook low-shelf biquad (b, a), Q=1.0.

    Parameter-identical to the experiment harness: ``alpha =
    sin(w0) / (2 * Q)`` with Q=1.0. Coefficients are computed with
    plain ``math`` so they match the harness's formula exactly.
    """
    import math

    amplitude = 10.0 ** (gain_db / 40.0)
    w0 = 2.0 * math.pi * freq_hz / sample_rate_hz
    alpha = math.sin(w0) / 2.0
    cos = math.cos(w0)
    sqrt_a = math.sqrt(amplitude)
    b0 = amplitude * ((amplitude + 1) - (amplitude - 1) * cos + 2 * sqrt_a * alpha)
    b1 = 2 * amplitude * ((amplitude - 1) - (amplitude + 1) * cos)
    b2 = amplitude * ((amplitude + 1) - (amplitude - 1) * cos - 2 * sqrt_a * alpha)
    a0 = (amplitude + 1) + (amplitude - 1) * cos + 2 * sqrt_a * alpha
    a1 = -2 * ((amplitude - 1) + (amplitude + 1) * cos)
    a2 = (amplitude + 1) + (amplitude - 1) * cos - 2 * sqrt_a * alpha
    return (
        [b0 / a0, b1 / a0, b2 / a0],
        [1.0, a1 / a0, a2 / a0],
    )


def _apply_kick_eq(audio: object, sample_rate_hz: float) -> object:
    """Apply the adopted kick EQ curve to a mono waveform.

    2nd-order Butterworth high-pass at 30 Hz, then an RBJ low-shelf
    +6 dB below 120 Hz, both causal ``sosfilt`` — the same form and
    parameters as the experiment harness. Input is converted to float64,
    output is float32, matching the harness. Raises
    :class:`EngineUnavailableError` if scipy is not installed or the
    signal is not mono, instead of silently returning unfiltered audio.
    """
    try:
        numpy = importlib.import_module("numpy")
        scipy_signal = importlib.import_module("scipy.signal")
    except ImportError as exc:
        raise EngineUnavailableError(
            "kick EQ preprocessing requires scipy, which is not installed "
            "in this worker; install the engine runtime"
        ) from exc
    data = numpy.asarray(audio, dtype=numpy.float64)
    if data.ndim != 1:
        raise EngineUnavailableError(
            f"kick EQ preprocessing expects mono audio, got shape {data.shape}"
        )
    if data.size == 0:
        return numpy.asarray(audio, dtype=numpy.float32)
    sos_hp = scipy_signal.butter(
        2, EQ_HIGHPASS_HZ, btype="highpass", fs=sample_rate_hz, output="sos"
    )
    filtered = scipy_signal.sosfilt(sos_hp, data)
    b, a = _rbj_lowshelf_coefficients(
        EQ_LOWSHELF_FREQ_HZ, sample_rate_hz, EQ_LOWSHELF_GAIN_DB
    )
    filtered = scipy_signal.sosfilt(scipy_signal.tf2sos(b, a), filtered)
    return numpy.asarray(filtered, dtype=numpy.float32)


def _extract_drum_stem(audio_path: Path, work_dir: Path) -> Path:
    """Run Demucs on the RAW mix and return the separated drums stem.

    Separation runs inside ``work_dir`` (``work_dir/htdemucs/<stem>/``),
    so nothing is written to the worker's current directory — the old
    ``transcribe(full_song=True)`` path called ``extract_drum_stem`` with
    no output directory, which dumped ``htdemucs/`` into the CWD.
    The un-EQ'd bass stem is left alongside the drums stem
    (``<same dir>/bass.wav``) for future rules; Phase 1 measured the
    bass-flux kick channel and rolled it back, so nothing reads it yet.
    Fail-closed: a missing upstream splitter interface or a missing
    drums stem raises :class:`EngineUnavailableError` / ``EngineOutputError``
    instead of silently transcribing the mix.
    """
    try:
        splitter_module = importlib.import_module("drumscript.audio_processor.stem_splitter")
        extract_drum_stem = splitter_module.extract_drum_stem
    except (ImportError, AttributeError) as exc:
        raise EngineUnavailableError(
            "stem separation requires drumscript.audio_processor.stem_splitter, "
            "which is not available in this worker; install the engine runtime"
        ) from exc
    try:
        drums_stem = Path(extract_drum_stem(str(audio_path), output_dir=str(work_dir)))
    except (TypeError, ValueError, OSError) as exc:
        raise EngineOutputError(
            f"Demucs stem separation failed for {audio_path.name}: {exc}"
        ) from exc
    if not drums_stem.is_file() or drums_stem.stat().st_size == 0:
        raise EngineOutputError(f"Demucs produced no usable drums stem for {audio_path.name}")
    return drums_stem


def apply_crash_decay_suppression(
    performance: DrumPerformance,
    *,
    window_seconds: float = CRASH_DECAY_WINDOW_SECONDS,
) -> DrumPerformance:
    """Drop crash hits that re-trigger inside a kept crash's decay window.

    Measured (Phase 1, 2026-11-16, 6 real tracks): the crash rule fires
    on sustained high-frequency energy, so one real crash produces a
    chain of candidates — electronic 247 crash labels for 8 reference
    crashes, rock 48 for 4. A plain 1.5 s lockout (keep the first crash,
    drop later crash labels within the window) cuts electronic 247 -> 41
    and rock 48 -> 9, and lifts app-path F1 on both tracks (electronic
    0.361 -> 0.379, rock 0.329 -> 0.334, direction only vs circular
    first-pass references). Non-crash events are untouched, and a crash
    that is an onset's only label removes that onset entirely (it was a
    false trigger, not a hit).

    The plan's "new HF attack" test for candidates inside the window was
    measured and NOT used: neither absolute HF flux nor the relative HF
    attack ratio separates first-in-chain from later candidates
    (electronic medians 1.75 vs 1.51; jazz/latin inverted), so the window
    itself is the mechanism. A crash exactly ``window_seconds`` after a
    kept crash is dropped (the window is inclusive).
    """
    if window_seconds <= 0:
        raise ValueError(f"window_seconds must be positive, got {window_seconds}")
    kept: list = []
    last_crash_time: float | None = None
    for event in sorted(performance.events, key=lambda e: e.time_seconds):
        if event.instrument is DrumInstrument.CRASH:
            if (
                last_crash_time is not None
                and event.time_seconds - last_crash_time <= window_seconds
            ):
                continue
            last_crash_time = event.time_seconds
        kept.append(event)
    return performance.model_copy(update={"events": kept})


def _prepare_eq_audio(audio_path: Path, work_dir: Path) -> Path:
    """Load audio at the DrumScript sample rate, apply the kick EQ curve,
    and write an EQ'd WAV for :func:`transcribe`.

    The input is the separated drums stem (Phase 1 reorder), not the mix:
    the EQ is applied after Demucs, never before it. Output is
    ``drums-eq.wav`` in ``work_dir``.

    Fail-closed: a missing or changed upstream loader/constants interface
    raises :class:`EngineUnavailableError` instead of silently
    transcribing the un-EQ'd file. An empty input is returned unchanged
    (there is nothing to filter; downstream handling is unchanged).
    """
    try:
        loader_module = importlib.import_module("drumscript.audio_processor.audio_loader")
        constants_module = importlib.import_module("drumscript.notation_generator.constants")
        scipy_wavfile = importlib.import_module("scipy.io.wavfile")
    except ImportError as exc:
        raise EngineUnavailableError(
            "kick EQ preprocessing requires drumscript and scipy, which are "
            "not installed in this worker; install the engine runtime"
        ) from exc
    try:
        sample_rate = int(constants_module.SAMPLE_RATE)
        load_audio = loader_module.load_audio
    except (AttributeError, TypeError, ValueError) as exc:
        raise EngineUnavailableError(
            "kick EQ preprocessing cannot use the installed DrumScript: "
            "audio loader interface changed"
        ) from exc
    if sample_rate <= 0:
        raise EngineUnavailableError(
            f"kick EQ preprocessing got an invalid DrumScript sample rate: {sample_rate}"
        )
    try:
        audio, loaded_sr = load_audio(str(audio_path), sr=sample_rate)
    except (ImportError, AttributeError, TypeError) as exc:
        raise EngineUnavailableError(
            "kick EQ preprocessing cannot load audio with the installed "
            "DrumScript: audio loader interface changed"
        ) from exc
    size = getattr(audio, "size", None)
    if size is None:
        raise EngineUnavailableError(
            "kick EQ preprocessing cannot use the installed DrumScript: "
            "audio loader returned an unexpected type"
        )
    if size == 0:
        return audio_path
    eq_audio = _apply_kick_eq(audio, float(loaded_sr))
    eq_path = work_dir / "drums-eq.wav"
    scipy_wavfile.write(str(eq_path), int(loaded_sr), eq_audio)
    return eq_path


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
    The default applies the measured ``lfer_min=0.10`` gate and the
    measured kick EQ preprocessing (30 Hz high-pass + 120 Hz low-shelf
    +6 dB, applied to the separated drums stem after Demucs); pass an
    explicit upstream config for stock DrumScript behaviour.

    Pipeline (Phase 1, 2026-11-16): Demucs runs on the raw mix, the EQ
    goes only on the drums stem, ``transcribe`` runs on that stem with
    ``full_song=False`` (no second separation, no ``htdemucs/`` dump in
    the worker directory), and the crash decay suppression is applied to
    the canonical performance before the output MIDI is written from it.
    No bass-stem kick channel and no one-label rule are applied — both
    were measured and rolled back (see the Phase 1 comment above
    ``CRASH_DECAY_WINDOW_SECONDS``).

    ``beat_this_checkpoint`` enables the Beat This! tempo correction: the
    stock tempogram tempo is replaced with the fused Beat This! tempo
    (see ``app.beat_this_tempo``). Pass an explicit checkpoint path, or
    set ``BEAT_THIS_CHECKPOINT``; when neither is available the stock
    tempo is kept unchanged.
    """

    def __init__(
        self,
        kick_config: KickClassificationConfig | None = None,
        beat_this_checkpoint: Path | str | None = None,
    ) -> None:
        self.kick_config = kick_config or KickClassificationConfig()
        self.beat_this_checkpoint = resolve_checkpoint(beat_this_checkpoint)

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
            # Phase 1 reorder: Demucs runs on the RAW mix (the EQ no
            # longer goes into separation), then the EQ is applied only
            # to the separated drums stem, and transcribe runs on that
            # stem with full_song=False. The old full_song=True call let
            # transcribe run Demucs itself with no output directory,
            # which dumped htdemucs/ into the worker's CWD.
            drums_stem = _extract_drum_stem(isolated_audio, work_dir)
            transcribe_audio = drums_stem
            if self.kick_config.eq_preprocessing:
                transcribe_audio = _prepare_eq_audio(drums_stem, work_dir)
            with _override_kick_thresholds(self.kick_config):
                result = engine.transcribe(
                    str(transcribe_audio),
                    full_song=False,
                    midi_only=True,
                    verbose=False,
                    output_dir=str(work_dir / "transcribe_out"),
                )
            if not isinstance(result, dict) or not result.get("midi_path"):
                keys = sorted(result) if isinstance(result, dict) else []
                raise EngineOutputError(
                    f"DrumScript returned no MIDI path (result keys: {keys})"
                )
            reported_path = Path(result["midi_path"])
            candidates = [reported_path]
            if not reported_path.is_absolute():
                candidates.extend(
                    [
                        work_dir / reported_path,
                        work_dir / "transcribe_out" / reported_path,
                        isolated_audio.parent / reported_path,
                    ]
                )
            midi_source = next((path for path in candidates if path.is_file()), None)
            if midi_source is None or midi_source.stat().st_size == 0:
                raise EngineOutputError("DrumScript MIDI output is missing or empty")

            normalized = midi_to_performance(midi_source)
            if not normalized.events:
                raise EngineOutputError(
                    "DrumScript MIDI contains no GM percussion events on channel 10"
                )
            # Phase 1 rule: crash decay suppression on the canonical
            # performance (see apply_crash_decay_suppression). The output
            # MIDI is written from this performance, not from the
            # upstream file, so suppressed crashes do not leak back in.
            normalized = apply_crash_decay_suppression(normalized)
            # Tempo correction runs on the original audio (pre-EQ) inside
            # the temp dir. Without a Beat This! checkpoint this is a
            # no-op: the stock tempo map is returned unchanged.
            tempo_map, _tempo_source = correct_tempo_map(
                normalized.tempo_map, isolated_audio, self.beat_this_checkpoint
            )
            normalized = normalized.model_copy(update={"tempo_map": tempo_map})
            event_end = max(event.time_seconds for event in normalized.events)
            tempo_end = max(change.time_seconds for change in normalized.tempo_map)
            performance = normalized.model_copy(
                update={
                    "duration_seconds": max(duration, event_end + 0.001, tempo_end + 0.001),
                }
            )
            # The on-disk MIDI is written from the canonical performance
            # under the (possibly corrected) tempo map: a verbatim copy
            # of the upstream file would keep DrumScript's own set_tempo
            # (e.g. rock 69.8 vs the corrected 142.9), so a DAW's bar
            # grid would be off by 2x, and it would keep crashes the
            # decay suppression removed. With no tempo correction the
            # write is a round-trip under the stock tempo, so note times
            # are unchanged.
            midi_destination = output_dir / "performance.mid"
            performance_to_midi(performance, midi_destination)

        return performance, midi_destination
