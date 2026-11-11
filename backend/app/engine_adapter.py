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
from pathlib import Path

from .drum_events import DrumPerformance
from .midi_adapter import midi_to_performance


class EngineUnavailableError(RuntimeError):
    """Raised when the optional transcription runtime is not installed."""


class EngineOutputError(RuntimeError):
    """Raised when DrumScript does not produce a usable MIDI artifact."""


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
    """Run a full-song DrumScript transcription and normalize its MIDI output."""

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
