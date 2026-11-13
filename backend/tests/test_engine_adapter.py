from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import mido
import pytest

from app import engine_adapter
from app.drum_events import DrumInstrument
from app.engine_adapter import KickClassificationConfig


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
        lambda name: SimpleNamespace(
            KICK_LFER_MIN=0.32,
            KICK_FREQ_MIN=40.0,
            KICK_FREQ_MAX=140.0,
            transcribe=fake_transcribe,
        ),
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
        lambda name: SimpleNamespace(
            KICK_LFER_MIN=0.32,
            KICK_FREQ_MIN=40.0,
            KICK_FREQ_MAX=140.0,
            transcribe=lambda *args, **kwargs: {},
        ),
    )
    monkeypatch.setattr(engine_adapter, "audio_duration_seconds", lambda path: 1.0)
    source = tmp_path / "source.wav"
    source.write_bytes(b"audio")

    with pytest.raises(engine_adapter.EngineOutputError, match="no MIDI path"):
        engine_adapter.DrumScriptEngine().analyze(source, tmp_path / "out")


def test_kick_config_default_is_measured_gate_not_upstream():
    config = KickClassificationConfig()
    assert not config.is_upstream_default
    assert config.lfer_min == 0.10
    assert config.peak_freq_min_hz == 40.0
    assert config.peak_freq_max_hz == 140.0


def test_kick_config_explicit_upstream_values_are_stock():
    config = KickClassificationConfig(lfer_min=0.32, peak_freq_min_hz=40.0, peak_freq_max_hz=140.0)
    assert config.is_upstream_default


@pytest.mark.parametrize(
    "kwargs",
    [
        {"lfer_min": -0.01},
        {"lfer_min": 1.01},
        {"peak_freq_min_hz": 0.0, "peak_freq_max_hz": 140.0},
        {"peak_freq_min_hz": 140.0, "peak_freq_max_hz": 140.0},
        {"peak_freq_min_hz": 200.0, "peak_freq_max_hz": 140.0},
    ],
)
def test_kick_config_rejects_invalid_values(kwargs):
    with pytest.raises(ValueError):
        KickClassificationConfig(**kwargs)


def test_engine_adapter_applies_custom_kick_thresholds_and_restores(tmp_path, monkeypatch):
    seen = {}

    def fake_transcribe(audio_path, **kwargs):
        seen["lfer_min"] = fake.KICK_LFER_MIN
        seen["freq_min"] = fake.KICK_FREQ_MIN
        seen["freq_max"] = fake.KICK_FREQ_MAX
        midi_path = Path(audio_path).with_suffix(".mid")
        _write_percussion_midi(midi_path)
        return {"midi_path": str(midi_path)}

    fake = SimpleNamespace(
        KICK_LFER_MIN=0.32,
        KICK_FREQ_MIN=40.0,
        KICK_FREQ_MAX=140.0,
        transcribe=fake_transcribe,
    )
    monkeypatch.setattr(engine_adapter.importlib, "import_module", lambda name: fake)
    monkeypatch.setattr(engine_adapter, "audio_duration_seconds", lambda path: 4.0)

    source = tmp_path / "source.wav"
    source.write_bytes(b"fake audio")
    engine = engine_adapter.DrumScriptEngine(
        kick_config=KickClassificationConfig(
            lfer_min=0.15, peak_freq_min_hz=40.0, peak_freq_max_hz=140.0
        )
    )
    engine.analyze(source, tmp_path / "output")

    assert seen == {"lfer_min": 0.15, "freq_min": 40.0, "freq_max": 140.0}
    assert fake.KICK_LFER_MIN == 0.32
    assert fake.KICK_FREQ_MIN == 40.0
    assert fake.KICK_FREQ_MAX == 140.0


def test_engine_adapter_default_config_applies_measured_gate(tmp_path, monkeypatch):
    seen = {}

    def fake_transcribe(audio_path, **kwargs):
        seen["lfer_min"] = fake.KICK_LFER_MIN
        midi_path = Path(audio_path).with_suffix(".mid")
        _write_percussion_midi(midi_path)
        return {"midi_path": str(midi_path)}

    fake = SimpleNamespace(
        KICK_LFER_MIN=0.32,
        KICK_FREQ_MIN=40.0,
        KICK_FREQ_MAX=140.0,
        transcribe=fake_transcribe,
    )
    monkeypatch.setattr(engine_adapter.importlib, "import_module", lambda name: fake)
    monkeypatch.setattr(engine_adapter, "audio_duration_seconds", lambda path: 4.0)

    source = tmp_path / "source.wav"
    source.write_bytes(b"fake audio")
    engine_adapter.DrumScriptEngine().analyze(source, tmp_path / "output")

    assert seen == {"lfer_min": 0.10}
    assert fake.KICK_LFER_MIN == 0.32


def test_engine_adapter_upstream_config_does_not_touch_thresholds(tmp_path, monkeypatch):
    def fake_transcribe(audio_path, **kwargs):
        midi_path = Path(audio_path).with_suffix(".mid")
        _write_percussion_midi(midi_path)
        return {"midi_path": str(midi_path)}

    fake = SimpleNamespace(
        KICK_LFER_MIN=0.32,
        KICK_FREQ_MIN=40.0,
        KICK_FREQ_MAX=140.0,
        transcribe=fake_transcribe,
    )
    monkeypatch.setattr(engine_adapter.importlib, "import_module", lambda name: fake)
    monkeypatch.setattr(engine_adapter, "audio_duration_seconds", lambda path: 4.0)

    source = tmp_path / "source.wav"
    source.write_bytes(b"fake audio")
    engine = engine_adapter.DrumScriptEngine(
        kick_config=KickClassificationConfig(lfer_min=0.32)
    )
    engine.analyze(source, tmp_path / "output")

    assert fake.KICK_LFER_MIN == 0.32
    assert fake.KICK_FREQ_MIN == 40.0
    assert fake.KICK_FREQ_MAX == 140.0


def test_engine_adapter_fails_closed_when_threshold_override_unsupported(tmp_path, monkeypatch):
    # Fake engine without the upstream threshold attributes: a non-default
    # config must fail loudly instead of silently running unmodified.
    monkeypatch.setattr(
        engine_adapter.importlib,
        "import_module",
        lambda name: SimpleNamespace(transcribe=lambda *args, **kwargs: {}),
    )
    monkeypatch.setattr(engine_adapter, "audio_duration_seconds", lambda path: 1.0)
    source = tmp_path / "source.wav"
    source.write_bytes(b"audio")

    engine = engine_adapter.DrumScriptEngine(kick_config=KickClassificationConfig(lfer_min=0.15))
    with pytest.raises(engine_adapter.EngineUnavailableError, match="does not expose"):
        engine.analyze(source, tmp_path / "out")
