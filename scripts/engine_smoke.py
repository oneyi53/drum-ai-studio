from __future__ import annotations

import shutil
import tempfile
from collections import Counter
from pathlib import Path

import numpy as np
import soundfile as sf

from app.midi_adapter import midi_to_performance


def make_synthetic_full_mix(path: Path, sample_rate: int = 44100, seconds: float = 8.0) -> None:
    """Create a deterministic, copyright-free mixed test signal with drum transients."""
    count = int(sample_rate * seconds)
    audio = np.zeros(count, dtype=np.float32)
    rng = np.random.default_rng(20261110)

    def add(signal: np.ndarray, start: int) -> None:
        end = min(count, start + len(signal))
        if end > start:
            audio[start:end] += signal[: end - start]

    beat = 60.0 / 120.0
    for beat_index in range(int(seconds / beat)):
        start = int(beat_index * beat * sample_rate)
        t = np.arange(int(0.16 * sample_rate), dtype=np.float32) / sample_rate
        kick = 0.85 * np.sin(2 * np.pi * (85 - 35 * t / 0.16) * t) * np.exp(-t * 24)
        add(kick.astype(np.float32), start)

        if beat_index % 4 in (1, 3):
            n = int(0.13 * sample_rate)
            t_snare = np.arange(n, dtype=np.float32) / sample_rate
            noise = rng.normal(0, 1, n).astype(np.float32)
            add(0.28 * noise * np.exp(-t_snare * 28), start)

        for offset in (0.0, beat / 2):
            hat_start = start + int(offset * sample_rate)
            n = int(0.035 * sample_rate)
            t_hat = np.arange(n, dtype=np.float32) / sample_rate
            hat = 0.075 * rng.normal(0, 1, n).astype(np.float32) * np.exp(-t_hat * 95)
            add(hat, hat_start)

    t_mix = np.arange(count, dtype=np.float32) / sample_rate
    audio += 0.035 * np.sin(2 * np.pi * 110 * t_mix)
    audio += 0.018 * np.sin(2 * np.pi * 164.81 * t_mix)
    sf.write(path, np.clip(audio, -0.98, 0.98), sample_rate, subtype="PCM_16")


def transcribe_and_check(ds: object, source: Path, label: str) -> None:
    """Run full-song transcription and validate its MIDI-to-event normalization."""
    result = ds.transcribe(
        str(source),
        full_song=True,
        midi_only=True,
        verbose=True,
    )
    if not isinstance(result, dict):
        raise RuntimeError(f"{label}: expected dict result, got {type(result).__name__}")

    midi_value = result.get("midi_path")
    if not midi_value:
        raise RuntimeError(f"{label}: no midi_path returned; keys={sorted(result)}")

    midi_path = Path(midi_value)
    if not midi_path.is_file() or midi_path.stat().st_size == 0:
        raise RuntimeError(f"{label}: MIDI output missing or empty: {midi_path}")

    performance = midi_to_performance(midi_path)
    if not performance.events:
        raise RuntimeError(
            f"{label}: MIDI exists but produced no canonical events on GM percussion channel 10"
        )

    instruments = Counter(event.instrument.value for event in performance.events)
    print(
        f"ENGINE_CANONICAL_OK label={label} events={len(performance.events)} "
        f"instruments={dict(sorted(instruments.items()))} "
        f"duration_seconds={performance.duration_seconds:.3f}"
    )
    print(f"ENGINE_SMOKE_OK label={label} midi_bytes={midi_path.stat().st_size}")


def main() -> None:
    import drumscript as ds

    with tempfile.TemporaryDirectory(prefix="drumai-engine-smoke-") as temp_dir:
        temp = Path(temp_dir)
        synthetic = temp / "synthetic_full_mix.wav"
        make_synthetic_full_mix(synthetic)
        transcribe_and_check(ds, synthetic, "synthetic")

        # Run the same full-song path on repository MP3s. Isolated copies keep
        # generated MIDI artifacts out of the checked-out source tree.
        samples = sorted(Path.cwd().glob("*.mp3"))
        if not samples:
            print("REAL_AUDIO_SMOKE_SKIPPED reason=no-root-mp3-files")
        for index, sample in enumerate(samples, start=1):
            sample_dir = temp / f"real-sample-{index}"
            sample_dir.mkdir()
            isolated_source = sample_dir / sample.name
            shutil.copy2(sample, isolated_source)
            transcribe_and_check(ds, isolated_source, f"repository-mp3-{index}")


if __name__ == "__main__":
    main()
