from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import mido
import pytest

from app import engine_adapter
from app.drum_events import DrumInstrument


def _write_percussion_midi(path: Path) -> None:
    midi = mido.MidiFile()
    track = mido.MidiTrack()
    midi.tracks.append(track)
    track.append(mido.Message("note_on", channel=9, note=36, velocity=101, time=0))
    track.append(mido.MetaMessage("end_of_track", time=480))
    midi.save(path)


def test_engine_adapter_runs_full_song_and_persists_canonical_midi(tmp_path, monkeypatch):
    calls = {}

    def fake_transcribe(audio_path, **kwargs):
        calls["audio_path"] = audio_path
        calls.update(kwargs)
        midi_path = Path(audio_path).with_suffix(".mid")
        _write_percussion_midi(midi_path)
        return {"midi_path": str(midi_path)}

    monkeypatch.setattr(
        engine_adapter.importlib,
        "import_module",
        lambda name: SimpleNamespace(transcribe=fake_transcribe),
    )
    monkeypatch.setattr(engine_adapter, "audio_duration_seconds", lambda path: 4.0)

    source = tmp_path / "source.wav"
    source.write_bytes(b"fake audio")
    output_dir = tmp_path / "output"
    performance, midi_path = engine_adapter.DrumScriptEngine().analyze(source, output_dir)

    assert calls["full_song"] is True
    assert calls["midi_only"] is True
    assert calls["verbose"] is False
    assert performance.duration_seconds >= 4.0
    assert performance.events[0].instrument == DrumInstrument.KICK
    assert performance.events[0].velocity == 101
    assert performance.events[0].source == "imported"
    assert midi_path == output_dir / "performance.mid"
    assert midi_path.is_file()


def test_engine_adapter_fails_clearly_when_engine_is_not_installed(tmp_path, monkeypatch):
    def missing_engine(name):
        raise ImportError(name)

    monkeypatch.setattr(engine_adapter.importlib, "import_module", missing_engine)
    source = tmp_path / "source.wav"
    source.write_bytes(b"audio")
    monkeypatch.setattr(engine_adapter, "audio_duration_seconds", lambda path: 1.0)

    with pytest.raises(engine_adapter.EngineUnavailableError, match="not installed"):
        engine_adapter.DrumScriptEngine().analyze(source, tmp_path / "out")


def test_engine_adapter_rejects_missing_midi_output(tmp_path, monkeypatch):
    monkeypatch.setattr(
        engine_adapter.importlib,
        "import_module",
        lambda name: SimpleNamespace(transcribe=lambda *args, **kwargs: {}),
    )
    monkeypatch.setattr(engine_adapter, "audio_duration_seconds", lambda path: 1.0)
    source = tmp_path / "source.wav"
    source.write_bytes(b"audio")

    with pytest.raises(engine_adapter.EngineOutputError, match="no MIDI path"):
        engine_adapter.DrumScriptEngine().analyze(source, tmp_path / "out")
