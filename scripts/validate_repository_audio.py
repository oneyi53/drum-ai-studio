from __future__ import annotations

import csv
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

# Verified against DrumScript's DRUM_NOTATION_MAP in its upstream constants.py.
DRUMSCRIPT_DRUM_MAP = {
    36: "kick",
    38: "snare",
    41: "low_tom",
    45: "mid_tom",
    48: "high_tom",
    42: "closed_hat",
    46: "open_hat",
    49: "crash",
    51: "ride",
}


def drum_notes(midi: pretty_midi.PrettyMIDI) -> list[tuple[int, pretty_midi.Note]]:
    """Return notes only from tracks explicitly marked as percussion."""
    tracks = [track for track in midi.instruments if track.is_drum]
    if not tracks:
        raise ValueError("MIDI contains no percussion track marked is_drum=True")
    return [
        (track_index, note)
        for track_index, track in enumerate(midi.instruments)
        if track.is_drum
        for note in track.notes
    ]


def export_predicted_events(midi: pretty_midi.PrettyMIDI, destination: Path) -> dict[str, int]:
    """Write an auditable event-level prediction CSV (never a ground-truth reference)."""
    notes = drum_notes(midi)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ["onset_seconds", "instrument", "pitch", "velocity", "duration_seconds", "track_index"]
        )
        for track_index, note in sorted(notes, key=lambda item: item[1].start):
            writer.writerow(
                [
                    f"{note.start:.6f}",
                    DRUMSCRIPT_DRUM_MAP.get(note.pitch, f"unknown_{note.pitch}"),
                    note.pitch,
                    note.velocity,
                    f"{note.end - note.start:.6f}",
                    track_index,
                ]
            )
    return {
        "note_events": len(notes),
        "unknown_pitch_events": sum(note.pitch not in DRUMSCRIPT_DRUM_MAP for _, note in notes),
    }


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
        event_csv = OUTPUT_DIR / f"{source.stem}_predicted-events.csv"
        event_metrics = export_predicted_events(midi, event_csv)
        drum_tracks = [track for track in midi.instruments if track.is_drum]
        non_drum_tracks = [track for track in midi.instruments if not track.is_drum]
        events = [note for track in drum_tracks for note in track.notes]
        if not events:
            raise RuntimeError(f"MIDI contains no drum events for {source.name}")

        target = OUTPUT_DIR / f"{source.stem}.mid"
        shutil.copy2(generated, target)
        details = {
            "source": source.name,
            "source_bytes": source.stat().st_size,
            "midi_file": target.name,
            "midi_bytes": target.stat().st_size,
            "predicted_events_csv": event_csv.name,
            "predicted_events_csv_bytes": event_csv.stat().st_size,
            "tempo_changes": len(midi.get_tempo_changes()[0]),
            "instrument_tracks": len(midi.instruments),
            "drum_tracks": len(drum_tracks),
            "non_drum_tracks": len(non_drum_tracks),
            **event_metrics,
            "pitch_counts": {
                str(pitch): sum(1 for note in events if note.pitch == pitch)
                for pitch in sorted({note.pitch for note in events})
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
