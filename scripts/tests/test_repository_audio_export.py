from __future__ import annotations

import sys
from pathlib import Path

import pretty_midi
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from validate_repository_audio import drum_notes, export_predicted_events


def test_event_export_uses_only_explicit_drum_tracks(tmp_path: Path) -> None:
    midi = pretty_midi.PrettyMIDI()
    drums = pretty_midi.Instrument(program=0, is_drum=True, name="Drums")
    drums.notes.append(pretty_midi.Note(velocity=100, pitch=36, start=0.25, end=0.35))
    drums.notes.append(pretty_midi.Note(velocity=80, pitch=42, start=0.5, end=0.55))
    other = pretty_midi.Instrument(program=0, is_drum=False, name="Other")
    other.notes.append(pretty_midi.Note(velocity=90, pitch=60, start=0.75, end=0.9))
    midi.instruments.extend([drums, other])

    destination = tmp_path / "events.csv"
    metrics = export_predicted_events(midi, destination)

    assert metrics == {"note_events": 2, "unknown_pitch_events": 0}
    rows = destination.read_text(encoding="utf-8").splitlines()
    assert rows[0] == "onset_seconds,instrument,pitch,velocity,duration_seconds,track_index"
    assert "0.250000,kick,36,100,0.100000,0" in rows
    assert "0.750000" not in destination.read_text(encoding="utf-8")


def test_missing_drum_flag_is_a_hard_error() -> None:
    midi = pretty_midi.PrettyMIDI()
    other = pretty_midi.Instrument(program=0, is_drum=False)
    other.notes.append(pretty_midi.Note(velocity=90, pitch=36, start=0.0, end=0.1))
    midi.instruments.append(other)

    with pytest.raises(ValueError, match="is_drum=True"):
        drum_notes(midi)
