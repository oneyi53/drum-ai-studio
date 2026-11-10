from __future__ import annotations

import json
import shutil
from pathlib import Path

import pretty_midi


ROOT = Path(__file__).resolve().parents[1]
INPUTS = [
    ROOT / "Creep (Album Version)_Radiohead.mp3",
    ROOT / "Psycho_Muse(1).mp3",
]
OUTPUT_DIR = ROOT / "real-audio-results"


def main() -> None:
    import drumscript as ds

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    summary: list[dict[str, object]] = []

    for source in INPUTS:
        if not source.is_file():
            raise FileNotFoundError(f"Repository test audio missing: {source.name}")

        print(f"REAL_AUDIO_START file={source.name} bytes={source.stat().st_size}", flush=True)
        result = ds.transcribe(
            str(source),
            full_song=True,
            midi_only=True,
            verbose=True,
        )
        if not isinstance(result, dict) or not result.get("midi_path"):
            raise RuntimeError(
                f"No MIDI returned for {source.name}; "
                f"result_type={type(result).__name__}, "
                f"keys={sorted(result) if isinstance(result, dict) else 'n/a'}"
            )

        generated = Path(str(result["midi_path"]))
        if not generated.is_file() or generated.stat().st_size == 0:
            raise RuntimeError(f"MIDI output missing or empty for {source.name}: {generated}")

        midi = pretty_midi.PrettyMIDI(str(generated))
        events = [
            (note.pitch, note.start, note.velocity)
            for instrument in midi.instruments
            for note in instrument.notes
        ]
        if not events:
            raise RuntimeError(f"MIDI contains no drum events for {source.name}")

        target = OUTPUT_DIR / f"{source.stem}.mid"
        shutil.copy2(generated, target)
        details = {
            "source": source.name,
            "source_bytes": source.stat().st_size,
            "midi_file": target.name,
            "midi_bytes": target.stat().st_size,
            "tempo_changes": len(midi.get_tempo_changes()[0]),
            "instrument_tracks": len(midi.instruments),
            "note_events": len(events),
            "pitch_counts": {
                str(pitch): sum(1 for event_pitch, _, _ in events if event_pitch == pitch)
                for pitch in sorted({event_pitch for event_pitch, _, _ in events})
            },
            "duration_seconds": round(midi.get_end_time(), 3),
        }
        summary.append(details)
        print("REAL_AUDIO_RESULT " + json.dumps(details, sort_keys=True), flush=True)

    report = OUTPUT_DIR / "summary.json"
    report.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"REAL_AUDIO_VALIDATION_OK files={len(summary)} output={OUTPUT_DIR}", flush=True)


if __name__ == "__main__":
    main()
