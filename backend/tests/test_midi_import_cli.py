import mido

from app.midi_import_cli import main


def test_midi_import_cli_writes_canonical_json(tmp_path, monkeypatch):
    midi_path = tmp_path / "source.mid"
    output_path = tmp_path / "events.json"
    midi = mido.MidiFile()
    track = mido.MidiTrack()
    track.append(mido.Message("note_on", channel=9, note=36, velocity=100, time=0))
    midi.tracks.append(track)
    midi.save(midi_path)

    monkeypatch.setattr(
        "sys.argv",
        ["drumai-midi-import", str(midi_path), "--output", str(output_path)],
    )
    assert main() == 0
    payload = output_path.read_text(encoding="utf-8")
    assert payload.endswith("\\n")
    assert '"instrument": "kick"' in payload
