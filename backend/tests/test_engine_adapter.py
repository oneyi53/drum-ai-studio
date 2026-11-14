from __future__ import annotations

import importlib
from pathlib import Path
from types import SimpleNamespace

import mido
import numpy as np
import pytest

from app import engine_adapter
from app.drum_events import DrumInstrument
from app.engine_adapter import KickClassificationConfig


def _sine_signal(freq_hz: float, seconds: float = 1.0, sample_rate: int = 44100) -> np.ndarray:
    t = np.arange(int(seconds * sample_rate), dtype=np.float64) / sample_rate
    return np.sin(2 * np.pi * freq_hz * t).astype(np.float32)


def _band_magnitude(signal: np.ndarray, freq_hz: float, sample_rate: int = 44100) -> float:
    spectrum = np.abs(np.fft.rfft(signal.astype(np.float64)))
    return float(spectrum[round(freq_hz * len(signal) / sample_rate)])


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
    engine = engine_adapter.DrumScriptEngine(
        kick_config=KickClassificationConfig(eq_preprocessing=False)
    )
    performance, midi_path = engine.analyze(source, output_dir)

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
        engine = engine_adapter.DrumScriptEngine(
            kick_config=KickClassificationConfig(eq_preprocessing=False)
        )
        engine.analyze(source, tmp_path / "out")


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
            lfer_min=0.15, peak_freq_min_hz=40.0, peak_freq_max_hz=140.0,
            eq_preprocessing=False,
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
    engine = engine_adapter.DrumScriptEngine(
        kick_config=KickClassificationConfig(eq_preprocessing=False)
    )
    engine.analyze(source, tmp_path / "output")

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
        kick_config=KickClassificationConfig(lfer_min=0.32, eq_preprocessing=False)
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

    engine = engine_adapter.DrumScriptEngine(
        kick_config=KickClassificationConfig(lfer_min=0.15, eq_preprocessing=False)
    )
    with pytest.raises(engine_adapter.EngineUnavailableError, match="does not expose"):
        engine.analyze(source, tmp_path / "out")


def test_kick_eq_boosts_low_frequencies_and_attenuates_subsonic():
    sample_rate = 44100
    signal = (
        _sine_signal(60.0, sample_rate=sample_rate)
        + _sine_signal(1000.0, sample_rate=sample_rate)
        + _sine_signal(10.0, sample_rate=sample_rate)
    )
    filtered = engine_adapter._apply_kick_eq(signal, sample_rate)
    assert filtered.dtype == np.float32
    assert filtered.shape == signal.shape
    # +6 dB shelf below 120 Hz roughly doubles the 60 Hz component, the
    # 30 Hz high-pass removes most of the 10 Hz component, 1 kHz is untouched.
    assert 1.7 < _band_magnitude(filtered, 60.0) / _band_magnitude(signal, 60.0) < 2.2
    assert _band_magnitude(filtered, 10.0) / _band_magnitude(signal, 10.0) < 0.3
    assert 0.9 < _band_magnitude(filtered, 1000.0) / _band_magnitude(signal, 1000.0) < 1.1


def test_kick_eq_empty_input_returns_empty():
    filtered = engine_adapter._apply_kick_eq(np.array([], dtype=np.float32), 44100)
    assert filtered.dtype == np.float32
    assert filtered.size == 0


def test_kick_eq_rejects_non_mono_input():
    stereo = np.zeros((2, 44100), dtype=np.float32)
    with pytest.raises(engine_adapter.EngineUnavailableError, match="mono"):
        engine_adapter._apply_kick_eq(stereo, 44100)


def _eq_import_dispatcher(monkeypatch, fake_engine, fake_load_audio, fail_names=()):
    """Fake drumscript loader/constants; delegate everything else (scipy,
    numpy) to the real import machinery unless listed in fail_names."""
    real_import = importlib.import_module

    def fake_import(name):
        if name in fail_names:
            raise ImportError(name)
        if name == "drumscript":
            return fake_engine
        if name == "drumscript.drum_classifier.classify":
            return fake_engine
        if name == "drumscript.audio_processor.audio_loader":
            return SimpleNamespace(load_audio=fake_load_audio)
        if name == "drumscript.notation_generator.constants":
            return SimpleNamespace(SAMPLE_RATE=44100)
        return real_import(name)

    monkeypatch.setattr(engine_adapter.importlib, "import_module", fake_import)


def _eq_fake_engine(transcribe):
    return SimpleNamespace(
        KICK_LFER_MIN=0.32,
        KICK_FREQ_MIN=40.0,
        KICK_FREQ_MAX=140.0,
        transcribe=transcribe,
    )


def test_engine_adapter_default_config_applies_eq_before_transcribe(tmp_path, monkeypatch):
    seen = {}

    def fake_transcribe(audio_path, **kwargs):
        seen["audio_path"] = audio_path
        seen["lfer_min"] = fake.KICK_LFER_MIN
        wav_path = Path(audio_path)
        assert wav_path.name == "source-eq.wav"
        assert wav_path.is_file()
        from scipy.io import wavfile

        rate, data = wavfile.read(str(wav_path))
        assert rate == 44100
        assert data.size > 0
        midi_path = wav_path.with_suffix(".mid")
        _write_percussion_midi(midi_path)
        return {"midi_path": str(midi_path)}

    fake = _eq_fake_engine(fake_transcribe)

    def fake_load_audio(path, sr=None):
        seen["load_audio_called"] = True
        return _sine_signal(60.0, seconds=0.5), 44100

    _eq_import_dispatcher(monkeypatch, fake, fake_load_audio)
    monkeypatch.setattr(engine_adapter, "audio_duration_seconds", lambda path: 4.0)

    source = tmp_path / "source.wav"
    source.write_bytes(b"fake audio")
    engine_adapter.DrumScriptEngine().analyze(source, tmp_path / "output")

    assert seen["load_audio_called"] is True
    assert seen["lfer_min"] == 0.10
    assert Path(seen["audio_path"]).name == "source-eq.wav"


def test_engine_adapter_eq_disabled_passes_original_audio(tmp_path, monkeypatch):
    seen = {}

    def fake_transcribe(audio_path, **kwargs):
        seen["audio_path"] = audio_path
        midi_path = Path(audio_path).with_suffix(".mid")
        _write_percussion_midi(midi_path)
        return {"midi_path": str(midi_path)}

    def fake_load_audio(path, sr=None):
        raise AssertionError("load_audio must not be called when EQ is disabled")

    _eq_import_dispatcher(monkeypatch, _eq_fake_engine(fake_transcribe), fake_load_audio)
    monkeypatch.setattr(engine_adapter, "audio_duration_seconds", lambda path: 4.0)

    source = tmp_path / "source.wav"
    source.write_bytes(b"fake audio")
    engine = engine_adapter.DrumScriptEngine(
        kick_config=KickClassificationConfig(eq_preprocessing=False)
    )
    engine.analyze(source, tmp_path / "output")

    assert Path(seen["audio_path"]).name == "source.wav"


def test_engine_adapter_eq_fails_closed_when_loader_missing(tmp_path, monkeypatch):
    def never_transcribe(*args, **kwargs):
        raise AssertionError("transcribe must not run when EQ preparation fails")

    _eq_import_dispatcher(
        monkeypatch,
        _eq_fake_engine(never_transcribe),
        lambda *args, **kwargs: None,
        fail_names={"drumscript.audio_processor.audio_loader"},
    )
    monkeypatch.setattr(engine_adapter, "audio_duration_seconds", lambda path: 1.0)
    source = tmp_path / "source.wav"
    source.write_bytes(b"audio")

    with pytest.raises(engine_adapter.EngineUnavailableError, match="drumscript"):
        engine_adapter.DrumScriptEngine().analyze(source, tmp_path / "out")


def test_engine_adapter_eq_fails_closed_when_scipy_missing(tmp_path, monkeypatch):
    def never_transcribe(*args, **kwargs):
        raise AssertionError("transcribe must not run when EQ preparation fails")

    def fake_load_audio(path, sr=None):
        return _sine_signal(60.0, seconds=0.5), 44100

    _eq_import_dispatcher(
        monkeypatch,
        _eq_fake_engine(never_transcribe),
        fake_load_audio,
        fail_names={"scipy.signal"},
    )
    monkeypatch.setattr(engine_adapter, "audio_duration_seconds", lambda path: 1.0)
    source = tmp_path / "source.wav"
    source.write_bytes(b"audio")

    with pytest.raises(engine_adapter.EngineUnavailableError, match="scipy"):
        engine_adapter.DrumScriptEngine().analyze(source, tmp_path / "out")


def test_kick_config_eq_preprocessing_defaults_on_and_restores_stock():
    assert KickClassificationConfig().eq_preprocessing is True
    assert KickClassificationConfig(eq_preprocessing=False).eq_preprocessing is False
    stock = KickClassificationConfig(lfer_min=0.32, eq_preprocessing=False)
    assert stock.is_upstream_default
    assert stock.eq_preprocessing is False
    with pytest.raises(TypeError):
        KickClassificationConfig(eq_preprocessing="yes")


def _write_stock_tempo_midi(path: Path) -> None:
    """Upstream-shaped MIDI: type 1, 220 tpq, set_tempo 69.8 BPM."""
    ticks_per_beat = 220
    ticks_per_second = ticks_per_beat * 69.8 / 60.0
    midi = mido.MidiFile(type=1, ticks_per_beat=ticks_per_beat)
    conductor = mido.MidiTrack()
    conductor.append(
        mido.MetaMessage("set_tempo", tempo=round(60_000_000 / 69.8), time=0)
    )
    conductor.append(
        mido.MetaMessage("time_signature", numerator=4, denominator=4, time=0)
    )
    conductor.append(mido.MetaMessage("end_of_track", time=1))
    midi.tracks.append(conductor)
    notes = mido.MidiTrack()
    notes.append(
        mido.Message(
            "note_on",
            channel=9,
            note=36,
            velocity=101,
            time=round(1.0 * ticks_per_second),
        )
    )
    notes.append(
        mido.Message(
            "note_on",
            channel=9,
            note=36,
            velocity=0,
            time=round(0.2 * ticks_per_second),
        )
    )
    notes.append(mido.MetaMessage("end_of_track", time=0))
    midi.tracks.append(notes)
    midi.save(path)


def _run_engine_with_tempo(monkeypatch, tmp_path, corrected_bpm):
    """Run analyze() with a fake engine and a stubbed tempo correction."""
    from app.drum_events import TempoChange

    def fake_transcribe(audio_path, **kwargs):
        midi_path = Path(audio_path).with_suffix(".mid")
        _write_stock_tempo_midi(midi_path)
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
    monkeypatch.setattr(
        engine_adapter,
        "correct_tempo_map",
        lambda tempo_map, audio, checkpoint: (
            [TempoChange(time_seconds=0, bpm=corrected_bpm, numerator=4, denominator=4)],
            "beat_this",
        ),
    )
    source = tmp_path / "source.wav"
    source.write_bytes(b"fake audio")
    engine = engine_adapter.DrumScriptEngine(
        kick_config=KickClassificationConfig(eq_preprocessing=False)
    )
    return engine.analyze(source, tmp_path / "output")


def _exported_tempo_bpm(midi_path: Path) -> float:
    midi = mido.MidiFile(midi_path)
    tempos = [
        60_000_000 / message.tempo
        for track in midi.tracks
        for message in track
        if message.type == "set_tempo"
    ]
    assert len(tempos) == 1
    return tempos[0]


def test_engine_adapter_exports_corrected_tempo_in_midi(tmp_path, monkeypatch):
    performance, midi_path = _run_engine_with_tempo(monkeypatch, tmp_path, 142.86)
    assert performance.tempo_map[0].bpm == pytest.approx(142.86)
    assert _exported_tempo_bpm(midi_path) == pytest.approx(142.86)
    assert performance.events[0].time_seconds == pytest.approx(1.0, abs=0.01)


def test_engine_adapter_keeps_stock_tempo_when_uncorrected(tmp_path, monkeypatch):
    performance, midi_path = _run_engine_with_tempo(monkeypatch, tmp_path, 69.8)
    assert performance.tempo_map[0].bpm == pytest.approx(69.8)
    assert _exported_tempo_bpm(midi_path) == pytest.approx(69.8)
    assert performance.events[0].time_seconds == pytest.approx(1.0, abs=0.01)
