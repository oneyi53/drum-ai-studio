from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf


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

        # Kick: short decaying low-frequency sweep.
        t = np.arange(int(0.16 * sample_rate), dtype=np.float32) / sample_rate
        kick = 0.85 * np.sin(2 * np.pi * (85 - 35 * t / 0.16) * t) * np.exp(-t * 24)
        add(kick.astype(np.float32), start)

        # Snare on beats 2 and 4.
        if beat_index % 4 in (1, 3):
            n = int(0.13 * sample_rate)
            t_snare = np.arange(n, dtype=np.float32) / sample_rate
            noise = rng.normal(0, 1, n).astype(np.float32)
            snare = 0.28 * noise * np.exp(-t_snare * 28)
            add(snare, start)

        # Closed hi-hat eighth notes.
        for offset in (0.0, beat / 2):
            hat_start = start + int(offset * sample_rate)
            n = int(0.035 * sample_rate)
            t_hat = np.arange(n, dtype=np.float32) / sample_rate
            hat = 0.075 * rng.normal(0, 1, n).astype(np.float32) * np.exp(-t_hat * 95)
            add(hat, hat_start)

    # Add a quiet sustained harmonic bed so this is not a drum-only stem.
    t_mix = np.arange(count, dtype=np.float32) / sample_rate
    audio += 0.035 * np.sin(2 * np.pi * 110 * t_mix)
    audio += 0.018 * np.sin(2 * np.pi * 164.81 * t_mix)
    audio = np.clip(audio, -0.98, 0.98)
    sf.write(path, audio, sample_rate, subtype="PCM_16")


def main() -> None:
    import drumscript as ds

    with tempfile.TemporaryDirectory(prefix="drumai-engine-smoke-") as temp_dir:
        source = Path(temp_dir) / "synthetic_full_mix.wav"
        make_synthetic_full_mix(source)

        result = ds.transcribe(
            str(source),
            full_song=True,
            midi_only=True,
            verbose=True,
        )
        if not isinstance(result, dict):
            raise RuntimeError(f"Expected DrumScript dict result, got {type(result).__name__}")

        midi_value = result.get("midi_path")
        if not midi_value:
            raise RuntimeError(f"DrumScript did not return midi_path. Result keys: {sorted(result)}")

        midi_path = Path(midi_value)
        if not midi_path.is_file() or midi_path.stat().st_size == 0:
            raise RuntimeError(f"MIDI output missing or empty: {midi_path}")

        print(f"ENGINE_SMOKE_OK midi={midi_path} bytes={midi_path.stat().st_size}")
        print(f"RESULT_KEYS={sorted(result)}")


if __name__ == "__main__":
    main()
